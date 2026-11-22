"""EVOLVE — Controlled Self-Development Engine.

Enforces strict lifecycle governance:
IDENTIFIED -> PLANNED -> DEVELOPED -> TESTED -> AEGIS_VERIFIED -> WAITING_FOR_APPROVAL -> PROMOTED | ROLLED_BACK

EVOLVE can NEVER deploy changes to production without passing isolated verification,
AEGIS static security scanning, and explicit OWNER/ADMIN ApprovalGate sign-off.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import ApprovalRecord, EvolutionProposalRecord
from app.db.repositories import append_audit_log
from app.services.aegis_service import scan_code_bundle
from app.services.approval_service import create_approval_request, serialize_approval


def create_proposal(
    db: Session,
    *,
    principal: Principal,
    title: str,
    capability_gap: str,
    target_module: str,
    plan_steps: list[str] | None = None,
) -> dict[str, Any]:
    proposal = EvolutionProposalRecord(
        proposal_id=f"evo_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        title=title.strip()[:240],
        capability_gap=capability_gap.strip(),
        target_module=target_module.strip()[:200],
        plan_json=json.dumps({"steps": plan_steps or ["Design", "Implement in isolation", "Test", "AEGIS verify", "Request approval"]}),
        status="PLANNED" if plan_steps else "IDENTIFIED",
        proposed_by=principal.username,
    )
    db.add(proposal)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="EVOLVE_PROPOSAL_CREATED",
        resource=proposal.proposal_id,
        outcome=proposal.target_module,
    )
    db.commit()
    db.refresh(proposal)
    return _serialize_proposal(proposal)


def verify_and_submit_proposal(
    db: Session,
    *,
    principal: Principal,
    proposal_id: str,
    patch_files: dict[str, str],
    patch_summary: str,
) -> dict[str, Any]:
    """Validate candidate patch in isolation (syntax + AEGIS scan) and submit to ApprovalGate if clean."""
    proposal = _get_proposal(db, principal.tenant_id, proposal_id)
    if not patch_files:
        raise ValidationError("patch_files must contain at least one file to verify.")

    aegis_result = scan_code_bundle(patch_files)
    proposal.patch_summary = patch_summary.strip()
    proposal.test_results_json = json.dumps(
        {
            "isolated_syntax_checks": aegis_result["syntax_checks"],
            "aegis_passed": aegis_result["passed"],
            "findings": aegis_result["findings"],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        },
        default=str,
    )

    if not aegis_result["passed"]:
        proposal.status = "DEVELOPED"
        proposal.updated_at = datetime.now(timezone.utc)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="EVOLVE_AEGIS_BLOCKED",
            resource=proposal.proposal_id,
            outcome=f"findings={aegis_result['findings_count']}",
        )
        db.commit()
        return {
            "proposal": _serialize_proposal(proposal),
            "aegis_verification": aegis_result,
            "submitted_for_approval": False,
            "message": "AEGIS blocked submission due to critical/high findings.",
        }

    approval = create_approval_request(
        db,
        tenant_id=principal.tenant_id,
        requested_by=principal.username,
        action_type="EVOLVE_PROMOTION",
        reason=f"Promote verified EVOLVE proposal '{proposal.title}' targeting '{proposal.target_module}'.",
        risk_level="HIGH",
        resource_ref=proposal.proposal_id,
        payload={
            "proposal_id": proposal.proposal_id,
            "target_module": proposal.target_module,
            "files": sorted(patch_files.keys()),
        },
        commit=False,
    )
    proposal.status = "WAITING_FOR_APPROVAL"
    proposal.approval_id = approval.approval_id
    proposal.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="EVOLVE_APPROVAL_REQUESTED",
        resource=proposal.proposal_id,
        outcome=approval.approval_id,
    )
    db.commit()
    return {
        "proposal": _serialize_proposal(proposal),
        "aegis_verification": aegis_result,
        "submitted_for_approval": True,
        "approval": serialize_approval(approval),
    }


def promote_proposal(db: Session, *, principal: Principal, proposal_id: str) -> dict[str, Any]:
    """Mark an EVOLVE proposal PROMOTED only after its ApprovalGate request is APPROVED."""
    proposal = _get_proposal(db, principal.tenant_id, proposal_id)
    if not proposal.approval_id:
        raise ConflictError("EVOLVE proposal has not passed AEGIS verification and ApprovalGate submission.")
    approval = db.get(ApprovalRecord, proposal.approval_id)
    if approval is None or approval.status != "APPROVED":
        raise ConflictError("ApprovalGate sign-off is required before promoting an EVOLVE proposal.")

    proposal.status = "PROMOTED"
    proposal.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="EVOLVE_PROPOSAL_PROMOTED",
        resource=proposal.proposal_id,
        outcome=proposal.target_module,
    )
    db.commit()
    return _serialize_proposal(proposal)


def rollback_proposal(db: Session, *, principal: Principal, proposal_id: str, reason: str) -> dict[str, Any]:
    proposal = _get_proposal(db, principal.tenant_id, proposal_id)
    proposal.status = "ROLLED_BACK"
    proposal.rollback_reason = reason.strip()
    proposal.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="EVOLVE_PROPOSAL_ROLLED_BACK",
        resource=proposal.proposal_id,
        outcome=reason[:120],
    )
    db.commit()
    return _serialize_proposal(proposal)


def list_proposals(db: Session, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvolutionProposalRecord)
        .where(EvolutionProposalRecord.tenant_id == tenant_id)
        .order_by(EvolutionProposalRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_serialize_proposal(r) for r in rows]


def _get_proposal(db: Session, tenant_id: str, proposal_id: str) -> EvolutionProposalRecord:
    rec = db.execute(
        select(EvolutionProposalRecord).where(
            EvolutionProposalRecord.proposal_id == proposal_id,
            EvolutionProposalRecord.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"EVOLVE proposal '{proposal_id}' not found.")
    return rec


def _serialize_proposal(p: EvolutionProposalRecord) -> dict[str, Any]:
    return {
        "proposal_id": p.proposal_id,
        "title": p.title,
        "capability_gap": p.capability_gap,
        "target_module": p.target_module,
        "plan": json.loads(p.plan_json or "{}"),
        "patch_summary": p.patch_summary,
        "status": p.status,
        "test_results": json.loads(p.test_results_json or "{}"),
        "approval_id": p.approval_id,
        "rollback_reason": p.rollback_reason,
        "proposed_by": p.proposed_by,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
