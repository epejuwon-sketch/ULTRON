"""Tenant & user notification center routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.notification_service import list_notifications, mark_all_read, mark_notification_read

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("")
def api_list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("notifications:read")),
    db: Session = Depends(get_db),
) -> dict:
    return list_notifications(db, principal=principal, unread_only=unread_only, limit=limit)


@router.post("/{notification_id}/read")
def api_mark_read(
    notification_id: str,
    principal: Principal = Depends(require_perm("notifications:write")),
    db: Session = Depends(get_db),
) -> dict:
    return mark_notification_read(db, principal=principal, notification_id=notification_id)


@router.post("/read-all")
def api_mark_all_read(
    principal: Principal = Depends(require_perm("notifications:write")),
    db: Session = Depends(get_db),
) -> dict:
    count = mark_all_read(db, principal=principal)
    return {"marked_read": count}
