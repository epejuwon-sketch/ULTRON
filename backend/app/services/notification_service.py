"""Tenant-scoped notification center with real-time WebSocket dispatch."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.db.models import NotificationRecord
from app.services.realtime_hub import realtime_hub


def create_notification(
    db: Session,
    *,
    tenant_id: str,
    title: str,
    message: str,
    severity: str = "INFO",
    category: str = "SYSTEM",
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    record = NotificationRecord(
        notification_id=f"ntf_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        user_id=user_id,
        severity=severity.upper(),
        category=category.upper(),
        title=title.strip()[:200],
        message=message.strip(),
        metadata_json=json.dumps(metadata or {}, default=str),
        read=False,
    )
    db.add(record)
    db.flush()
    if commit:
        db.commit()
        db.refresh(record)
    serialized = serialize_notification(record)
    realtime_hub.publish_sync(tenant_id, "notification.created", serialized)
    return serialized


def list_notifications(
    db: Session,
    *,
    principal: Principal,
    unread_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(NotificationRecord).where(
        NotificationRecord.tenant_id == principal.tenant_id,
        (NotificationRecord.user_id.is_(None)) | (NotificationRecord.user_id == principal.user_id),
    )
    if unread_only:
        stmt = stmt.where(NotificationRecord.read.is_(False))
    rows = db.execute(stmt.order_by(NotificationRecord.created_at.desc()).limit(limit)).scalars().all()
    unread_count = db.execute(
        select(func.count())
        .select_from(NotificationRecord)
        .where(
            NotificationRecord.tenant_id == principal.tenant_id,
            NotificationRecord.read.is_(False),
            (NotificationRecord.user_id.is_(None)) | (NotificationRecord.user_id == principal.user_id),
        )
    ).scalar_one()
    return {
        "unread_count": int(unread_count),
        "total": len(rows),
        "notifications": [serialize_notification(r) for r in rows],
    }


def mark_notification_read(db: Session, *, principal: Principal, notification_id: str) -> dict[str, Any]:
    record = db.execute(
        select(NotificationRecord).where(
            NotificationRecord.notification_id == notification_id,
            NotificationRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Notification '{notification_id}' not found.")
    record.read = True
    db.commit()
    db.refresh(record)
    return serialize_notification(record)


def mark_all_read(db: Session, *, principal: Principal) -> int:
    rows = db.execute(
        select(NotificationRecord).where(
            NotificationRecord.tenant_id == principal.tenant_id,
            NotificationRecord.read.is_(False),
            (NotificationRecord.user_id.is_(None)) | (NotificationRecord.user_id == principal.user_id),
        )
    ).scalars().all()
    for r in rows:
        r.read = True
    db.commit()
    return len(rows)


def serialize_notification(r: NotificationRecord) -> dict[str, Any]:
    return {
        "notification_id": r.notification_id,
        "tenant_id": r.tenant_id,
        "user_id": r.user_id,
        "severity": r.severity,
        "category": r.category,
        "title": r.title,
        "message": r.message,
        "metadata": json.loads(r.metadata_json or "{}"),
        "read": r.read,
        "created_at": r.created_at.isoformat(),
    }
