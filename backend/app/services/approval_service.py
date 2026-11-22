"""ARGON ApprovalGate governance workflow service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.db.models import ApprovalRecord, TaskRecord
from app.db.repositories import append_audit_log


def create_approval_request(
    db: Session,
    *,
    tenant_id: str,
    requested_by: str,
    action_type: str,
    reason: str,
    risk_level: str = "HIGH",
    financial_amount_usd: float = 0.0,
    task_id: str | None = None,
    tool_name: str | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> ApprovalRecord:
    """Create a pending ApprovalGate request and record it in the immutable audit ledger."""
    record = ApprovalRecord(
        approval_id=f"apr_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        task_id=task_id,
        tool_name=tool_name,
        requested_by=requested_by,
        action_type=action_type,
        risk_level=risk_level,
        financial_amount_usd=float(financial_amount_usd),
        payload_json=json.dumps(payload or {}, default=str),
        reason=reason,
        status="PENDING",
    )
    db.add(record)
    db.flush()
    append_audit_log(
        db,
        tenant_id=tenant_id,
        actor=requested_by,
        action="APPROVAL_GATE_TRIGGERED",
        resource=record.approval_id,
        outcome=f"PENDING|RISK={risk_level}|USD={financial_amount_usd:.2f}",
        metadata={"task_id": task_id, "tool_name": tool_name, "action_type": action_type},
    )
    if commit:
        db.commit()
        db.refresh(record)
    return record


def list_approvals(
    db: Session,
    *,
    tenant_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(ApprovalRecord).where(ApprovalRecord.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(ApprovalRecord.status == status.upper())
    rows = db.execute(stmt.order_by(ApprovalRecord.created_at.desc()).limit(limit)).scalars().all()
    return [serialize_approval(r) for r in rows]


def get_approval(db: Session, *, tenant_id: str, approval_id: str) -> dict[str, Any]:
    record = db.execute(
        select(ApprovalRecord).where(
            ApprovalRecord.approval_id == approval_id,
            ApprovalRecord.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Approval request '{approval_id}' not found.")
    return serialize_approval(record)


def decide_approval(
    db: Session,
    *,
    principal: Principal,
    approval_id: str,
    decision: str,
    note: str = "",
) -> dict[str, Any]:
    """Approve or reject a pending ApprovalGate request and transition any linked task."""
    normalized = decision.strip().upper()
    if normalized not in {"APPROVED", "REJECTED"}:
        raise ConflictError("Decision must be either 'APPROVED' or 'REJECTED'.")

    record = db.execute(
        select(ApprovalRecord).where(
            ApprovalRecord.approval_id == approval_id,
            ApprovalRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Approval request '{approval_id}' not found.")
    if record.status != "PENDING":
        raise ConflictError(f"Approval request '{approval_id}' is already {record.status}.")

    now = datetime.now(timezone.utc)
    record.status = normalized
    record.decided_by = principal.username
    record.decision_note = note.strip() or None
    record.decided_at = now

    linked_task_state: str | None = None
    if record.task_id:
        task = db.get(TaskRecord, record.task_id)
        if task is not None and task.lifecycle_state == "WAITING_FOR_APPROVAL":
            task.lifecycle_state = "READY" if normalized == "APPROVED" else "CANCELLED"
            task.updated_at = now
            if normalized == "REJECTED":
                task.error_detail = f"Rejected via ApprovalGate ({approval_id}): {note or 'No reason provided'}"
            linked_task_state = task.lifecycle_state

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=f"APPROVAL_GATE_{normalized}",
        resource=record.approval_id,
        outcome=f"TASK_STATE={linked_task_state or 'NONE'}",
        metadata={"note": note, "task_id": record.task_id},
    )
    db.commit()
    db.refresh(record)
    result = serialize_approval(record)
    result["linked_task_state"] = linked_task_state
    return result


def serialize_approval(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "approval_id": record.approval_id,
        "tenant_id": record.tenant_id,
        "task_id": record.task_id,
        "tool_name": record.tool_name,
        "requested_by": record.requested_by,
        "action_type": record.action_type,
        "risk_level": record.risk_level,
        "financial_amount_usd": record.financial_amount_usd,
        "payload": json.loads(record.payload_json or "{}"),
        "reason": record.reason,
        "status": record.status,
        "decided_by": record.decided_by,
        "decision_note": record.decision_note,
        "created_at": record.created_at.isoformat(),
        "decided_at": record.decided_at.isoformat() if record.decided_at else None,
    }
