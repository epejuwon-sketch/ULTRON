"""Immutable SHA-256 hash-chained audit ledger query and integrity verification endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.models import AuditLogRecord
from app.db.repositories import verify_audit_chain
from app.db.session import get_db
from app.routers.deps import require_perm

router = APIRouter(prefix="/api/v1/audit", tags=["Audit Ledger"])


@router.get("/logs")
def api_list_audit_logs(
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_perm("audit:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(AuditLogRecord).where(AuditLogRecord.tenant_id == principal.tenant_id)
    if action:
        stmt = stmt.where(AuditLogRecord.action == action.upper())
    rows = db.execute(stmt.order_by(AuditLogRecord.seq.desc()).limit(limit)).scalars().all()
    return {
        "total": len(rows),
        "logs": [
            {
                "seq": r.seq,
                "event_id": r.event_id,
                "tenant_id": r.tenant_id,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "outcome": r.outcome,
                "metadata": json.loads(r.metadata_json or "{}"),
                "prev_hash": r.prev_hash,
                "entry_hash": r.entry_hash,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/verify")
def api_verify_audit_chain(
    _principal: Principal = Depends(require_perm("audit:read")),
    db: Session = Depends(get_db),
) -> dict:
    """Verify unbroken SHA-256 hash chain linkage across the audit ledger."""
    return verify_audit_chain(db)
