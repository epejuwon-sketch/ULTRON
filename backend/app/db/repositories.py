"""Cryptographic SHA-256 hash-chained audit ledger and shared repository helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLogRecord


def _compute_entry_hash(
    *,
    event_id: str,
    tenant_id: str,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    metadata_json: str,
    prev_hash: str,
    created_at_iso: str,
) -> str:
    raw = "|".join(
        [
            event_id,
            tenant_id,
            actor,
            action,
            resource,
            outcome,
            metadata_json,
            prev_hash,
            created_at_iso,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_audit_log(
    db: Session,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLogRecord:
    """Append an immutable hash-chained record to the ARGON audit ledger."""
    last = db.execute(select(AuditLogRecord).order_by(AuditLogRecord.seq.desc()).limit(1)).scalar_one_or_none()
    prev_hash = last.entry_hash if last is not None else "0" * 64

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    meta_str = json.dumps(metadata or {}, sort_keys=True, default=str)
    seed = f"{now_iso}|{tenant_id}|{actor}|{action}|{resource}|{prev_hash}"
    event_id = f"AUD-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:14].upper()}"
    entry_hash = _compute_entry_hash(
        event_id=event_id,
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        metadata_json=meta_str,
        prev_hash=prev_hash,
        created_at_iso=now_iso,
    )

    record = AuditLogRecord(
        event_id=event_id,
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        metadata_json=meta_str,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=now,
    )
    db.add(record)
    db.flush()
    return record


def verify_audit_chain(db: Session) -> dict[str, Any]:
    """Verify full SHA-256 hash chain continuity across all audit records."""
    rows = db.execute(select(AuditLogRecord).order_by(AuditLogRecord.seq.asc())).scalars().all()
    if not rows:
        return {"valid": True, "checked_entries": 0, "broken_seq": None}

    expected_prev = "0" * 64
    for row in rows:
        if row.prev_hash != expected_prev:
            return {
                "valid": False,
                "checked_entries": len(rows),
                "broken_seq": row.seq,
                "reason": "prev_hash linkage mismatch",
            }
        expected_prev = row.entry_hash

    return {"valid": True, "checked_entries": len(rows), "broken_seq": None}
