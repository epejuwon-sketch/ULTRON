"""EVOLVE Controlled Self-Development API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.evolve_service import (
    create_proposal,
    list_proposals,
    promote_proposal,
    rollback_proposal,
    verify_and_submit_proposal,
)

router = APIRouter(prefix="/api/v1/evolve", tags=["EVOLVE Self-Development"])


class CreateProposalRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    capability_gap: str = Field(min_length=5, max_length=2000)
    target_module: str = Field(min_length=2, max_length=200)
    plan_steps: list[str] | None = None


class VerifyProposalRequest(BaseModel):
    patch_files: dict[str, str]
    patch_summary: str = Field(min_length=3, max_length=2000)


class RollbackProposalRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/proposals")
def api_list_proposals(
    principal: Principal = Depends(require_perm("evolve:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_proposals(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "proposals": items}


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
def api_create_proposal(
    body: CreateProposalRequest,
    principal: Principal = Depends(require_perm("evolve:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return create_proposal(
        db,
        principal=principal,
        title=body.title,
        capability_gap=body.capability_gap,
        target_module=body.target_module,
        plan_steps=body.plan_steps,
    )


@router.post("/proposals/{proposal_id}/verify")
def api_verify_proposal(
    proposal_id: str,
    body: VerifyProposalRequest,
    principal: Principal = Depends(require_perm("evolve:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return verify_and_submit_proposal(
        db,
        principal=principal,
        proposal_id=proposal_id,
        patch_files=body.patch_files,
        patch_summary=body.patch_summary,
    )


@router.post("/proposals/{proposal_id}/promote")
def api_promote_proposal(
    proposal_id: str,
    principal: Principal = Depends(require_perm("evolve:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return promote_proposal(db, principal=principal, proposal_id=proposal_id)


@router.post("/proposals/{proposal_id}/rollback")
def api_rollback_proposal(
    proposal_id: str,
    body: RollbackProposalRequest,
    principal: Principal = Depends(require_perm("evolve:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return rollback_proposal(db, principal=principal, proposal_id=proposal_id, reason=body.reason)
