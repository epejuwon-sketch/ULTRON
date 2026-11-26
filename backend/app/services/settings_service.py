"""Tenant-scoped system settings and OWNER emergency autonomous execution kill switch."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError
from app.core.permissions import Principal, Role
from app.db.models import SystemSettingRecord
from app.db.repositories import append_audit_log

DEFAULT_SYSTEM_SETTINGS: dict[str, Any] = {
    "autonomous_execution_enabled": True,
    "approval_soft_limit_usd": 50.0,
    "memory_retention_days": 90,
    "argon_max_parallel_steps": 4,
    "require_approval_for_external_comms": True,
    "require_approval_for_prod_deploys": True,
}

OWNER_ONLY_KEYS = frozenset({"autonomous_execution_enabled", "approval_soft_limit_usd"})


def get_system_settings(db: Session, *, tenant_id: str) -> dict[str, Any]:
    merged = dict(DEFAULT_SYSTEM_SETTINGS)
    rows = db.execute(
        select(SystemSettingRecord).where(SystemSettingRecord.tenant_id == tenant_id)
    ).scalars().all()
    for row in rows:
        merged[row.setting_key] = json.loads(row.value_json)
    return merged


def upsert_system_setting(
    db: Session,
    *,
    principal: Principal,
    key: str,
    value: Any,
) -> dict[str, Any]:
    clean_key = key.strip()
    if clean_key in OWNER_ONLY_KEYS and principal.role != Role.OWNER:
        raise AuthorizationError(f"Only OWNER may modify critical governance setting '{clean_key}'.")

    existing = db.execute(
        select(SystemSettingRecord).where(
            SystemSettingRecord.tenant_id == principal.tenant_id,
            SystemSettingRecord.setting_key == clean_key,
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    serialized_val = json.dumps(value, default=str)

    if existing is not None:
        existing.value_json = serialized_val
        existing.updated_by = principal.username
        existing.updated_at = now
    else:
        db.add(
            SystemSettingRecord(
                setting_id=f"set_{uuid.uuid4().hex[:16]}",
                tenant_id=principal.tenant_id,
                setting_key=clean_key,
                value_json=serialized_val,
                updated_by=principal.username,
            )
        )

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SYSTEM_SETTING_UPDATED",
        resource=clean_key,
        outcome=serialized_val[:100],
    )
    db.commit()
    return {"key": clean_key, "value": value, "updated_by": principal.username}


def is_autonomous_execution_enabled(db: Session, *, tenant_id: str) -> bool:
    settings_map = get_system_settings(db, tenant_id=tenant_id)
    return bool(settings_map.get("autonomous_execution_enabled", True))
