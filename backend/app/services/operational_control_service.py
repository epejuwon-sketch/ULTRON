"""ULTRON x CARAVAN Operational Control Policy & Owner Approval Enforcement."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.core.permissions import Principal
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.settings_service import get_system_settings

AUTONOMOUS_PERMITTED_ACTIONS = frozenset({
    "RESEARCH",
    "ANALYSIS",
    "TESTING",
    "INTERNAL_REPORTING",
    "APPROVED_DEVELOPMENT",
})

OWNER_APPROVAL_REQUIRED_ACTIONS = frozenset({
    "SPEND_MONEY",
    "PAYMENT_OR_TRANSFER",
    "EXTERNAL_OUTREACH",
    "PUBLISH_CAMPAIGN",
    "CONTRACTUAL_COMMITMENT",
    "PRODUCTION_CHANGE",
})


def get_operational_control_policy(db: Session, *, tenant_id: str) -> dict[str, Any]:
    cfg = get_system_settings(db, tenant_id=tenant_id)
    return {
        "tenant_id": tenant_id,
        "autonomous_execution_enabled": bool(cfg.get("autonomous_execution_enabled", True)),
        "autonomous_permitted_actions": sorted(AUTONOMOUS_PERMITTED_ACTIONS),
        "owner_approval_required_actions": sorted(OWNER_APPROVAL_REQUIRED_ACTIONS),
        "require_approval_for_external_comms": bool(cfg.get("require_approval_for_external_comms", True)),
        "require_approval_for_prod_deploys": bool(cfg.get("require_approval_for_prod_deploys", True)),
        "approval_soft_limit_usd": float(cfg.get("approval_soft_limit_usd", 50.0)),
    }


def evaluate_operational_action(
    db: Session,
    *,
    principal: Principal,
    action_category: str,
    summary: str,
    venture: str = "CARAVAN",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cat = action_category.strip().upper()
    if cat not in AUTONOMOUS_PERMITTED_ACTIONS and cat not in OWNER_APPROVAL_REQUIRED_ACTIONS:
        raise ValidationError(f"Unknown operational action_category '{action_category}'.")

    cfg = get_system_settings(db, tenant_id=principal.tenant_id)
    if not bool(cfg.get("autonomous_execution_enabled", True)):
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="OPERATIONAL_CONTROL_HALTED",
            resource=f"{venture}:{cat}",
            outcome="KILL_SWITCH_ACTIVE",
        )
        db.commit()
        raise ConflictError("Autonomous execution is halted by OWNER emergency kill switch (autonomous_execution_enabled=false).")

    if cat in AUTONOMOUS_PERMITTED_ACTIONS:
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="OPERATIONAL_ACTION_AUTHORIZED",
            resource=f"{venture}:{cat}",
            outcome="AUTONOMOUS_PERMITTED",
        )
        db.commit()
        return {
            "authorized": True,
            "requires_owner_approval": False,
            "action_category": cat,
            "venture": venture,
            "approval": None,
        }

    approval = create_approval_request(
        db,
        tenant_id=principal.tenant_id,
        requested_by=principal.username,
        action_type=f"OP_CTRL_{cat}",
        reason=f"[{venture}] Owner approval required for {cat}: {summary.strip()[:240]}",
        payload={"venture": venture, "action_category": cat, **(payload or {})},
        commit=False,
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="OPERATIONAL_CONTROL_GATE",
        resource=f"{venture}:{cat}",
        outcome=f"APPROVAL_REQUIRED|{approval.approval_id}",
    )
    db.commit()
    return {
        "authorized": False,
        "requires_owner_approval": True,
        "action_category": cat,
        "venture": venture,
        "approval": serialize_approval(approval),
    }
