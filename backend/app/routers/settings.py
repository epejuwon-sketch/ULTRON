"""Tenant system settings and OWNER emergency kill-switch routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import UpdateSettingRequest
from app.services.settings_service import get_system_settings, upsert_system_setting

router = APIRouter(prefix="/api/v1/settings", tags=["System Settings"])


@router.get("")
def api_get_settings(
    principal: Principal = Depends(require_perm("settings:read")),
    db: Session = Depends(get_db),
) -> dict:
    return {"tenant_id": principal.tenant_id, "settings": get_system_settings(db, tenant_id=principal.tenant_id)}


@router.put("")
def api_update_setting(
    body: UpdateSettingRequest,
    principal: Principal = Depends(require_perm("settings:write")),
    db: Session = Depends(get_db),
) -> dict:
    return upsert_system_setting(db, principal=principal, key=body.key, value=body.value)
