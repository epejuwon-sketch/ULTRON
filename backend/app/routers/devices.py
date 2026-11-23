"""Multi-Device Connectivity Mesh routes (Windows, macOS, iOS, iPadOS, Android, PWA)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.device_service import (
    authenticate_device_token,
    complete_device_pairing,
    dispatch_device_task,
    init_device_pairing,
    list_devices,
    poll_pending_device_tasks,
    record_device_heartbeat,
    report_device_task_result,
    revoke_device,
    update_device_permissions,
)
from app.services.orbit_app_service import (
    SUPPORTED_ORBIT_APPS,
    list_app_permissions,
    prepare_or_dispatch_app_launch,
    revoke_app_permission,
    set_app_permission,
)

router = APIRouter(prefix="/api/v1/devices", tags=["Multi-Device Connectivity"])


class PairInitRequest(BaseModel):
    target_platform: str = Field(min_length=3, max_length=32)
    requested_permissions: dict[str, bool] = Field(default_factory=dict)
    authorized_folders: list[str] = Field(default_factory=list)
    ttl_minutes: int = Field(default=10, ge=1, le=30)


class PairCompleteRequest(BaseModel):
    pairing_code: str = Field(min_length=6, max_length=64)
    device_name: str = Field(min_length=2, max_length=160)
    platform: str = Field(min_length=3, max_length=32)
    os_version: str = Field(default="", max_length=120)
    app_version: str = Field(default="2026.3.0", max_length=64)
    capabilities: list[str] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    os_version: str | None = None
    app_version: str | None = None
    capabilities: list[str] | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class UpdatePermissionsRequest(BaseModel):
    permissions: dict[str, bool]
    authorized_folders: list[str] | None = None


class DispatchDeviceTaskRequest(BaseModel):
    action: str = Field(min_length=2, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None


class ReportDeviceTaskRequest(BaseModel):
    status: str = Field(min_length=4, max_length=32)
    result: dict[str, Any] = Field(default_factory=dict)
    error_detail: str | None = None


@router.post("/pair/init", status_code=status.HTTP_201_CREATED)
def api_pair_init(
    body: PairInitRequest,
    principal: Principal = Depends(require_perm("devices:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return init_device_pairing(
        db,
        principal=principal,
        target_platform=body.target_platform,
        requested_permissions=body.requested_permissions,
        authorized_folders=body.authorized_folders,
        ttl_minutes=body.ttl_minutes,
    )


@router.post("/pair/complete", status_code=status.HTTP_201_CREATED)
def api_pair_complete(body: PairCompleteRequest, db: Session = Depends(get_db)) -> dict:
    """Public pairing exchange authenticated strictly by the single-use cryptographic pairing code."""
    return complete_device_pairing(
        db,
        pairing_code=body.pairing_code,
        device_name=body.device_name,
        platform=body.platform,
        os_version=body.os_version,
        app_version=body.app_version,
        capabilities=body.capabilities or None,
    )


@router.get("")
def api_list_devices(
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_devices(db, tenant_id=principal.tenant_id)
    return {
        "total": len(items),
        "devices": items,
        "empty_state": None if items else "No devices paired yet. Call POST /api/v1/devices/pair/init to pair a device.",
    }


@router.post("/{device_id}/heartbeat")
def api_device_heartbeat(
    device_id: str,
    body: HeartbeatRequest,
    x_device_token: str = Header(default="", alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> dict:
    device = authenticate_device_token(db, raw_token=x_device_token)
    if device.device_id != device_id:
        raise AuthorizationError("Device token does not match target device_id.")
    return record_device_heartbeat(
        db,
        device=device,
        os_version=body.os_version,
        app_version=body.app_version,
        capabilities=body.capabilities,
        telemetry=body.telemetry,
    )


@router.patch("/{device_id}/permissions")
def api_device_permissions(
    device_id: str,
    body: UpdatePermissionsRequest,
    principal: Principal = Depends(require_perm("devices:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return update_device_permissions(
        db,
        principal=principal,
        device_id=device_id,
        permissions=body.permissions,
        authorized_folders=body.authorized_folders,
    )


@router.post("/{device_id}/revoke")
def api_device_revoke(
    device_id: str,
    principal: Principal = Depends(require_perm("devices:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return revoke_device(db, principal=principal, device_id=device_id)


@router.post("/{device_id}/tasks", status_code=status.HTTP_201_CREATED)
def api_dispatch_device_task(
    device_id: str,
    body: DispatchDeviceTaskRequest,
    principal: Principal = Depends(require_perm("devices:execute")),
    db: Session = Depends(get_db),
) -> dict:
    return dispatch_device_task(
        db,
        principal=principal,
        device_id=device_id,
        action=body.action,
        payload=body.payload,
        parent_task_id=body.parent_task_id,
    )


@router.get("/{device_id}/tasks/pending")
def api_poll_device_tasks(
    device_id: str,
    x_device_token: str = Header(default="", alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> dict:
    device = authenticate_device_token(db, raw_token=x_device_token)
    if device.device_id != device_id:
        raise AuthorizationError("Device token does not match target device_id.")
    tasks = poll_pending_device_tasks(db, device=device)
    return {"total": len(tasks), "tasks": tasks}


from app.services.orbit_location_service import (
    create_location_alert,
    list_device_locations,
    list_location_alerts,
    report_device_location,
    set_location_sharing_state,
)


class ReportLocationRequest(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_meters: float = Field(default=0.0, ge=0.0)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    label: str = Field(default="", max_length=160)


class LocationControlRequest(BaseModel):
    action: str = Field(pattern="^(PAUSE|RESUME|REVOKE)$")


class CreateLocationAlertRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    center_lat: float = Field(ge=-90.0, le=90.0)
    center_lng: float = Field(ge=-180.0, le=180.0)
    radius_meters: float = Field(default=500.0, ge=50.0, le=50000.0)
    trigger_on: str = Field(default="ENTER", pattern="^(ENTER|EXIT)$")


@router.post("/{device_id}/tasks/{device_task_id}/report")
def api_report_device_task(
    device_id: str,
    device_task_id: str,
    body: ReportDeviceTaskRequest,
    x_device_token: str = Header(default="", alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> dict:
    device = authenticate_device_token(db, raw_token=x_device_token)
    if device.device_id != device_id:
        raise AuthorizationError("Device token does not match target device_id.")
    return report_device_task_result(
        db,
        device=device,
        device_task_id=device_task_id,
        status_value=body.status,
        result=body.result,
        error_detail=body.error_detail,
    )


@router.post("/{device_id}/location", status_code=status.HTTP_201_CREATED)
def api_report_device_location(
    device_id: str,
    body: ReportLocationRequest,
    x_device_token: str = Header(default="", alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> dict:
    device = authenticate_device_token(db, raw_token=x_device_token)
    if device.device_id != device_id:
        raise AuthorizationError("Device token does not match target device_id.")
    return report_device_location(
        db,
        device=device,
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_meters=body.accuracy_meters,
        city=body.city,
        country=body.country,
        label=body.label,
    )


@router.get("/locations")
def api_list_locations(
    device_id: str | None = None,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_device_locations(db, tenant_id=principal.tenant_id, device_id=device_id)
    return {
        "total": len(items),
        "locations": items,
        "empty_state": None if items else "No authorized device locations recorded yet.",
    }


@router.post("/{device_id}/location/control")
def api_location_control(
    device_id: str,
    body: LocationControlRequest,
    principal: Principal = Depends(require_perm("devices:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return set_location_sharing_state(db, principal=principal, device_id=device_id, action=body.action)


@router.post("/{device_id}/location/alerts", status_code=status.HTTP_201_CREATED)
def api_create_location_alert(
    device_id: str,
    body: CreateLocationAlertRequest,
    principal: Principal = Depends(require_perm("devices:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return create_location_alert(
        db,
        principal=principal,
        device_id=device_id,
        name=body.name,
        center_lat=body.center_lat,
        center_lng=body.center_lng,
        radius_meters=body.radius_meters,
        trigger_on=body.trigger_on,
    )


@router.get("/location/alerts")
def api_list_location_alerts(
    device_id: str | None = None,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_location_alerts(db, tenant_id=principal.tenant_id, device_id=device_id)
    return {"total": len(items), "alerts": items}


# ---------------------------------------------------------------------------
# ORBIT Persistent Device Application Launch Permissions
# ---------------------------------------------------------------------------
class SetAppPermissionRequest(BaseModel):
    app_id: str = Field(min_length=2, max_length=64)
    device_id: str = Field(default="this_device", max_length=64)
    device_label: str = Field(default="This Device", max_length=160)
    decision: str = Field(min_length=4, max_length=24)


class LaunchAppRequest(BaseModel):
    app_id: str = Field(min_length=2, max_length=64)
    device_id: str = Field(default="this_device", max_length=64)
    device_label: str = Field(default="This Device", max_length=160)
    platform: str = Field(default="ios", max_length=32)
    target_uri: str | None = Field(default=None, max_length=500)
    allow_once: bool = False


@router.get("/apps/catalog")
def api_list_orbit_apps(
    _principal: Principal = Depends(require_perm("devices:read")),
) -> dict:
    return {
        "total": len(SUPPORTED_ORBIT_APPS),
        "apps": list(SUPPORTED_ORBIT_APPS.values()),
    }


@router.get("/apps/permissions")
def api_list_app_permissions(
    device_id: str | None = None,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_app_permissions(db, principal=principal, device_id=device_id)
    return {"total": len(items), "permissions": items}


@router.post("/apps/permissions")
def api_set_app_permission(
    body: SetAppPermissionRequest,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    return set_app_permission(
        db,
        principal=principal,
        app_id=body.app_id,
        device_id=body.device_id,
        device_label=body.device_label,
        decision=body.decision,
    )


@router.post("/apps/permissions/{permission_id}/revoke")
def api_revoke_app_permission(
    permission_id: str,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    return revoke_app_permission(db, principal=principal, permission_id=permission_id)


@router.post("/apps/launch")
def api_launch_orbit_app(
    body: LaunchAppRequest,
    principal: Principal = Depends(require_perm("devices:read")),
    db: Session = Depends(get_db),
) -> dict:
    return prepare_or_dispatch_app_launch(
        db,
        principal=principal,
        app_id=body.app_id,
        device_id=body.device_id,
        device_label=body.device_label,
        platform=body.platform,
        target_uri=body.target_uri,
        allow_once=body.allow_once,
    )
