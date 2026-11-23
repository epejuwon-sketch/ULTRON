"""CARAVAN First-Party Product Service — Funding Discovery, Verification, NEON Eligibility, Applications & Governance."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, SecurityViolationError, ValidationError
from app.core.permissions import Principal
from app.db.models import (
    CaravanApplicationRecord,
    CaravanCustomerAccountRecord,
    CaravanEligibilityAssessmentRecord,
    CaravanFundingOpportunityRecord,
    CaravanFundingSourceRecord,
    CaravanNotificationRecord,
    CaravanSavedOpportunityRecord,
    CaravanSubscriptionRecord,
    CaravanSupportTicketRecord,
    UniversalConnectorRecord,
)
from app.db.repositories import append_audit_log
from app.services.operational_control_service import evaluate_operational_action
from app.services.platform_modules_service import get_caravan_analytics_summary
from app.services.universal_connections_service import validate_public_https_url

VALID_FUNDING_TYPES = frozenset({
    "GRANT",
    "LOAN",
    "SCHOLARSHIP",
    "ACCELERATOR",
    "COMPETITION",
    "INVESTMENT",
    "OTHER",
})

VALID_VERIFICATION_STATUSES = frozenset({"VERIFIED", "UNVERIFIED", "EXPIRED", "CLOSED"})

VALID_APPLICATION_STATUSES = frozenset({
    "DRAFT",
    "PREPARING",
    "AWAITING_APPROVAL",
    "SUBMITTED",
    "UNDER_REVIEW",
    "AWARDED",
    "REJECTED",
    "WITHDRAWN",
})

PLAN_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    "FREE": {
        "max_saved_opportunities": 10,
        "neon_assessments_per_month": 5,
        "argon_research_runs": 1,
        "live_payments_enabled": False,
    },
    "PRO": {
        "max_saved_opportunities": 100,
        "neon_assessments_per_month": 50,
        "argon_research_runs": 15,
        "live_payments_enabled": False,
    },
    "INSTITUTIONAL": {
        "max_saved_opportunities": 1000,
        "neon_assessments_per_month": 500,
        "argon_research_runs": 100,
        "live_payments_enabled": False,
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_customer_account(db: Session, *, principal: Principal) -> CaravanCustomerAccountRecord:
    acc = db.execute(
        select(CaravanCustomerAccountRecord).where(
            CaravanCustomerAccountRecord.tenant_id == principal.tenant_id,
            CaravanCustomerAccountRecord.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if acc is None:
        acc = CaravanCustomerAccountRecord(
            account_id=f"cacc_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            organization_name=f"{principal.username} Organization",
            entity_type="STARTUP",
            country="Nigeria",
            sector="Technology",
            stage="SEED",
            annual_revenue_band="PRE_REVENUE",
            profile_summary="",
            onboarding_completed=False,
        )
        db.add(acc)
        db.flush()
    return acc


def _get_or_create_subscription(db: Session, *, tenant_id: str, account_id: str) -> CaravanSubscriptionRecord:
    sub = db.execute(
        select(CaravanSubscriptionRecord).where(
            CaravanSubscriptionRecord.tenant_id == tenant_id,
            CaravanSubscriptionRecord.account_id == account_id,
        )
    ).scalar_one_or_none()
    if sub is None:
        sub = CaravanSubscriptionRecord(
            subscription_id=f"csub_{uuid.uuid4().hex[:14]}",
            tenant_id=tenant_id,
            account_id=account_id,
            plan_tier="FREE",
            status="ACTIVE",
            live_payments_enabled=False,
            entitlements_json=json.dumps(PLAN_ENTITLEMENTS["FREE"]),
        )
        db.add(sub)
        db.flush()
    return sub


def _push_notification(
    db: Session,
    *,
    tenant_id: str,
    account_id: str,
    title: str,
    body: str,
    category: str = "OPPORTUNITY",
) -> None:
    db.add(
        CaravanNotificationRecord(
            notification_id=f"cnot_{uuid.uuid4().hex[:14]}",
            tenant_id=tenant_id,
            account_id=account_id,
            title=title[:180],
            body=body,
            category=category[:32],
            read=False,
        )
    )


def get_caravan_overview(db: Session, *, principal: Principal) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    sub = _get_or_create_subscription(db, tenant_id=principal.tenant_id, account_id=acc.account_id)

    opps = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == principal.tenant_id
        )
    ).scalars().all()

    status_counts = {"VERIFIED": 0, "UNVERIFIED": 0, "EXPIRED": 0, "CLOSED": 0}
    for o in opps:
        status_counts[o.verification_status] = status_counts.get(o.verification_status, 0) + 1

    app_count = db.execute(
        select(func.count(CaravanApplicationRecord.application_id)).where(
            CaravanApplicationRecord.tenant_id == principal.tenant_id,
            CaravanApplicationRecord.account_id == acc.account_id,
        )
    ).scalar_one()

    saved_count = db.execute(
        select(func.count(CaravanSavedOpportunityRecord.saved_id)).where(
            CaravanSavedOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanSavedOpportunityRecord.account_id == acc.account_id,
        )
    ).scalar_one()

    unread_notifs = db.execute(
        select(func.count(CaravanNotificationRecord.notification_id)).where(
            CaravanNotificationRecord.tenant_id == principal.tenant_id,
            CaravanNotificationRecord.account_id == acc.account_id,
            CaravanNotificationRecord.read.is_(False),
        )
    ).scalar_one()

    analytics = get_caravan_analytics_summary(db, tenant_id=principal.tenant_id, venture="CARAVAN")
    db.commit()

    return {
        "product": "CARAVAN",
        "account": _serialize_account(acc),
        "subscription": _serialize_subscription(sub),
        "opportunities_total": len(opps),
        "verification_breakdown": status_counts,
        "my_applications_count": int(app_count or 0),
        "saved_opportunities_count": int(saved_count or 0),
        "unread_notifications_count": int(unread_notifs or 0),
        "analytics": analytics,
        "governance": {
            "live_payments_enabled": False,
            "external_outreach_requires_approval": True,
            "zero_fabricated_opportunities": True,
        },
    }


def register_funding_source(
    db: Session,
    *,
    principal: Principal,
    name: str,
    source_type: str,
    base_url: str,
    connector_id: str | None = None,
    verification_policy: str = "MANUAL_REVIEW",
) -> dict[str, Any]:
    clean_url = validate_public_https_url(base_url, require_https=False)
    if connector_id:
        conn = db.execute(
            select(UniversalConnectorRecord).where(
                UniversalConnectorRecord.tenant_id == principal.tenant_id,
                UniversalConnectorRecord.connector_id == connector_id,
            )
        ).scalar_one_or_none()
        if conn is None:
            raise NotFoundError(f"Connector '{connector_id}' not found in Connections Centre.")

    rec = CaravanFundingSourceRecord(
        source_id=f"csrc_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        name=name.strip(),
        source_type=(source_type or "PUBLIC_PORTAL").strip().upper(),
        base_url=clean_url,
        connector_id=connector_id,
        verification_policy=verification_policy.strip().upper(),
        status="ACTIVE",
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_SOURCE_REGISTERED",
        resource=rec.source_id,
        outcome=rec.name,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_source(rec)


def list_funding_sources(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CaravanFundingSourceRecord)
        .where(CaravanFundingSourceRecord.tenant_id == tenant_id)
        .order_by(CaravanFundingSourceRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_source(r) for r in rows]


def create_funding_opportunity(
    db: Session,
    *,
    principal: Principal,
    title: str,
    provider_org: str,
    funding_type: str,
    source_url: str,
    eligibility_requirements: str,
    geographic_restrictions: str = "Global / See source",
    amount_display: str = "Not specified by source",
    currency: str = "USD",
    deadline_at: datetime | None = None,
    supporting_evidence: str = "",
    source_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    ftype = (funding_type or "GRANT").strip().upper()
    if ftype not in VALID_FUNDING_TYPES:
        raise ValidationError(f"Unsupported funding_type '{ftype}'.")
    clean_url = validate_public_https_url(source_url, require_https=False)
    if not clean_url:
        raise ValidationError("Every funding opportunity requires a valid source_url.")

    rec = CaravanFundingOpportunityRecord(
        opportunity_id=f"copp_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        source_id=source_id,
        title=title.strip(),
        provider_org=provider_org.strip(),
        funding_type=ftype,
        source_url=clean_url,
        amount_display=(amount_display or "Not specified by source").strip(),
        currency=(currency or "USD").strip().upper()[:16],
        eligibility_requirements=eligibility_requirements.strip(),
        geographic_restrictions=(geographic_restrictions or "Global / See source").strip(),
        deadline_at=deadline_at,
        verification_status="UNVERIFIED",
        supporting_evidence=(supporting_evidence or "").strip(),
        tags_json=json.dumps([t.strip() for t in (tags or []) if t.strip()]),
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_OPPORTUNITY_CREATED",
        resource=rec.opportunity_id,
        outcome=f"type={ftype}|status=UNVERIFIED",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_opportunity(rec)


def verify_funding_opportunity(
    db: Session,
    *,
    principal: Principal,
    opportunity_id: str,
    verification_status: str,
    supporting_evidence: str,
) -> dict[str, Any]:
    vstatus = (verification_status or "").strip().upper()
    if vstatus not in VALID_VERIFICATION_STATUSES:
        raise ValidationError(f"Invalid verification_status '{vstatus}'.")
    if vstatus == "VERIFIED" and not (supporting_evidence or "").strip():
        raise ValidationError("Supporting evidence is required to mark an opportunity VERIFIED.")

    rec = _get_opportunity(db, tenant_id=principal.tenant_id, opportunity_id=opportunity_id)
    now = _utcnow()
    rec.verification_status = vstatus
    rec.supporting_evidence = supporting_evidence.strip()
    rec.last_verified_at = now
    rec.verified_by = principal.username
    rec.updated_at = now

    acc = _get_or_create_customer_account(db, principal=principal)
    if vstatus == "VERIFIED":
        _push_notification(
            db,
            tenant_id=principal.tenant_id,
            account_id=acc.account_id,
            title=f"Verified Funding: {rec.title}",
            body=f"{rec.provider_org} ({rec.funding_type}) was verified against {rec.source_url}.",
            category="VERIFICATION",
        )

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_OPPORTUNITY_VERIFIED",
        resource=rec.opportunity_id,
        outcome=f"status={vstatus}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_opportunity(rec)


def list_funding_opportunities(
    db: Session,
    *,
    tenant_id: str,
    query: str = "",
    funding_type: str = "",
    verification_status: str = "",
) -> list[dict[str, Any]]:
    stmt = select(CaravanFundingOpportunityRecord).where(CaravanFundingOpportunityRecord.tenant_id == tenant_id)
    if funding_type.strip():
        stmt = stmt.where(CaravanFundingOpportunityRecord.funding_type == funding_type.strip().upper())
    if verification_status.strip():
        stmt = stmt.where(CaravanFundingOpportunityRecord.verification_status == verification_status.strip().upper())
    rows = db.execute(stmt.order_by(CaravanFundingOpportunityRecord.updated_at.desc())).scalars().all()
    q = query.strip().lower()
    if q:
        rows = [
            r
            for r in rows
            if q in r.title.lower()
            or q in r.provider_org.lower()
            or q in r.eligibility_requirements.lower()
            or q in r.geographic_restrictions.lower()
        ]
    return [_serialize_opportunity(r) for r in rows]


def get_funding_opportunity(db: Session, *, tenant_id: str, opportunity_id: str) -> dict[str, Any]:
    return _serialize_opportunity(_get_opportunity(db, tenant_id=tenant_id, opportunity_id=opportunity_id))


def run_neon_eligibility_assessment(
    db: Session,
    *,
    principal: Principal,
    opportunity_id: str,
    settings: Settings,
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    opp = _get_opportunity(db, tenant_id=principal.tenant_id, opportunity_id=opportunity_id)

    req_lower = opp.eligibility_requirements.lower()
    geo_lower = opp.geographic_restrictions.lower()
    matched: list[str] = []
    gaps: list[str] = []
    recs: list[str] = []

    if acc.country.lower() in geo_lower or "global" in geo_lower or "africa" in geo_lower or "worldwide" in geo_lower:
        matched.append(f"Geographic match: {acc.country} aligns with '{opp.geographic_restrictions}'.")
    else:
        gaps.append(f"Geographic check needed: profile country '{acc.country}' vs '{opp.geographic_restrictions}'.")

    if acc.sector.lower() in req_lower or acc.entity_type.lower() in req_lower or acc.stage.lower() in req_lower:
        matched.append(f"Profile alignment: {acc.entity_type}/{acc.sector}/{acc.stage} referenced in requirements.")
    else:
        recs.append("Ensure pitch narrative explicitly addresses the provider's sector and stage criteria.")

    if opp.verification_status == "VERIFIED":
        matched.append(f"Source verified at {opp.last_verified_at.isoformat() if opp.last_verified_at else 'recorded'}.")
    elif opp.verification_status in {"EXPIRED", "CLOSED"}:
        gaps.append(f"Opportunity status is {opp.verification_status}; do not submit without confirming reopening.")
    else:
        gaps.append("Opportunity is UNVERIFIED; verify source URL before committing application effort.")

    score = max(15, min(95, 45 + len(matched) * 20 - len(gaps) * 15))
    if opp.verification_status in {"EXPIRED", "CLOSED"}:
        verdict = "INELIGIBLE"
        score = min(score, 25)
    elif score >= 75:
        verdict = "ELIGIBLE"
    elif score >= 45:
        verdict = "PARTIAL_MATCH"
    else:
        verdict = "INSUFFICIENT_DATA"

    neon_mode = "GEMINI_LIVE" if (settings.gemini_api_key and settings.gemini_api_key.get_secret_value()) else "DETERMINISTIC"
    assessment = CaravanEligibilityAssessmentRecord(
        assessment_id=f"cass_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        account_id=acc.account_id,
        opportunity_id=opp.opportunity_id,
        score=score,
        verdict=verdict,
        matched_criteria_json=json.dumps(matched),
        gaps_json=json.dumps(gaps),
        recommendations_json=json.dumps(recs or ["Review full official guidelines at the source URL."]),
        neon_mode=neon_mode,
        assessed_by=principal.username,
    )
    db.add(assessment)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_ELIGIBILITY_ASSESSED",
        resource=opp.opportunity_id,
        outcome=f"verdict={verdict}|score={score}|mode={neon_mode}",
    )
    db.commit()
    db.refresh(assessment)
    return _serialize_assessment(assessment)


def list_eligibility_assessments(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rows = db.execute(
        select(CaravanEligibilityAssessmentRecord)
        .where(
            CaravanEligibilityAssessmentRecord.tenant_id == principal.tenant_id,
            CaravanEligibilityAssessmentRecord.account_id == acc.account_id,
        )
        .order_by(CaravanEligibilityAssessmentRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_assessment(r) for r in rows]


def get_personalized_recommendations(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    opps = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanFundingOpportunityRecord.verification_status.in_(["VERIFIED", "UNVERIFIED"]),
        )
    ).scalars().all()
    ranked: list[tuple[int, CaravanFundingOpportunityRecord]] = []
    for o in opps:
        score = 20 if o.verification_status == "VERIFIED" else 5
        if acc.country.lower() in o.geographic_restrictions.lower() or "global" in o.geographic_restrictions.lower():
            score += 30
        if acc.sector.lower() in o.eligibility_requirements.lower():
            score += 25
        if acc.stage.lower() in o.eligibility_requirements.lower():
            score += 15
        ranked.append((score, o))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [{**_serialize_opportunity(o), "match_score": s} for s, o in ranked[:20]]


def create_application(
    db: Session,
    *,
    principal: Principal,
    opportunity_id: str,
    notes: str = "",
    checklist: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    opp = _get_opportunity(db, tenant_id=principal.tenant_id, opportunity_id=opportunity_id)
    if opp.verification_status in {"EXPIRED", "CLOSED"}:
        raise ConflictError(f"Cannot start an application for an {opp.verification_status} opportunity.")

    default_checklist = checklist or [
        {"item": "Confirm eligibility against official source URL", "done": False},
        {"item": "Prepare organization profile & narrative", "done": False},
        {"item": "Attach supporting documents", "done": False},
    ]
    rec = CaravanApplicationRecord(
        application_id=f"capp_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        account_id=acc.account_id,
        opportunity_id=opp.opportunity_id,
        status="DRAFT",
        progress_pct=15,
        checklist_json=json.dumps(default_checklist),
        notes=notes.strip(),
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_APPLICATION_CREATED",
        resource=rec.application_id,
        outcome=opp.opportunity_id,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_application(rec)


def update_application(
    db: Session,
    *,
    principal: Principal,
    application_id: str,
    status_value: str | None = None,
    progress_pct: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    rec = db.execute(
        select(CaravanApplicationRecord).where(
            CaravanApplicationRecord.tenant_id == principal.tenant_id,
            CaravanApplicationRecord.application_id == application_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Application '{application_id}' not found.")

    if status_value:
        next_status = status_value.strip().upper()
        if next_status not in VALID_APPLICATION_STATUSES:
            raise ValidationError(f"Invalid application status '{next_status}'.")
        if next_status == "SUBMITTED":
            # External commitment routed through AEGIS Operational Control
            gate = evaluate_operational_action(
                db,
                principal=principal,
                action_category="CONTRACTUAL_COMMITMENT",
                summary=f"Submit Caravan application {rec.application_id} for opportunity {rec.opportunity_id}",
                venture="CARAVAN",
                payload={"application_id": rec.application_id, "opportunity_id": rec.opportunity_id},
            )
            if gate.get("status") != "APPROVED":
                rec.status = "AWAITING_APPROVAL"
                rec.approval_id = gate.get("approval_id")
            else:
                rec.status = "SUBMITTED"
                rec.submitted_at = _utcnow()
        else:
            rec.status = next_status

    if progress_pct is not None:
        rec.progress_pct = max(0, min(100, progress_pct))
    if notes is not None:
        rec.notes = notes.strip()
    rec.updated_at = _utcnow()

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_APPLICATION_UPDATED",
        resource=rec.application_id,
        outcome=f"status={rec.status}|progress={rec.progress_pct}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_application(rec)


def list_applications(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rows = db.execute(
        select(CaravanApplicationRecord)
        .where(
            CaravanApplicationRecord.tenant_id == principal.tenant_id,
            CaravanApplicationRecord.account_id == acc.account_id,
        )
        .order_by(CaravanApplicationRecord.updated_at.desc())
    ).scalars().all()
    return [_serialize_application(r) for r in rows]


def save_opportunity(db: Session, *, principal: Principal, opportunity_id: str, notes: str = "") -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    _get_opportunity(db, tenant_id=principal.tenant_id, opportunity_id=opportunity_id)
    existing = db.execute(
        select(CaravanSavedOpportunityRecord).where(
            CaravanSavedOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanSavedOpportunityRecord.account_id == acc.account_id,
            CaravanSavedOpportunityRecord.opportunity_id == opportunity_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _serialize_saved(existing)

    rec = CaravanSavedOpportunityRecord(
        saved_id=f"csav_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        account_id=acc.account_id,
        opportunity_id=opportunity_id,
        notes=notes.strip(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _serialize_saved(rec)


def list_saved_opportunities(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rows = db.execute(
        select(CaravanSavedOpportunityRecord)
        .where(
            CaravanSavedOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanSavedOpportunityRecord.account_id == acc.account_id,
        )
        .order_by(CaravanSavedOpportunityRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_saved(r) for r in rows]


def remove_saved_opportunity(db: Session, *, principal: Principal, saved_id: str) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanSavedOpportunityRecord).where(
            CaravanSavedOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanSavedOpportunityRecord.account_id == acc.account_id,
            CaravanSavedOpportunityRecord.saved_id == saved_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Saved opportunity '{saved_id}' not found.")
    db.delete(rec)
    db.commit()
    return {"deleted": True, "saved_id": saved_id}


def update_customer_account(
    db: Session,
    *,
    principal: Principal,
    organization_name: str | None = None,
    entity_type: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    stage: str | None = None,
    annual_revenue_band: str | None = None,
    profile_summary: str | None = None,
    onboarding_completed: bool | None = None,
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    if organization_name is not None:
        acc.organization_name = organization_name.strip()
    if entity_type is not None:
        acc.entity_type = entity_type.strip().upper()
    if country is not None:
        acc.country = country.strip()
    if sector is not None:
        acc.sector = sector.strip()
    if stage is not None:
        acc.stage = stage.strip().upper()
    if annual_revenue_band is not None:
        acc.annual_revenue_band = annual_revenue_band.strip().upper()
    if profile_summary is not None:
        acc.profile_summary = profile_summary.strip()
    if onboarding_completed is not None:
        acc.onboarding_completed = onboarding_completed
    acc.updated_at = _utcnow()
    db.commit()
    db.refresh(acc)
    return _serialize_account(acc)


def update_subscription_plan(
    db: Session,
    *,
    principal: Principal,
    plan_tier: str,
    enable_live_payments: bool = False,
) -> dict[str, Any]:
    if enable_live_payments:
        raise SecurityViolationError("Live payment processing is disabled by governance policy.")
    tier = (plan_tier or "FREE").strip().upper()
    if tier not in PLAN_ENTITLEMENTS:
        raise ValidationError(f"Unsupported plan_tier '{tier}'.")
    acc = _get_or_create_customer_account(db, principal=principal)
    sub = _get_or_create_subscription(db, tenant_id=principal.tenant_id, account_id=acc.account_id)
    sub.plan_tier = tier
    sub.live_payments_enabled = False
    sub.entitlements_json = json.dumps(PLAN_ENTITLEMENTS[tier])
    sub.updated_at = _utcnow()
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_SUBSCRIPTION_UPDATED",
        resource=sub.subscription_id,
        outcome=f"tier={tier}|live_payments=False",
    )
    db.commit()
    db.refresh(sub)
    return _serialize_subscription(sub)


def create_support_ticket(
    db: Session,
    *,
    principal: Principal,
    subject: str,
    message: str,
    category: str = "GENERAL",
    priority: str = "NORMAL",
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = CaravanSupportTicketRecord(
        ticket_id=f"ctkt_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        account_id=acc.account_id,
        subject=subject.strip(),
        category=(category or "GENERAL").strip().upper(),
        priority=(priority or "NORMAL").strip().upper(),
        status="OPEN",
        messages_json=json.dumps([{"sender": principal.username, "body": message.strip(), "at": _utcnow().isoformat()}]),
        created_by=principal.username,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _serialize_ticket(rec)


def list_support_tickets(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CaravanSupportTicketRecord)
        .where(CaravanSupportTicketRecord.tenant_id == principal.tenant_id)
        .order_by(CaravanSupportTicketRecord.updated_at.desc())
    ).scalars().all()
    return [_serialize_ticket(r) for r in rows]


def list_notifications(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rows = db.execute(
        select(CaravanNotificationRecord)
        .where(
            CaravanNotificationRecord.tenant_id == principal.tenant_id,
            CaravanNotificationRecord.account_id == acc.account_id,
        )
        .order_by(CaravanNotificationRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_notification(r) for r in rows]


def mark_notification_read(db: Session, *, principal: Principal, notification_id: str) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanNotificationRecord).where(
            CaravanNotificationRecord.tenant_id == principal.tenant_id,
            CaravanNotificationRecord.account_id == acc.account_id,
            CaravanNotificationRecord.notification_id == notification_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Notification '{notification_id}' not found.")
    rec.read = True
    db.commit()
    db.refresh(rec)
    return _serialize_notification(rec)


def _get_opportunity(db: Session, *, tenant_id: str, opportunity_id: str) -> CaravanFundingOpportunityRecord:
    rec = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == tenant_id,
            CaravanFundingOpportunityRecord.opportunity_id == opportunity_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Funding opportunity '{opportunity_id}' not found.")
    return rec


def _serialize_source(r: CaravanFundingSourceRecord) -> dict[str, Any]:
    return {
        "source_id": r.source_id,
        "name": r.name,
        "source_type": r.source_type,
        "base_url": r.base_url,
        "connector_id": r.connector_id,
        "verification_policy": r.verification_policy,
        "status": r.status,
        "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
        "created_at": r.created_at.isoformat(),
    }


def _serialize_opportunity(r: CaravanFundingOpportunityRecord) -> dict[str, Any]:
    return {
        "opportunity_id": r.opportunity_id,
        "source_id": r.source_id,
        "title": r.title,
        "provider_org": r.provider_org,
        "funding_type": r.funding_type,
        "source_url": r.source_url,
        "amount_display": r.amount_display,
        "currency": r.currency,
        "eligibility_requirements": r.eligibility_requirements,
        "geographic_restrictions": r.geographic_restrictions,
        "deadline_at": r.deadline_at.isoformat() if r.deadline_at else None,
        "verification_status": r.verification_status,
        "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
        "verified_by": r.verified_by,
        "supporting_evidence": r.supporting_evidence,
        "tags": json.loads(r.tags_json or "[]"),
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def _serialize_account(r: CaravanCustomerAccountRecord) -> dict[str, Any]:
    return {
        "account_id": r.account_id,
        "user_id": r.user_id,
        "organization_name": r.organization_name,
        "entity_type": r.entity_type,
        "country": r.country,
        "sector": r.sector,
        "stage": r.stage,
        "annual_revenue_band": r.annual_revenue_band,
        "profile_summary": r.profile_summary,
        "onboarding_completed": r.onboarding_completed,
        "updated_at": r.updated_at.isoformat(),
    }


def _serialize_assessment(r: CaravanEligibilityAssessmentRecord) -> dict[str, Any]:
    return {
        "assessment_id": r.assessment_id,
        "account_id": r.account_id,
        "opportunity_id": r.opportunity_id,
        "score": r.score,
        "verdict": r.verdict,
        "matched_criteria": json.loads(r.matched_criteria_json or "[]"),
        "gaps": json.loads(r.gaps_json or "[]"),
        "recommendations": json.loads(r.recommendations_json or "[]"),
        "neon_mode": r.neon_mode,
        "assessed_by": r.assessed_by,
        "created_at": r.created_at.isoformat(),
    }


def _serialize_application(r: CaravanApplicationRecord) -> dict[str, Any]:
    return {
        "application_id": r.application_id,
        "account_id": r.account_id,
        "opportunity_id": r.opportunity_id,
        "status": r.status,
        "progress_pct": r.progress_pct,
        "checklist": json.loads(r.checklist_json or "[]"),
        "notes": r.notes,
        "approval_id": r.approval_id,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def _serialize_saved(r: CaravanSavedOpportunityRecord) -> dict[str, Any]:
    return {
        "saved_id": r.saved_id,
        "account_id": r.account_id,
        "opportunity_id": r.opportunity_id,
        "notes": r.notes,
        "created_at": r.created_at.isoformat(),
    }


def _serialize_subscription(r: CaravanSubscriptionRecord) -> dict[str, Any]:
    return {
        "subscription_id": r.subscription_id,
        "account_id": r.account_id,
        "plan_tier": r.plan_tier,
        "status": r.status,
        "live_payments_enabled": bool(r.live_payments_enabled),
        "entitlements": json.loads(r.entitlements_json or "{}"),
        "updated_at": r.updated_at.isoformat(),
    }


def _serialize_ticket(r: CaravanSupportTicketRecord) -> dict[str, Any]:
    return {
        "ticket_id": r.ticket_id,
        "account_id": r.account_id,
        "subject": r.subject,
        "category": r.category,
        "priority": r.priority,
        "status": r.status,
        "messages": json.loads(r.messages_json or "[]"),
        "assigned_to": r.assigned_to,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def _serialize_notification(r: CaravanNotificationRecord) -> dict[str, Any]:
    return {
        "notification_id": r.notification_id,
        "account_id": r.account_id,
        "title": r.title,
        "body": r.body,
        "category": r.category,
        "read": r.read,
        "created_at": r.created_at.isoformat(),
    }


def verify_funding_source_via_argon(
    db: Session,
    *,
    principal: Principal,
    source_id: str,
    http_client: Any = None,
) -> dict[str, Any]:
    """ARGON-controlled SSRF-hardened reachability verification for a registered funding source."""
    import httpx

    src = db.execute(
        select(CaravanFundingSourceRecord).where(
            CaravanFundingSourceRecord.tenant_id == principal.tenant_id,
            CaravanFundingSourceRecord.source_id == source_id,
        )
    ).scalar_one_or_none()
    if src is None:
        raise NotFoundError(f"Funding source '{source_id}' not found.")

    clean_url = validate_public_https_url(src.base_url)
    now = _utcnow()
    reachable = False
    http_status: int | None = None
    detail = ""
    try:
        if http_client is not None:
            resp = http_client.get(clean_url, timeout=8.0, follow_redirects=True)
        else:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                resp = client.get(clean_url)
        http_status = resp.status_code
        reachable = 200 <= resp.status_code < 400
        detail = f"HTTP {resp.status_code}" if reachable else f"HTTP {resp.status_code} (unhealthy)"
    except Exception as exc:
        detail = f"Network error: {type(exc).__name__}"

    src.last_checked_at = now
    src.status = "ACTIVE" if reachable else "DEGRADED"
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_ARGON_SOURCE_CHECK",
        resource=src.source_id,
        outcome=f"reachable={reachable}|status={http_status}|{detail}",
    )
    db.commit()
    return {
        "source_id": src.source_id,
        "name": src.name,
        "base_url": clean_url,
        "reachable": reachable,
        "http_status": http_status,
        "status": src.status,
        "last_checked_at": now.isoformat(),
        "argon_workflow": "SSRF_GUARDED_SOURCE_PROBE",
        "detail": detail,
    }

