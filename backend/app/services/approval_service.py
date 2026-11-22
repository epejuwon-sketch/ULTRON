"""ARGON ApprovalGate governance workflow service covering tasks, finance, deployments, comms, and agent extensions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.db.models import (
    AgentRecord,
    ApprovalRecord,
    DeploymentRequest,
    DeviceTaskRecord,
    FinancialTransaction,
    TaskRecord,
)
from app.db.repositories import append_audit_log
from app.services.notification_service import create_notification
from app.services.realtime_hub import realtime_hub


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
    resource_ref: str | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> ApprovalRecord:
    """Create a pending ApprovalGate request, notify tenant operators/owners, and audit."""
    record = ApprovalRecord(
        approval_id=f"apr_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        task_id=task_id,
        tool_name=tool_name,
        resource_ref=resource_ref,
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
        outcome=f"PENDING|TYPE={action_type}|RISK={risk_level}|USD={financial_amount_usd:.2f}",
        metadata={"task_id": task_id, "tool_name": tool_name, "resource_ref": resource_ref},
    )
    create_notification(
        db,
        tenant_id=tenant_id,
        severity="WARNING",
        category="APPROVAL_GATE",
        title=f"Approval Required: {action_type}",
        message=reason,
        metadata={"approval_id": record.approval_id, "risk_level": risk_level, "amount_usd": financial_amount_usd},
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(record)
    realtime_hub.publish_sync(tenant_id, "approval.pending", serialize_approval(record))
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
    """Approve or reject a pending ApprovalGate request and transition any linked entity."""
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
    linked_resource_state: str | None = None

    if record.task_id:
        task = db.get(TaskRecord, record.task_id)
        if task is not None and task.lifecycle_state == "WAITING_FOR_APPROVAL":
            task.lifecycle_state = "READY" if normalized == "APPROVED" else "CANCELLED"
            task.updated_at = now
            if normalized == "REJECTED":
                task.error_detail = f"Rejected via ApprovalGate ({approval_id}): {note or 'No reason provided'}"
            linked_task_state = task.lifecycle_state

    if record.action_type == "FINANCIAL_TRANSACTION" and record.resource_ref:
        tx = db.get(FinancialTransaction, record.resource_ref)
        if tx is not None:
            tx.status = "APPROVED" if normalized == "APPROVED" else "REJECTED"
            linked_resource_state = tx.status

    if record.action_type == "PRODUCTION_DEPLOYMENT" and record.resource_ref:
        dep = db.get(DeploymentRequest, record.resource_ref)
        if dep is not None:
            dep.status = "APPROVED_READY_TO_DEPLOY" if normalized == "APPROVED" else "REJECTED"
            dep.updated_at = now
            linked_resource_state = dep.status

    if record.action_type == "AGENT_EXTENSION_REGISTRATION" and record.resource_ref:
        agent = db.get(AgentRecord, record.resource_ref)
        if agent is not None:
            if normalized == "APPROVED":
                agent.approved = True
                agent.capability_state = "AVAILABLE"
                linked_resource_state = "AVAILABLE"
            else:
                agent.approved = False
                agent.capability_state = "UNAVAILABLE"
                linked_resource_state = "UNAVAILABLE"

    if record.action_type == "DEVICE_SENSITIVE_ACTION" and record.resource_ref:
        dt = db.get(DeviceTaskRecord, record.resource_ref)
        if dt is not None:
            dt.status = "PENDING" if normalized == "APPROVED" else "REJECTED"
            dt.updated_at = now
            linked_resource_state = dt.status

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=f"APPROVAL_GATE_{normalized}",
        resource=record.approval_id,
        outcome=f"TASK_STATE={linked_task_state or 'NONE'}|RES_STATE={linked_resource_state or 'NONE'}",
        metadata={"note": note, "task_id": record.task_id, "resource_ref": record.resource_ref},
    )
    create_notification(
        db,
        tenant_id=principal.tenant_id,
        severity="INFO",
        category="APPROVAL_GATE",
        title=f"Approval {normalized}: {record.action_type}",
        message=f"Decided by {principal.username}. {note or ''}".strip(),
        metadata={"approval_id": record.approval_id, "decision": normalized},
        commit=False,
    )
    db.commit()
    db.refresh(record)
    result = serialize_approval(record)
    result["linked_task_state"] = linked_task_state
    result["linked_resource_state"] = linked_resource_state
    realtime_hub.publish_sync(principal.tenant_id, "approval.decided", result)
    return result


def serialize_approval(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "approval_id": record.approval_id,
        "tenant_id": record.tenant_id,
        "task_id": record.task_id,
        "tool_name": record.tool_name,
        "resource_ref": record.resource_ref,
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
