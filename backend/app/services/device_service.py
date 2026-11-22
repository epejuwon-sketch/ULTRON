"""Secure Multi-Device Connectivity Mesh: pairing, device auth, explicit permissions, cross-device task sync, and revocation."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.security import hash_token
from app.db.models import DevicePairingCodeRecord, DeviceRecord, DeviceTaskRecord
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.notification_service import create_notification
from app.services.realtime_hub import realtime_hub

SUPPORTED_PLATFORMS = frozenset({"windows", "macos", "ios", "ipados", "android", "pwa"})

# All sensitive permissions default to False and require explicit user opt-in & interaction.
SENSITIVE_PERMISSIONS = frozenset(
    {
        "camera",
        "microphone",
        "location",
        "contacts",
        "messages",
        "personal_files",
        "app_launch",
        "local_dev_tools",
    }
)

DEFAULT_DEVICE_PERMISSIONS: dict[str, bool] = {
    "device_status": True,
    "notifications": True,
    "task_sync": True,
    "authorized_folder_read": False,
    "authorized_folder_write": False,
    "app_launch": False,
    "local_dev_tools": False,
    "camera": False,
    "microphone": False,
    "location": False,
    "contacts": False,
    "messages": False,
    "personal_files": False,
}

ACTION_REQUIRED_PERMISSION: dict[str, str] = {
    "status_check": "device_status",
    "notify": "notifications",
    "folder_list": "authorized_folder_read",
    "folder_read": "authorized_folder_read",
    "folder_write": "authorized_folder_write",
    "launch_app": "app_launch",
    "run_dev_tool": "local_dev_tools",
    "capture_camera": "camera",
    "capture_audio": "microphone",
    "read_location": "location",
}


def init_device_pairing(
    db: Session,
    *,
    principal: Principal,
    target_platform: str,
    requested_permissions: dict[str, bool] | None = None,
    authorized_folders: list[str] | None = None,
    ttl_minutes: int = 10,
) -> dict[str, Any]:
    """Generate a single-use cryptographic pairing code for a user device."""
    platform = target_platform.strip().lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValidationError(f"Unsupported platform '{target_platform}'. Must be one of {sorted(SUPPORTED_PLATFORMS)}.")

    merged_perms = dict(DEFAULT_DEVICE_PERMISSIONS)
    for k, v in (requested_permissions or {}).items():
        if k in DEFAULT_DEVICE_PERMISSIONS:
            merged_perms[k] = bool(v)

    raw_code = f"ULT-{secrets.token_hex(4).upper()}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, min(30, ttl_minutes)))

    rec = DevicePairingCodeRecord(
        pairing_id=f"pair_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        created_by_user_id=principal.user_id,
        created_by_username=principal.username,
        code_hash=hash_token(raw_code),
        target_platform=platform,
        requested_permissions_json=json.dumps(merged_perms),
        authorized_folders_json=json.dumps([f.strip() for f in (authorized_folders or []) if f.strip()]),
        consumed=False,
        expires_at=expires_at,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="DEVICE_PAIRING_INITIATED",
        resource=rec.pairing_id,
        outcome=f"PLATFORM={platform}",
    )
    db.commit()
    return {
        "pairing_id": rec.pairing_id,
        "pairing_code": raw_code,
        "target_platform": platform,
        "permissions": merged_perms,
        "authorized_folders": json.loads(rec.authorized_folders_json),
        "expires_at": expires_at.isoformat(),
    }


def complete_device_pairing(
    db: Session,
    *,
    pairing_code: str,
    device_name: str,
    platform: str,
    os_version: str = "",
    app_version: str = "1.0.0",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Exchange a valid single-use pairing code for a cryptographic device identity and token."""
    clean_platform = platform.strip().lower()
    code_hash = hash_token(pairing_code.strip().upper())
    pair = db.execute(
        select(DevicePairingCodeRecord).where(DevicePairingCodeRecord.code_hash == code_hash)
    ).scalar_one_or_none()
    if pair is None or pair.consumed:
        raise AuthenticationError("Invalid or already used device pairing code.")

    now = datetime.now(timezone.utc)
    exp = pair.expires_at if pair.expires_at.tzinfo else pair.expires_at.replace(tzinfo=timezone.utc)
    if now >= exp:
        raise AuthenticationError("Device pairing code has expired.")
    if pair.target_platform != clean_platform:
        raise ValidationError(f"Pairing code was issued for '{pair.target_platform}', not '{clean_platform}'.")

    raw_device_token = f"ult_dev_{secrets.token_urlsafe(32)}"
    device = DeviceRecord(
        device_id=f"dev_{uuid.uuid4().hex[:16]}",
        tenant_id=pair.tenant_id,
        owner_user_id=pair.created_by_user_id,
        name=device_name.strip()[:160],
        platform=clean_platform,
        device_token_hash=hash_token(raw_device_token),
        os_version=os_version.strip()[:120],
        app_version=app_version.strip()[:64],
        capabilities_json=json.dumps(capabilities or ["device_status", "notifications", "task_sync"]),
        permissions_json=pair.requested_permissions_json,
        authorized_folders_json=pair.authorized_folders_json,
        status="ONLINE",
        last_seen_at=now,
    )
    pair.consumed = True
    db.add(device)
    append_audit_log(
        db,
        tenant_id=pair.tenant_id,
        actor=pair.created_by_username,
        action="DEVICE_PAIRED",
        resource=device.device_id,
        outcome=f"{clean_platform}:{device.name}",
    )
    create_notification(
        db,
        tenant_id=pair.tenant_id,
        user_id=pair.created_by_user_id,
        severity="INFO",
        category="DEVICE_MESH",
        title=f"Device Paired: {device.name}",
        message=f"Platform '{clean_platform}' paired successfully.",
        metadata={"device_id": device.device_id, "platform": clean_platform},
        commit=False,
    )
    db.commit()
    db.refresh(device)
    result = serialize_device(device)
    result["device_token"] = raw_device_token  # returned once on pairing completion
    return result


def authenticate_device_token(db: Session, *, raw_token: str) -> DeviceRecord:
    """Authenticate a paired device using its cryptographic `X-Device-Token`."""
    if not raw_token or not raw_token.strip():
        raise AuthenticationError("Missing X-Device-Token header.")
    rec = db.execute(
        select(DeviceRecord).where(DeviceRecord.device_token_hash == hash_token(raw_token.strip()))
    ).scalar_one_or_none()
    if rec is None or rec.status == "REVOKED" or rec.revoked_at is not None:
        raise AuthenticationError("Invalid or revoked device token.")
    return rec


def record_device_heartbeat(
    db: Session,
    *,
    device: DeviceRecord,
    os_version: str | None = None,
    app_version: str | None = None,
    capabilities: list[str] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    device.status = "ONLINE"
    device.last_seen_at = now
    if os_version:
        device.os_version = os_version.strip()[:120]
    if app_version:
        device.app_version = app_version.strip()[:64]
    if capabilities is not None:
        device.capabilities_json = json.dumps(capabilities)
    db.commit()
    db.refresh(device)
    realtime_hub.publish_sync(
        device.tenant_id,
        "device.heartbeat",
        {"device_id": device.device_id, "name": device.name, "telemetry": telemetry or {}},
    )
    return serialize_device(device)


def update_device_permissions(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
    permissions: dict[str, bool],
    authorized_folders: list[str] | None = None,
) -> dict[str, Any]:
    device = _get_tenant_device(db, tenant_id=principal.tenant_id, device_id=device_id)
    current = json.loads(device.permissions_json or "{}")
    for k, v in permissions.items():
        if k in DEFAULT_DEVICE_PERMISSIONS:
            current[k] = bool(v)
    device.permissions_json = json.dumps(current)
    if authorized_folders is not None:
        device.authorized_folders_json = json.dumps([f.strip() for f in authorized_folders if f.strip()])
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="DEVICE_PERMISSIONS_UPDATED",
        resource=device.device_id,
        outcome="UPDATED",
        metadata={"permissions": current},
    )
    db.commit()
    db.refresh(device)
    return serialize_device(device)


def revoke_device(db: Session, *, principal: Principal, device_id: str) -> dict[str, Any]:
    device = _get_tenant_device(db, tenant_id=principal.tenant_id, device_id=device_id)
    now = datetime.now(timezone.utc)
    device.status = "REVOKED"
    device.revoked_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="DEVICE_SESSION_REVOKED",
        resource=device.device_id,
        outcome="REVOKED",
    )
    db.commit()
    db.refresh(device)
    return serialize_device(device)


def dispatch_device_task(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
    action: str,
    payload: dict[str, Any],
    parent_task_id: str | None = None,
) -> dict[str, Any]:
    """Queue a cross-device task only if device is active and explicitly grants the required permission."""
    device = _get_tenant_device(db, tenant_id=principal.tenant_id, device_id=device_id)
    if device.status == "REVOKED":
        raise ConflictError("Cannot dispatch tasks to a revoked device.")

    clean_action = action.strip().lower()
    req_perm = ACTION_REQUIRED_PERMISSION.get(clean_action)
    if req_perm is None:
        raise ValidationError(f"Unsupported device action '{action}'.")

    perms = json.loads(device.permissions_json or "{}")
    if not perms.get(req_perm, False):
        raise AuthorizationError(
            f"Device '{device.name}' has not granted required permission '{req_perm}' for action '{clean_action}'.",
            details={"device_id": device.device_id, "required_permission": req_perm},
        )

    sensitive = req_perm in SENSITIVE_PERMISSIONS or clean_action == "folder_write"
    dt_id = f"dtk_{uuid.uuid4().hex[:16]}"
    dt = DeviceTaskRecord(
        device_task_id=dt_id,
        tenant_id=principal.tenant_id,
        device_id=device.device_id,
        parent_task_id=parent_task_id,
        action=clean_action,
        payload_json=json.dumps(payload, default=str),
        requires_user_interaction=sensitive,
        status="WAITING_FOR_APPROVAL" if sensitive else "PENDING",
        created_by=principal.username,
    )
    db.add(dt)
    db.flush()

    approval_payload = None
    if sensitive:
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type="DEVICE_SENSITIVE_ACTION",
            reason=f"Sensitive device action '{clean_action}' on '{device.name}' requires explicit user authorization.",
            risk_level="HIGH",
            resource_ref=dt_id,
            payload={"device_id": device.device_id, "action": clean_action, "payload": payload},
            commit=False,
        )
        dt.approval_id = approval.approval_id
        approval_payload = serialize_approval(approval)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="DEVICE_TASK_DISPATCHED",
        resource=f"{device.device_id}:{dt_id}",
        outcome=f"ACTION={clean_action}|STATUS={dt.status}",
    )
    db.commit()
    db.refresh(dt)
    out = serialize_device_task(dt)
    out["approval"] = approval_payload
    realtime_hub.publish_sync(principal.tenant_id, "device.task.created", out)
    return out


def poll_pending_device_tasks(db: Session, *, device: DeviceRecord) -> list[dict[str, Any]]:
    rows = db.execute(
        select(DeviceTaskRecord)
        .where(DeviceTaskRecord.device_id == device.device_id, DeviceTaskRecord.status == "PENDING")
        .order_by(DeviceTaskRecord.created_at.asc())
        .limit(20)
    ).scalars().all()
    for r in rows:
        r.status = "DISPATCHED"
        r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return [serialize_device_task(r) for r in rows]


def report_device_task_result(
    db: Session,
    *,
    device: DeviceRecord,
    device_task_id: str,
    status_value: str,
    result: dict[str, Any],
    error_detail: str | None = None,
) -> dict[str, Any]:
    dt = db.execute(
        select(DeviceTaskRecord).where(
            DeviceTaskRecord.device_task_id == device_task_id,
            DeviceTaskRecord.device_id == device.device_id,
        )
    ).scalar_one_or_none()
    if dt is None:
        raise NotFoundError(f"Device task '{device_task_id}' not found.")

    norm = status_value.strip().upper()
    if norm not in {"COMPLETED", "FAILED", "REJECTED"}:
        raise ValidationError("Device task report status must be COMPLETED, FAILED, or REJECTED.")
    dt.status = norm
    dt.result_json = json.dumps(result, default=str)
    dt.error_detail = error_detail
    dt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dt)
    out = serialize_device_task(dt)
    realtime_hub.publish_sync(device.tenant_id, "device.task.updated", out)
    return out


def list_devices(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(DeviceRecord).where(DeviceRecord.tenant_id == tenant_id).order_by(DeviceRecord.created_at.desc())
    ).scalars().all()
    return [serialize_device(r) for r in rows]


def _get_tenant_device(db: Session, *, tenant_id: str, device_id: str) -> DeviceRecord:
    rec = db.execute(
        select(DeviceRecord).where(DeviceRecord.device_id == device_id, DeviceRecord.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Device '{device_id}' not found.")
    return rec


def serialize_device(d: DeviceRecord) -> dict[str, Any]:
    return {
        "device_id": d.device_id,
        "tenant_id": d.tenant_id,
        "owner_user_id": d.owner_user_id,
        "name": d.name,
        "platform": d.platform,
        "os_version": d.os_version,
        "app_version": d.app_version,
        "capabilities": json.loads(d.capabilities_json or "[]"),
        "permissions": json.loads(d.permissions_json or "{}"),
        "authorized_folders": json.loads(d.authorized_folders_json or "[]"),
        "status": d.status,
        "last_seen_at": d.last_seen_at.isoformat(),
        "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
        "created_at": d.created_at.isoformat(),
    }


def serialize_device_task(dt: DeviceTaskRecord) -> dict[str, Any]:
    return {
        "device_task_id": dt.device_task_id,
        "device_id": dt.device_id,
        "parent_task_id": dt.parent_task_id,
        "action": dt.action,
        "payload": json.loads(dt.payload_json or "{}"),
        "requires_user_interaction": dt.requires_user_interaction,
        "approval_id": dt.approval_id,
        "status": dt.status,
        "result": json.loads(dt.result_json or "{}"),
        "error_detail": dt.error_detail,
        "created_by": dt.created_by,
        "created_at": dt.created_at.isoformat(),
    }
