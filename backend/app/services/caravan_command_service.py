"""CARAVAN Command Centre Aggregation & Operations Service (Zero Fabricated Metrics)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.permissions import Principal, Role
from app.db.models import (
    ApprovalRecord,
    AuditLogRecord,
    CaravanApplicationRecord,
    CaravanCustomerAccountRecord,
    CaravanEligibilityAssessmentRecord,
    CaravanFundingOpportunityRecord,
    CaravanFundingSourceRecord,
    CaravanNotificationRecord,
    CaravanSavedOpportunityRecord,
    CaravanSubscriptionRecord,
    CaravanSupportTicketRecord,
    IntegrationConnectionRecord,
)
from app.db.repositories import append_audit_log
from app.services.caravan_product_service import _compute_freshness_status, _serialize_opportunity, _serialize_source


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def toggle_funding_source_status(
    db: Session,
    *,
    principal: Principal,
    source_id: str,
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable a registered funding source (OWNER/ADMIN only)."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may enable or disable funding sources.")
    src = db.execute(
        select(CaravanFundingSourceRecord).where(
            CaravanFundingSourceRecord.tenant_id == principal.tenant_id,
            CaravanFundingSourceRecord.source_id == source_id,
        )
    ).scalar_one_or_none()
    if src is None:
        raise NotFoundError(f"Funding source '{source_id}' not found.")

    src.status = "ACTIVE" if enabled else "DISABLED"
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_SOURCE_TOGGLED",
        resource=src.source_id,
        outcome=f"status={src.status}",
    )
    db.commit()
    db.refresh(src)
    return _serialize_source(src)


def get_caravan_command_centre(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    days: int = 30,
) -> dict[str, Any]:
    """Aggregate real operational metrics, source health, NEON/ARGON jobs, customer ops, finance, and audit timeline."""
    tid = principal.tenant_id
    cutoff = _utcnow() - timedelta(days=max(1, min(365, days)))

    sources = db.execute(
        select(CaravanFundingSourceRecord)
        .where(CaravanFundingSourceRecord.tenant_id == tid)
        .order_by(CaravanFundingSourceRecord.created_at.desc())
    ).scalars().all()

    opps = db.execute(
        select(CaravanFundingOpportunityRecord)
        .where(CaravanFundingOpportunityRecord.tenant_id == tid)
        .order_by(CaravanFundingOpportunityRecord.updated_at.desc())
    ).scalars().all()

    accounts = db.execute(
        select(CaravanCustomerAccountRecord)
        .where(CaravanCustomerAccountRecord.tenant_id == tid)
        .order_by(CaravanCustomerAccountRecord.updated_at.desc())
    ).scalars().all()

    subs = db.execute(
        select(CaravanSubscriptionRecord).where(CaravanSubscriptionRecord.tenant_id == tid)
    ).scalars().all()
    sub_by_acc = {s.account_id: s for s in subs}

    assessments = db.execute(
        select(CaravanEligibilityAssessmentRecord)
        .where(CaravanEligibilityAssessmentRecord.tenant_id == tid)
        .order_by(CaravanEligibilityAssessmentRecord.created_at.desc())
    ).scalars().all()

    saved = db.execute(
        select(CaravanSavedOpportunityRecord).where(CaravanSavedOpportunityRecord.tenant_id == tid)
    ).scalars().all()

    apps = db.execute(
        select(CaravanApplicationRecord).where(CaravanApplicationRecord.tenant_id == tid)
    ).scalars().all()

    tickets = db.execute(
        select(CaravanSupportTicketRecord)
        .where(CaravanSupportTicketRecord.tenant_id == tid)
        .order_by(CaravanSupportTicketRecord.updated_at.desc())
    ).scalars().all()

    notifs = db.execute(
        select(CaravanNotificationRecord)
        .where(CaravanNotificationRecord.tenant_id == tid)
        .order_by(CaravanNotificationRecord.created_at.desc())
    ).scalars().all()

    audits = db.execute(
        select(AuditLogRecord)
        .where(AuditLogRecord.tenant_id == tid, AuditLogRecord.created_at >= cutoff)
        .order_by(AuditLogRecord.created_at.desc())
        .limit(100)
    ).scalars().all()

    pending_approvals = db.execute(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tid,
            ApprovalRecord.status == "PENDING",
        )
    ).scalars().all()

    payment_conns = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tid,
            IntegrationConnectionRecord.provider.in_(["stripe", "paystack", "flutterwave"]),
            IntegrationConnectionRecord.disconnected_at.is_(None),
        )
    ).scalars().all()

    # Source breakdown
    src_healthy = sum(1 for s in sources if s.status == "ACTIVE")
    src_degraded = sum(1 for s in sources if s.status == "DEGRADED")
    src_disabled = sum(1 for s in sources if s.status == "DISABLED")

    # Opportunity breakdown
    serialized_opps = [_serialize_opportunity(o) for o in opps]
    awaiting_review = [o for o in serialized_opps if o["verification_status"] in {"DISCOVERED", "EXTRACTED", "NEEDS_REVIEW", "UNVERIFIED"}]
    verified_opps = [o for o in serialized_opps if o["verification_status"] == "VERIFIED"]
    rejected_opps = [o for o in serialized_opps if o["verification_status"] == "REJECTED"]
    expired_opps = [o for o in serialized_opps if o["verification_status"] == "EXPIRED" or o["freshness_status"] == "EXPIRED"]
    stale_opps = [o for o in serialized_opps if o["freshness_status"] == "STALE"]

    # Subscription distribution
    sub_dist = {"FREE": 0, "PRO": 0, "INSTITUTIONAL": 0}
    for s in subs:
        sub_dist[s.plan_tier] = sub_dist.get(s.plan_tier, 0) + 1

    # Customer operations summary (non-sensitive)
    ass_by_acc: dict[str, int] = {}
    for a in assessments:
        ass_by_acc[a.account_id] = ass_by_acc.get(a.account_id, 0) + 1
    sav_by_acc: dict[str, int] = {}
    for sv in saved:
        sav_by_acc[sv.account_id] = sav_by_acc.get(sv.account_id, 0) + 1
    app_by_acc: dict[str, int] = {}
    for ap in apps:
        app_by_acc[ap.account_id] = app_by_acc.get(ap.account_id, 0) + 1

    customer_rows = [
        {
            "account_id": acc.account_id,
            "organization_name": acc.organization_name,
            "country": acc.country,
            "sector": acc.sector,
            "stage": acc.stage,
            "onboarding_completed": acc.onboarding_completed,
            "plan_tier": sub_by_acc[acc.account_id].plan_tier if acc.account_id in sub_by_acc else "FREE",
            "assessments_count": ass_by_acc.get(acc.account_id, 0),
            "saved_count": sav_by_acc.get(acc.account_id, 0),
            "applications_count": app_by_acc.get(acc.account_id, 0),
        }
        for acc in accounts
    ]

    # NEON & ARGON monitoring
    neon_modes: dict[str, int] = {}
    neon_verdicts: dict[str, int] = {}
    for a in assessments:
        neon_modes[a.neon_mode] = neon_modes.get(a.neon_mode, 0) + 1
        neon_verdicts[a.verdict] = neon_verdicts.get(a.verdict, 0) + 1

    caravan_audits = [
        {
            "id": log.event_id,
            "timestamp": log.created_at.isoformat(),
            "actor": log.actor,
            "action": log.action,
            "resource": log.resource,
            "outcome": log.outcome,
        }
        for log in audits
        if log.action.startswith("CARAVAN_") or log.action.startswith("APPROVAL_")
    ]

    argon_ingestions = [l for l in caravan_audits if l["action"] == "CARAVAN_ARGON_INGESTION"]
    argon_checks = [l for l in caravan_audits if l["action"] == "CARAVAN_ARGON_SOURCE_CHECK"]
    argon_failed = [l for l in argon_checks if "reachable=False" in (l["outcome"] or "")]

    # Financial read-only status
    live_payment_providers = [p.provider for p in payment_conns if p.status == "AVAILABLE"]
    any_live_sub = any(s.live_payments_enabled for s in subs)

    # Support & Operational alerts
    open_tickets = [t for t in tickets if t.status in {"OPEN", "IN_PROGRESS"}]
    resolved_tickets = [t for t in tickets if t.status in {"RESOLVED", "CLOSED"}]
    unread_notifs = [n for n in notifs if not n.read]

    operational_alerts: list[dict[str, str]] = []
    if src_degraded > 0:
        operational_alerts.append({"severity": "WARN", "message": f"{src_degraded} funding source(s) marked DEGRADED."})
    if len(stale_opps) > 0:
        operational_alerts.append({"severity": "WARN", "message": f"{len(stale_opps)} verified opportunity(s) are STALE (>30 days)."})
    if len(awaiting_review) > 0:
        operational_alerts.append({"severity": "INFO", "message": f"{len(awaiting_review)} opportunity(s) awaiting administrator review."})
    if len(argon_failed) > 0:
        operational_alerts.append({"severity": "WARN", "message": f"{len(argon_failed)} ARGON source probe(s) failed reachability."})

    return {
        "tenant_id": tid,
        "window_days": days,
        "executive_overview": {
            "sources_total": len(sources),
            "sources_healthy": src_healthy,
            "sources_degraded": src_degraded,
            "sources_disabled": src_disabled,
            "opportunities_total": len(serialized_opps),
            "awaiting_review_count": len(awaiting_review),
            "verified_count": len(verified_opps),
            "rejected_count": len(rejected_opps),
            "expired_count": len(expired_opps),
            "stale_count": len(stale_opps),
            "active_customers_count": len(accounts),
            "subscription_distribution": sub_dist,
            "saved_opportunities_count": len(saved),
            "applications_count": len(apps),
            "open_support_tickets_count": len(open_tickets),
            "resolved_support_tickets_count": len(resolved_tickets),
            "neon_assessments_count": len(assessments),
            "argon_ingestions_count": len(argon_ingestions),
            "argon_source_checks_count": len(argon_checks),
        },
        "sources": [_serialize_source(s) for s in sources],
        "verification_queue": awaiting_review[:50],
        "customer_operations": customer_rows,
        "neon_monitoring": {
            "gemini_configured": bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip()),
            "total_assessments": len(assessments),
            "modes": neon_modes,
            "verdicts": neon_verdicts,
        },
        "argon_monitoring": {
            "total_ingestions": len(argon_ingestions),
            "total_source_checks": len(argon_checks),
            "failed_source_checks": len(argon_failed),
            "pending_aegis_approvals": len(pending_approvals),
            "recent_ingestions": argon_ingestions[:15],
            "recent_checks": argon_checks[:15],
        },
        "financial_overview": {
            "payment_integration_status": "CONNECTED" if live_payment_providers else "NOT_CONNECTED",
            "connected_payment_providers": live_payment_providers,
            "live_payments_enabled": any_live_sub,
            "subscription_records_count": len(subs),
            "subscription_distribution": sub_dist,
            "actual_revenue_usd": 0.0,
            "read_only": True,
        },
        "support_and_notifications": {
            "open_tickets": [
                {
                    "ticket_id": t.ticket_id,
                    "subject": t.subject,
                    "category": t.category,
                    "priority": t.priority,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                }
                for t in open_tickets[:20]
            ],
            "resolved_tickets_count": len(resolved_tickets),
            "unread_notifications_count": len(unread_notifs),
            "operational_alerts": operational_alerts,
        },
        "activity_timeline": caravan_audits[:50],
    }
