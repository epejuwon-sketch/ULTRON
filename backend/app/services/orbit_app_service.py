"""ORBIT Persistent Device Application Launch & Permission Service."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import DeviceAppPermissionRecord, DeviceRecord
from app.db.repositories import append_audit_log
from app.services.device_service import dispatch_device_task

SUPPORTED_ORBIT_APPS: dict[str, dict[str, Any]] = {
    "spotify": {
        "app_id": "spotify",
        "name": "Spotify",
        "category": "Media",
        "ios_scheme": "spotify://",
        "universal_link": "https://open.spotify.com",
        "android_intent": "intent://open.spotify.com/#Intent;scheme=https;package=com.spotify.music;end",
        "web_fallback": "https://open.spotify.com",
        "desktop_app_key": "spotify",
        "ios_note": "iOS PWA uses Universal Links / spotify:// on direct tap, with Spotify Web fallback if the native app is unavailable.",
    },
    "whatsapp": {
        "app_id": "whatsapp",
        "name": "WhatsApp",
        "category": "Communication",
        "ios_scheme": "whatsapp://",
        "universal_link": "https://wa.me/",
        "android_intent": "intent://send/#Intent;scheme=whatsapp;package=com.whatsapp;end",
        "web_fallback": "https://web.whatsapp.com",
        "desktop_app_key": "whatsapp",
        "ios_note": "iOS PWA opens whatsapp:// or wa.me Universal Link on direct user tap.",
    },
    "gmail": {
        "app_id": "gmail",
        "name": "Gmail",
        "category": "Communication",
        "ios_scheme": "googlegmail://",
        "universal_link": "https://mail.google.com/",
        "android_intent": "intent://mail.google.com/#Intent;scheme=https;package=com.google.android.gm;end",
        "web_fallback": "https://mail.google.com/",
        "desktop_app_key": "gmail",
        "ios_note": "iOS PWA opens googlegmail:// on direct tap or falls back to Gmail Web.",
    },
    "settings": {
        "app_id": "settings",
        "name": "Settings",
        "category": "System",
        "ios_scheme": "App-Prefs:",
        "universal_link": "",
        "android_intent": "intent:#Intent;action=android.settings.SETTINGS;end",
        "web_fallback": "/settings/preferences",
        "desktop_app_key": "settings",
        "ios_note": "Apple restricts PWAs from opening arbitrary iOS System Settings; ULTRON opens its Settings workspace when iOS blocks App-Prefs:.",
    },
    "google_calendar": {
        "app_id": "google_calendar",
        "name": "Google Calendar",
        "category": "Productivity",
        "ios_scheme": "googlecalendar://",
        "universal_link": "https://calendar.google.com/",
        "android_intent": "intent://calendar.google.com/#Intent;scheme=https;package=com.google.android.calendar;end",
        "web_fallback": "https://calendar.google.com/",
        "desktop_app_key": "google_calendar",
        "ios_note": "iOS PWA opens googlecalendar:// on direct tap or falls back to Google Calendar Web.",
    },
}

_SPOTIFY_URI_RE = re.compile(r"spotify:(playlist|artist|track|album):([A-Za-z0-9]+)")
_SPOTIFY_URL_RE = re.compile(r"open\.spotify\.com/(playlist|artist|track|album)/([A-Za-z0-9]+)")


def _resolve_spotify_targets(target_uri: str | None) -> tuple[str, str]:
    raw = (target_uri or "").strip()
    if not raw:
        return "spotify://", "https://open.spotify.com"
    m_uri = _SPOTIFY_URI_RE.search(raw)
    if m_uri:
        kind, oid = m_uri.group(1), m_uri.group(2)
        return f"spotify://{kind}/{oid}", f"https://open.spotify.com/{kind}/{oid}"
    m_url = _SPOTIFY_URL_RE.search(raw)
    if m_url:
        kind, oid = m_url.group(1), m_url.group(2)
        return f"spotify://{kind}/{oid}", f"https://open.spotify.com/{kind}/{oid}"
    lower = raw.lower()
    for kind in ("playlist", "artist", "track", "album"):
        if kind in lower:
            q = re.sub(rf".*\b{kind}\b\s*", "", raw, flags=re.I).strip()
            if q:
                from urllib.parse import quote
                return f"spotify://search/{quote(q)}", f"https://open.spotify.com/search/{quote(q)}"
    return "spotify://", "https://open.spotify.com"


def list_app_permissions(
    db: Session,
    *,
    principal: Principal,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(DeviceAppPermissionRecord).where(
        DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
        DeviceAppPermissionRecord.user_id == principal.user_id,
    )
    if device_id:
        stmt = stmt.where(DeviceAppPermissionRecord.device_id == device_id.strip())
    rows = db.execute(stmt.order_by(DeviceAppPermissionRecord.updated_at.desc())).scalars().all()
    return [_serialize_app_perm(r) for r in rows]


def set_app_permission(
    db: Session,
    *,
    principal: Principal,
    app_id: str,
    device_id: str,
    device_label: str,
    decision: str,
) -> dict[str, Any]:
    clean_app = app_id.strip().lower()
    if clean_app not in SUPPORTED_ORBIT_APPS:
        raise ValidationError(f"Unsupported ORBIT application '{app_id}'.")
    clean_dec = decision.strip().upper()
    if clean_dec not in {"ALWAYS_ALLOW", "DENIED", "REVOKED"}:
        raise ValidationError("decision must be ALWAYS_ALLOW, DENIED, or REVOKED.")

    app_meta = SUPPORTED_ORBIT_APPS[clean_app]
    clean_dev = device_id.strip() or "this_device"
    now = datetime.now(timezone.utc)

    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == clean_app,
        )
    ).scalar_one_or_none()

    if rec is None:
        rec = DeviceAppPermissionRecord(
            permission_id=f"dap_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            device_id=clean_dev,
            device_label=(device_label or "This Device").strip()[:160],
            app_id=clean_app,
            app_name=app_meta["name"],
            status=clean_dec,
            permission_scope="app_launch",
            approved_at=now if clean_dec == "ALWAYS_ALLOW" else None,
        )
        db.add(rec)
    else:
        rec.device_label = (device_label or rec.device_label).strip()[:160]
        rec.status = clean_dec
        rec.permission_scope = "app_launch"
        if clean_dec == "ALWAYS_ALLOW":
            rec.approved_at = now
        rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_PERMISSION_UPDATED",
        resource=f"{clean_dev}:{clean_app}",
        outcome=clean_dec,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_app_perm(rec)


def revoke_app_permission(
    db: Session,
    *,
    principal: Principal,
    permission_id: str,
) -> dict[str, Any]:
    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.permission_id == permission_id,
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Application permission '{permission_id}' not found.")
    rec.status = "REVOKED"
    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_PERMISSION_REVOKED",
        resource=f"{rec.device_id}:{rec.app_id}",
        outcome="REVOKED",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_app_perm(rec)


def prepare_or_dispatch_app_launch(
    db: Session,
    *,
    principal: Principal,
    app_id: str,
    device_id: str,
    device_label: str = "This Device",
    platform: str = "ios",
    target_uri: str | None = None,
    allow_once: bool = False,
) -> dict[str, Any]:
    clean_app = app_id.strip().lower()
    if clean_app not in SUPPORTED_ORBIT_APPS:
        raise ValidationError(f"Unsupported ORBIT application '{app_id}'.")
    app_meta = SUPPORTED_ORBIT_APPS[clean_app]
    clean_dev = device_id.strip() or "this_device"

    perm = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == clean_app,
        )
    ).scalar_one_or_none()

    if perm is not None and perm.status == "DENIED" and not allow_once:
        return {
            "status": "DENIED",
            "app_id": clean_app,
            "app_name": app_meta["name"],
            "device_id": clean_dev,
            "message": f"Launch permission for {app_meta['name']} on this device is currently denied.",
        }

    has_always_allow = perm is not None and perm.status == "ALWAYS_ALLOW"
    if not has_always_allow and not allow_once:
        return {
            "status": "APPROVAL_REQUIRED",
            "app_id": clean_app,
            "app_name": app_meta["name"],
            "device_id": clean_dev,
            "device_label": device_label,
            "permission_scope": "app_launch",
            "prompt": f"Allow ULTRON to open {app_meta['name']} on this device whenever you request it?",
            "actions": ["allow_once", "always_allow", "deny"],
        }

    # Resolve safe launch URLs (whitelisted schemes only; never arbitrary external commands)
    if clean_app == "spotify":
        scheme_url, web_url = _resolve_spotify_targets(target_uri)
    else:
        scheme_url = app_meta["ios_scheme"]
        web_url = app_meta["web_fallback"]

    now = datetime.now(timezone.utc)
    desktop_task = None
    launch_status = "SCHEME_DISPATCHED"

    if platform.strip().lower() in {"windows", "macos", "linux"}:
        paired = db.execute(
            select(DeviceRecord).where(
                DeviceRecord.device_id == clean_dev,
                DeviceRecord.tenant_id == principal.tenant_id,
                DeviceRecord.status == "ACTIVE",
            )
        ).scalar_one_or_none()
        if paired is not None:
            perms = json.loads(paired.permissions_json or "{}")
            if perms.get("execute_commands"):
                desktop_task = dispatch_device_task(
                    db,
                    principal=principal,
                    device_id=paired.device_id,
                    action="open_application",
                    payload={"app_id": app_meta["desktop_app_key"], "target_url": web_url},
                )
                launch_status = "DESKTOP_TASK_QUEUED"

    if perm is not None:
        perm.last_launch_at = now
        perm.last_launch_status = launch_status
        perm.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_LAUNCH_DISPATCHED",
        resource=f"{clean_dev}:{clean_app}",
        outcome=f"mode={launch_status}|always_allow={has_always_allow}",
    )
    db.commit()

    return {
        "status": "READY_TO_LAUNCH",
        "app_id": clean_app,
        "app_name": app_meta["name"],
        "device_id": clean_dev,
        "permission_mode": "ALWAYS_ALLOW" if has_always_allow else "ALLOW_ONCE",
        "launch_status": launch_status,
        "launch_url": scheme_url,
        "universal_link": app_meta.get("universal_link") or web_url,
        "android_intent_url": app_meta["android_intent"],
        "web_fallback_url": web_url,
        "desktop_task": desktop_task,
        "platform_limitation_note": app_meta["ios_note"],
        "os_confirmed": False,
    }


def _serialize_app_perm(r: DeviceAppPermissionRecord) -> dict[str, Any]:
    return {
        "permission_id": r.permission_id,
        "user_id": r.user_id,
        "device_id": r.device_id,
        "device_label": r.device_label,
        "app_id": r.app_id,
        "app_name": r.app_name,
        "status": r.status,
        "permission_scope": r.permission_scope,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "last_launch_at": r.last_launch_at.isoformat() if r.last_launch_at else None,
        "last_launch_status": r.last_launch_status,
        "updated_at": r.updated_at.isoformat(),
    }
