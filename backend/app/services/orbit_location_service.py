"""ORBIT Location & Geofence Service — Authorized device location with pause/revoke controls."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import DeviceLocationRecord, DeviceRecord, LocationAlertRecord
from app.db.repositories import append_audit_log
from app.services.notification_service import create_notification


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def report_device_location(
    db: Session,
    *,
    device: DeviceRecord,
    latitude: float,
    longitude: float,
    accuracy_meters: float = 0.0,
    city: str = "",
    country: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Record a device's location strictly when `location` permission is granted and not paused."""
    perms = json.loads(device.permissions_json or "{}")
    if not perms.get("location", False):
        raise AuthorizationError("Location permission is not granted for this device.")
    if perms.get("location_paused", False):
        raise AuthorizationError("Location tracking is currently paused by the user for this device.")
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise ValidationError("Invalid latitude/longitude coordinates.")

    loc = DeviceLocationRecord(
        location_id=f"loc_{uuid.uuid4().hex[:14]}",
        tenant_id=device.tenant_id,
        device_id=device.device_id,
        latitude=round(float(latitude), 6),
        longitude=round(float(longitude), 6),
        accuracy_meters=max(0.0, float(accuracy_meters)),
        city=city.strip()[:120],
        country=country.strip()[:120],
        label=label.strip()[:160],
    )
    db.add(loc)
    db.flush()

    # Evaluate active geofence alerts
    triggered_alerts: list[str] = []
    alerts = db.execute(
        select(LocationAlertRecord).where(
            LocationAlertRecord.tenant_id == device.tenant_id,
            LocationAlertRecord.device_id == device.device_id,
            LocationAlertRecord.active.is_(True),
        )
    ).scalars().all()
    for alert in alerts:
        dist = _haversine_meters(loc.latitude, loc.longitude, alert.center_lat, alert.center_lng)
        matched = (alert.trigger_on == "ENTER" and dist <= alert.radius_meters) or (
            alert.trigger_on == "EXIT" and dist > alert.radius_meters
        )
        if matched:
            alert.last_triggered_at = datetime.now(timezone.utc)
            triggered_alerts.append(alert.alert_id)
            create_notification(
                db,
                tenant_id=device.tenant_id,
                category="ORBIT_LOCATION",
                severity="INFO",
                title=f"Geofence '{alert.name}' triggered ({alert.trigger_on})",
                message=f"Device '{device.name}' matched geofence '{alert.name}' (distance {dist:.0f}m).",
                metadata={"device_id": device.device_id, "alert_id": alert.alert_id, "distance_m": round(dist, 1)},
                commit=False,
            )

    db.commit()
    db.refresh(loc)
    return {
        "location": _serialize_location(loc),
        "triggered_alerts": triggered_alerts,
    }


def list_device_locations(
    db: Session,
    *,
    tenant_id: str,
    device_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(DeviceLocationRecord).where(DeviceLocationRecord.tenant_id == tenant_id)
    if device_id:
        stmt = stmt.where(DeviceLocationRecord.device_id == device_id)
    rows = db.execute(stmt.order_by(DeviceLocationRecord.recorded_at.desc()).limit(limit)).scalars().all()
    return [_serialize_location(r) for r in rows]


def set_location_sharing_state(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
    action: str,  # PAUSE | RESUME | REVOKE
) -> dict[str, Any]:
    """Allow the user to pause, resume, or completely revoke location permission on a device."""
    device = db.execute(
        select(DeviceRecord).where(
            DeviceRecord.device_id == device_id,
            DeviceRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError(f"Device '{device_id}' not found.")

    perms = json.loads(device.permissions_json or "{}")
    act = action.upper()
    if act == "PAUSE":
        perms["location_paused"] = True
    elif act == "RESUME":
        perms["location"] = True
        perms["location_paused"] = False
    elif act == "REVOKE":
        perms["location"] = False
        perms["location_paused"] = True
    else:
        raise ValidationError("action must be PAUSE, RESUME, or REVOKE.")

    device.permissions_json = json.dumps(perms)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=f"ORBIT_LOCATION_{act}",
        resource=device.device_id,
        outcome=json.dumps({"location": perms.get("location"), "paused": perms.get("location_paused")}),
    )
    db.commit()
    return {
        "device_id": device.device_id,
        "location_enabled": bool(perms.get("location", False)),
        "location_paused": bool(perms.get("location_paused", False)),
    }


def create_location_alert(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
    name: str,
    center_lat: float,
    center_lng: float,
    radius_meters: float = 500.0,
    trigger_on: str = "ENTER",
) -> dict[str, Any]:
    device = db.execute(
        select(DeviceRecord).where(
            DeviceRecord.device_id == device_id,
            DeviceRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError(f"Device '{device_id}' not found.")

    alert = LocationAlertRecord(
        alert_id=f"lalt_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        device_id=device.device_id,
        name=name.strip()[:160],
        center_lat=float(center_lat),
        center_lng=float(center_lng),
        radius_meters=max(50.0, float(radius_meters)),
        trigger_on=trigger_on.upper() if trigger_on.upper() in {"ENTER", "EXIT"} else "ENTER",
        active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _serialize_alert(alert)


def list_location_alerts(db: Session, *, tenant_id: str, device_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(LocationAlertRecord).where(LocationAlertRecord.tenant_id == tenant_id)
    if device_id:
        stmt = stmt.where(LocationAlertRecord.device_id == device_id)
    rows = db.execute(stmt.order_by(LocationAlertRecord.created_at.desc())).scalars().all()
    return [_serialize_alert(r) for r in rows]


def _serialize_location(loc: DeviceLocationRecord) -> dict[str, Any]:
    return {
        "location_id": loc.location_id,
        "device_id": loc.device_id,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "accuracy_meters": loc.accuracy_meters,
        "city": loc.city,
        "country": loc.country,
        "label": loc.label,
        "recorded_at": loc.recorded_at.isoformat(),
    }


def _serialize_alert(a: LocationAlertRecord) -> dict[str, Any]:
    return {
        "alert_id": a.alert_id,
        "device_id": a.device_id,
        "name": a.name,
        "center_lat": a.center_lat,
        "center_lng": a.center_lng,
        "radius_meters": a.radius_meters,
        "trigger_on": a.trigger_on,
        "active": a.active,
        "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
        "created_at": a.created_at.isoformat(),
    }
