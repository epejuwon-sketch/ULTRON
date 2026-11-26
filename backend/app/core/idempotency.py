"""Database-backed Idempotency-Key support preventing duplicate mutation side effects."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.models import IdempotencyRecord


def compute_request_hash(method: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(f"{method.upper()}:{path}:".encode("utf-8"))
    h.update(body or b"")
    return h.hexdigest()


def lookup_idempotency(
    db: Session,
    *,
    key: str,
    tenant_id: str,
    request_hash: str,
) -> dict[str, Any] | None:
    """Return cached response dict if key exists and matches payload, or raise ConflictError on mismatch."""
    record = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    exp = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if now >= exp:
        db.delete(record)
        db.commit()
        return None

    if record.request_hash != request_hash:
        raise ConflictError(
            "Idempotency-Key was already used with a different request payload.",
            details={"idempotency_key": key},
        )
    return {
        "status_code": record.status_code,
        "body": json.loads(record.response_json or "{}"),
    }


def save_idempotency(
    db: Session,
    *,
    key: str,
    tenant_id: str,
    request_hash: str,
    status_code: int,
    response_body: Any,
    ttl_hours: int = 24,
) -> None:
    """Persist an idempotency response snapshot for replay safety."""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    record = IdempotencyRecord(
        idempotency_key=key,
        tenant_id=tenant_id,
        request_hash=request_hash,
        status_code=status_code,
        response_json=json.dumps(response_body, default=str),
        expires_at=expires_at,
    )
    db.merge(record)
    db.commit()
