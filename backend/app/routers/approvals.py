"""ARGON ApprovalGate human-in-the-loop governance endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import DecideApprovalRequest
from app.services.approval_service import decide_approval, get_approval, list_approvals

router = APIRouter(prefix="/api/v1/approvals", tags=["ApprovalGate Governance"])


@router.get("")
def api_list_approvals(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("approvals:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_approvals(db, tenant_id=principal.tenant_id, status=status, limit=limit)
    return {"total": len(items), "approvals": items}


@router.get("/{approval_id}")
def api_get_approval(
    approval_id: str,
    principal: Principal = Depends(require_perm("approvals:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_approval(db, tenant_id=principal.tenant_id, approval_id=approval_id)


@router.post("/{approval_id}/decide")
def api_decide_approval(
    approval_id: str,
    body: DecideApprovalRequest,
    principal: Principal = Depends(require_perm("approvals:decide")),
    db: Session = Depends(get_db),
) -> dict:
    """Approve or reject a pending ApprovalGate request (OWNER/ADMIN only)."""
    return decide_approval(
        db,
        principal=principal,
        approval_id=approval_id,
        decision=body.decision,
        note=body.note,
    )
