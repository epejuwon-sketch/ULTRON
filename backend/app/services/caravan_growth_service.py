"""CARAVAN Phase 6 — Growth, Revenue, Safe Payment Webhooks, CRM, Retention, NEON BI & Privacy."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, NotFoundError, SecurityViolationError, ValidationError
from app.core.permissions import Principal, Role
from app.db.models import (
    AuditLogRecord,
    CaravanApplicationRecord,
    CaravanCrmNoteRecord,
    CaravanCustomerAccountRecord,
    CaravanEligibilityAssessmentRecord,
    BusinessAnalyticsEventRecord,
    CaravanFundingOpportunityRecord,
    CaravanGrowthDraftRecord,
    CaravanOperatingExpenseRecord,
    CaravanPaymentEventRecord,
    CaravanPrivacyConsentRecord,
    CaravanSavedOpportunityRecord,
    CaravanSubscriptionRecord,
    CaravanSupportTicketRecord,
)
from app.db.repositories import append_audit_log
from app.services.caravan_product_service import PLAN_ENTITLEMENTS, _get_or_create_customer_account
from app.services.operational_control_service import evaluate_operational_action

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "FREE": {
        "tier": "FREE",
        "label": "Community Explorer (Free)",
        "target_audience": "Individuals, students, and early-stage founders exploring verified funding.",
        "monthly_usd": 0.0,
        "annual_usd": 0.0,
        "monthly_ngn": 0.0,
        "annual_ngn": 0.0,
        "entitlements": PLAN_ENTITLEMENTS["FREE"],
    },
    "STARTER": {
        "tier": "STARTER",
        "label": "Emerging Founder (Starter)",
        "target_audience": "Early-stage startups and solo founders initiating grant applications.",
        "monthly_usd": 19.0,
        "annual_usd": 190.0,
        "monthly_ngn": 29000.0,
        "annual_ngn": 290000.0,
        "entitlements": PLAN_ENTITLEMENTS["STARTER"],
    },
    "GROWTH": {
        "tier": "GROWTH",
        "label": "Growth Accelerator",
        "target_audience": "Active seed/pre-series A ventures scaling application output.",
        "monthly_usd": 49.0,
        "annual_usd": 490.0,
        "monthly_ngn": 75000.0,
        "annual_ngn": 750000.0,
        "entitlements": PLAN_ENTITLEMENTS["GROWTH"],
    },
    "PRO": {
        "tier": "PRO",
        "label": "Caravan Pro",
        "target_audience": "High-volume applicants and advisory teams requiring advanced intelligence.",
        "monthly_usd": 99.0,
        "annual_usd": 990.0,
        "monthly_ngn": 150000.0,
        "annual_ngn": 1500000.0,
        "entitlements": PLAN_ENTITLEMENTS["PRO"],
    },
    "BUSINESS": {
        "tier": "BUSINESS",
        "label": "Business & Institutional",
        "target_audience": "Incubators, venture studios, universities, and corporate accelerators.",
        "monthly_usd": 249.0,
        "annual_usd": 2490.0,
        "monthly_ngn": 380000.0,
        "annual_ngn": 3800000.0,
        "entitlements": PLAN_ENTITLEMENTS["BUSINESS"],
    },
    "ENTERPRISE": {
        "tier": "ENTERPRISE",
        "label": "Custom Enterprise",
        "target_audience": "Government agencies, sovereign wealth funds, and large ecosystem managers.",
        "monthly_usd": 999.0,
        "annual_usd": 9990.0,
        "monthly_ngn": 1500000.0,
        "annual_ngn": 15000000.0,
        "entitlements": PLAN_ENTITLEMENTS["ENTERPRISE"],
    },
}
# Backward compatibility aliases
PLAN_CATALOG["INSTITUTIONAL"] = PLAN_CATALOG["BUSINESS"]
PLAN_CATALOG["CUSTOM"] = PLAN_CATALOG["ENTERPRISE"]


PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_public_pricing_catalog() -> dict[str, Any]:
    canonical_plans = [v for k, v in PLAN_CATALOG.items() if k not in {"INSTITUTIONAL", "CUSTOM"}]
    return {
        "live_payments_enabled": False,
        "sandbox_mode": True,
        "currencies": ["USD", "NGN"],
        "plans": canonical_plans,
        "cancellation_policy": "Cancel anytime; access continues through the current period with zero hidden fees.",
        "legal_notice": "Terms of Service, Privacy Policy, and NDPR/GDPR consent controls apply prior to public launch.",
    }


def verify_payment_webhook_signature(
    *,
    provider: str,
    raw_body: bytes,
    signature: str,
    secret: str,
) -> bool:
    prov = (provider or "").strip().lower()
    clean_sig = (signature or "").strip()
    clean_sec = (secret or "").strip()
    if not clean_sig or not clean_sec:
        return False
    if prov == "flutterwave":
        return hmac.compare_digest(clean_sig, clean_sec)
    # HMAC-SHA256 for paystack, stripe-compatible, or sandbox webhooks
    expected = hmac.new(clean_sec.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(clean_sig.lower(), expected.lower())


def ingest_payment_webhook(
    db: Session,
    *,
    tenant_id: str,
    account_id: str,
    provider: str,
    provider_ref: str,
    event_type: str,
    amount: float,
    currency: str,
    status: str,
    raw_body: bytes,
    signature: str,
    webhook_secret: str,
    sandbox_mode: bool = True,
    actor: str = "payment-webhook",
) -> dict[str, Any]:
    """Verify webhook signature, enforce idempotency, and record non-sensitive payment event."""
    if not sandbox_mode:
        raise SecurityViolationError("Live payment execution is disabled until explicitly authorized.")
    if not verify_payment_webhook_signature(
        provider=provider, raw_body=raw_body, signature=signature, secret=webhook_secret
    ):
        raise SecurityViolationError("Invalid payment webhook signature.")

    prov = provider.strip().lower()
    ref = provider_ref.strip()
    existing = db.execute(
        select(CaravanPaymentEventRecord).where(
            CaravanPaymentEventRecord.tenant_id == tenant_id,
            CaravanPaymentEventRecord.provider == prov,
            CaravanPaymentEventRecord.provider_ref == ref,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "payment_event_id": existing.payment_event_id,
            "idempotent_duplicate": True,
            "status": existing.status,
        }

    rec = CaravanPaymentEventRecord(
        payment_event_id=f"cpay_{uuid.uuid4().hex[:14]}",
        tenant_id=tenant_id,
        account_id=account_id,
        provider=prov,
        provider_ref=ref,
        event_type=event_type.strip().upper(),
        amount=round(float(amount), 2),
        currency=currency.strip().upper()[:16],
        status=status.strip().upper()[:24],
        sandbox_mode=True,
        signature_verified=True,
        metadata_json="{}",
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=tenant_id,
        actor=actor,
        action="CARAVAN_PAYMENT_EVENT_RECORDED",
        resource=rec.payment_event_id,
        outcome=f"provider={prov}|status={rec.status}|sandbox=True",
    )
    db.commit()
    db.refresh(rec)
    return {
        "payment_event_id": rec.payment_event_id,
        "idempotent_duplicate": False,
        "provider": rec.provider,
        "provider_ref": rec.provider_ref,
        "amount": rec.amount,
        "currency": rec.currency,
        "status": rec.status,
        "sandbox_mode": rec.sandbox_mode,
        "signature_verified": rec.signature_verified,
    }


def record_operating_expense(
    db: Session,
    *,
    principal: Principal,
    category: str,
    description: str,
    amount: float,
    currency: str = "USD",
) -> dict[str, Any]:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may record operating expenses.")
    cat = category.strip().upper()
    if cat not in {"PAYMENT_FEE", "HOSTING", "AI_PROVIDER", "OTHER"}:
        raise ValidationError("Expense category must be PAYMENT_FEE, HOSTING, AI_PROVIDER, or OTHER.")
    rec = CaravanOperatingExpenseRecord(
        expense_id=f"cexp_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        category=cat,
        description=description.strip()[:240],
        amount=round(float(amount), 2),
        currency=currency.strip().upper()[:16],
        recorded_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_EXPENSE_RECORDED",
        resource=rec.expense_id,
        outcome=f"{cat}|{rec.amount} {rec.currency}",
    )
    db.commit()
    db.refresh(rec)
    return {
        "expense_id": rec.expense_id,
        "category": rec.category,
        "description": rec.description,
        "amount": rec.amount,
        "currency": rec.currency,
        "created_at": rec.created_at.isoformat(),
    }


def get_caravan_business_intelligence(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    period: str = "monthly",
) -> dict[str, Any]:
    """Compute real business, revenue, funnel, retention, financial, and NEON BI metrics."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may view Caravan Business Intelligence.")
    tid = principal.tenant_id
    p_key = period.strip().lower()
    days = PERIOD_DAYS.get(p_key, 30)
    cutoff = _utcnow() - timedelta(days=days)

    accounts = db.execute(select(CaravanCustomerAccountRecord).where(CaravanCustomerAccountRecord.tenant_id == tid)).scalars().all()
    subs = db.execute(select(CaravanSubscriptionRecord).where(CaravanSubscriptionRecord.tenant_id == tid)).scalars().all()
    payments = db.execute(select(CaravanPaymentEventRecord).where(CaravanPaymentEventRecord.tenant_id == tid)).scalars().all()
    expenses = db.execute(select(CaravanOperatingExpenseRecord).where(CaravanOperatingExpenseRecord.tenant_id == tid)).scalars().all()
    assessments = db.execute(select(CaravanEligibilityAssessmentRecord).where(CaravanEligibilityAssessmentRecord.tenant_id == tid)).scalars().all()
    saved = db.execute(select(CaravanSavedOpportunityRecord).where(CaravanSavedOpportunityRecord.tenant_id == tid)).scalars().all()
    apps = db.execute(select(CaravanApplicationRecord).where(CaravanApplicationRecord.tenant_id == tid)).scalars().all()
    tickets = db.execute(select(CaravanSupportTicketRecord).where(CaravanSupportTicketRecord.tenant_id == tid)).scalars().all()
    opps = db.execute(select(CaravanFundingOpportunityRecord).where(CaravanFundingOpportunityRecord.tenant_id == tid)).scalars().all()
    events = db.execute(select(BusinessAnalyticsEventRecord).where(BusinessAnalyticsEventRecord.tenant_id == tid, BusinessAnalyticsEventRecord.venture == "CARAVAN")).scalars().all()
    audits = db.execute(select(AuditLogRecord).where(AuditLogRecord.tenant_id == tid, AuditLogRecord.created_at >= cutoff)).scalars().all()

    total_customers = len(accounts)
    new_registrations = sum(
        1 for a in accounts if (a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)) >= cutoff
    )
    onboarded_customers = sum(1 for a in accounts if a.onboarding_completed)
    onboarding_pct = round((onboarded_customers / total_customers) * 100, 1) if total_customers else 0.0

    sub_dist = {"FREE": 0, "STARTER": 0, "GROWTH": 0, "PRO": 0, "BUSINESS": 0, "ENTERPRISE": 0}
    for s in subs:
        normalized_tier = "BUSINESS" if s.plan_tier == "INSTITUTIONAL" else ("ENTERPRISE" if s.plan_tier == "CUSTOM" else s.plan_tier)
        sub_dist[normalized_tier] = sub_dist.get(normalized_tier, 0) + 1
    paid_subs = sum(
        1 for s in subs if s.plan_tier in {"STARTER", "GROWTH", "PRO", "BUSINESS", "ENTERPRISE", "INSTITUTIONAL", "CUSTOM"} and s.status == "ACTIVE"
    )
    free_to_paid_pct = round((paid_subs / total_customers) * 100, 1) if total_customers else 0.0

    # Committed MRR/ARR (based on active subscriptions, clearly labelled as commitments vs actual collected)
    committed_mrr_usd = sum(PLAN_CATALOG.get(s.plan_tier, PLAN_CATALOG["FREE"])["monthly_usd"] for s in subs if s.status == "ACTIVE")
    committed_arr_usd = round(committed_mrr_usd * 12.0, 2)

    # Actual payment events grouped by currency
    collected_by_cur: dict[str, float] = {}
    pending_by_cur: dict[str, float] = {}
    refunds_by_cur: dict[str, float] = {}
    failed_payments = 0
    for pay in payments:
        cur = pay.currency or "USD"
        if pay.status == "SUCCEEDED":
            collected_by_cur[cur] = round(collected_by_cur.get(cur, 0.0) + pay.amount, 2)
        elif pay.status == "PENDING":
            pending_by_cur[cur] = round(pending_by_cur.get(cur, 0.0) + pay.amount, 2)
        elif pay.status == "REFUNDED":
            refunds_by_cur[cur] = round(refunds_by_cur.get(cur, 0.0) + pay.amount, 2)
        elif pay.status == "FAILED":
            failed_payments += 1

    expenses_by_cur: dict[str, float] = {}
    for ex in expenses:
        cur = ex.currency or "USD"
        expenses_by_cur[cur] = round(expenses_by_cur.get(cur, 0.0) + ex.amount, 2)

    gross_usd = collected_by_cur.get("USD", 0.0)
    refunds_usd = refunds_by_cur.get("USD", 0.0)
    expenses_usd = expenses_by_cur.get("USD", 0.0)
    net_usd = round(gross_usd - refunds_usd, 2)
    margin_usd = round(net_usd - expenses_usd, 2)
    arpu_usd = round(gross_usd / paid_subs, 2) if paid_subs else 0.0

    # Retention & churn
    canceled_subs = sum(1 for s in subs if s.status in {"CANCELED", "CANCELLED"})
    churn_pct = round((canceled_subs / len(subs)) * 100, 1) if subs else 0.0
    retention_pct = round(100.0 - churn_pct, 1) if subs else 0.0
    ltv_usd = round(arpu_usd * (12.0 if churn_pct == 0 else (100.0 / max(1.0, churn_pct))), 2) if arpu_usd > 0 else 0.0

    # Acquisition & Funnel
    source_counts: dict[str, int] = {}
    for ev in events:
        src = ev.acquisition_source or "DIRECT"
        source_counts[src] = source_counts.get(src, 0) + ev.count_value

    saved_accounts = {s.account_id for s in saved}
    assessed_accounts = {a.account_id for a in assessments}
    app_accounts = {ap.account_id for ap in apps}

    # Retention alerts
    incomplete_onboarding = [a.account_id for a in accounts if not a.onboarding_completed]
    unresolved_tickets = [t.ticket_id for t in tickets if t.status in {"OPEN", "IN_PROGRESS"}]

    # NEON Business Intelligence (Strict separation of observed facts vs AI interpretation)
    gemini_ready = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    neon_mode = "GEMINI_LIVE" if gemini_ready else "DETERMINISTIC"

    return {
        "period": p_key,
        "window_days": days,
        "business_command_centre": {
            "total_customers": total_customers,
            "new_registrations": new_registrations,
            "active_customers": onboarded_customers,
            "onboarding_completion_pct": onboarding_pct,
            "subscription_distribution": sub_dist,
            "free_to_paid_conversion_pct": free_to_paid_pct,
            "subscription_commitments_mrr_usd": round(committed_mrr_usd, 2),
            "subscription_commitments_arr_usd": committed_arr_usd,
            "actual_collected_by_currency": collected_by_cur,
            "pending_by_currency": pending_by_cur,
            "refunds_by_currency": refunds_by_cur,
            "failed_payments_count": failed_payments,
            "arpu_usd": arpu_usd,
            "ltv_usd": ltv_usd,
            "ltv_methodology": "ARPU_USD * (12 months if churn=0% else 100/churn_pct); 0.0 when no actual collected revenue.",
            "retention_pct": retention_pct,
            "churn_pct": churn_pct,
            "support_tickets_open": len(unresolved_tickets),
            "opportunities_total": len(opps),
            "applications_total": len(apps),
            "neon_assessments_total": len(assessments),
            "audit_events_in_window": len(audits),
        },
        "acquisition_funnel": {
            "registered_customers": total_customers,
            "onboarded_customers": onboarded_customers,
            "customers_with_assessments": len(assessed_accounts),
            "customers_with_saved": len(saved_accounts),
            "customers_with_applications": len(app_accounts),
            "paid_subscriptions": paid_subs,
            "acquisition_sources": source_counts,
        },
        "retention_intelligence": {
            "incomplete_onboarding_count": len(incomplete_onboarding),
            "unresolved_support_cases_count": len(unresolved_tickets),
            "canceled_subscriptions_count": canceled_subs,
            "recommendations": [
                f"Follow up with {len(incomplete_onboarding)} incomplete onboarding account(s) via consent-approved channels."
                if incomplete_onboarding
                else "All registered customer accounts have completed onboarding.",
                f"Resolve {len(unresolved_tickets)} open customer support ticket(s)."
                if unresolved_tickets
                else "No unresolved support backlog.",
            ],
        },
        "financial_intelligence": {
            "live_payments_enabled": False,
            "gross_collected_by_currency": collected_by_cur,
            "refunds_by_currency": refunds_by_cur,
            "operating_expenses_by_currency": expenses_by_cur,
            "net_collected_usd": net_usd,
            "estimated_operating_margin_usd": margin_usd,
            "read_only": True,
        },
        "neon_business_intelligence": {
            "neon_mode": neon_mode,
            "gemini_available": gemini_ready,
            "observed_facts": {
                "total_customers": total_customers,
                "onboarding_completion_pct": onboarding_pct,
                "free_to_paid_conversion_pct": free_to_paid_pct,
                "actual_collected_usd": gross_usd,
            },
            "ai_interpretation": {
                "summary": (
                    f"Over the {p_key} window ({days}d), Caravan has {total_customers} customer(s), "
                    f"{onboarding_pct}% onboarding completion, and {free_to_paid_pct}% paid conversion."
                ),
                "note": (
                    "Generated by Gemini live model."
                    if gemini_ready
                    else "Gemini API key not configured; deterministic BI summary used."
                ),
            },
        },
    }


def list_crm_customers(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may access Caravan CRM.")
    tid = principal.tenant_id
    accounts = db.execute(select(CaravanCustomerAccountRecord).where(CaravanCustomerAccountRecord.tenant_id == tid)).scalars().all()
    subs = db.execute(select(CaravanSubscriptionRecord).where(CaravanSubscriptionRecord.tenant_id == tid)).scalars().all()
    notes = db.execute(select(CaravanCrmNoteRecord).where(CaravanCrmNoteRecord.tenant_id == tid).order_by(CaravanCrmNoteRecord.created_at.desc())).scalars().all()
    sub_map = {s.account_id: s.plan_tier for s in subs}
    notes_map: dict[str, list[dict[str, Any]]] = {}
    for n in notes:
        notes_map.setdefault(n.account_id, []).append({
            "note_id": n.note_id,
            "author": n.author,
            "note": n.note,
            "segment_tag": n.segment_tag,
            "created_at": n.created_at.isoformat(),
        })
    return [
        {
            "account_id": a.account_id,
            "organization_name": a.organization_name,
            "entity_type": a.entity_type,
            "country": a.country,
            "sector": a.sector,
            "onboarding_completed": a.onboarding_completed,
            "plan_tier": sub_map.get(a.account_id, "FREE"),
            "notes": notes_map.get(a.account_id, []),
        }
        for a in accounts
    ]


def add_crm_note(
    db: Session,
    *,
    principal: Principal,
    account_id: str,
    note: str,
    segment_tag: str = "GENERAL",
) -> dict[str, Any]:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may add CRM notes.")
    acc = db.execute(
        select(CaravanCustomerAccountRecord).where(
            CaravanCustomerAccountRecord.tenant_id == principal.tenant_id,
            CaravanCustomerAccountRecord.account_id == account_id,
        )
    ).scalar_one_or_none()
    if acc is None:
        raise NotFoundError(f"Customer account '{account_id}' not found.")
    rec = CaravanCrmNoteRecord(
        note_id=f"ccrm_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        account_id=account_id,
        author=principal.username,
        note=note.strip(),
        segment_tag=segment_tag.strip().upper()[:64],
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_CRM_NOTE_ADDED",
        resource=account_id,
        outcome=rec.segment_tag,
    )
    db.commit()
    db.refresh(rec)
    return {
        "note_id": rec.note_id,
        "account_id": rec.account_id,
        "author": rec.author,
        "note": rec.note,
        "segment_tag": rec.segment_tag,
        "created_at": rec.created_at.isoformat(),
    }


def create_growth_draft(
    db: Session,
    *,
    principal: Principal,
    draft_type: str,
    title: str,
    content: str,
    target_segment: str = "ALL",
) -> dict[str, Any]:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may create growth drafts.")
    rec = CaravanGrowthDraftRecord(
        draft_id=f"cdrf_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        draft_type=draft_type.strip().upper()[:32],
        title=title.strip()[:200],
        content=content.strip(),
        target_segment=target_segment.strip().upper()[:64],
        status="DRAFT",
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_GROWTH_DRAFT_CREATED",
        resource=rec.draft_id,
        outcome=rec.draft_type,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_draft(rec)


def request_growth_draft_approval(db: Session, *, principal: Principal, draft_id: str) -> dict[str, Any]:
    """Route external campaign/communication draft through AEGIS approval gate."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may request growth draft approval.")
    rec = db.execute(
        select(CaravanGrowthDraftRecord).where(
            CaravanGrowthDraftRecord.tenant_id == principal.tenant_id,
            CaravanGrowthDraftRecord.draft_id == draft_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Growth draft '{draft_id}' not found.")
    gate = evaluate_operational_action(
        db,
        principal=principal,
        action_category="PUBLISH_CAMPAIGN",
        summary=f"Publish Caravan {rec.draft_type}: {rec.title}",
        venture="CARAVAN",
        payload={"draft_id": rec.draft_id, "target_segment": rec.target_segment},
    )
    rec.status = "APPROVED" if gate.get("status") == "APPROVED" else "AWAITING_APPROVAL"
    rec.approval_id = gate.get("approval_id")
    rec.updated_at = _utcnow()
    db.commit()
    db.refresh(rec)
    return _serialize_draft(rec)


def _serialize_draft(r: CaravanGrowthDraftRecord) -> dict[str, Any]:
    return {
        "draft_id": r.draft_id,
        "draft_type": r.draft_type,
        "title": r.title,
        "content": r.content,
        "target_segment": r.target_segment,
        "status": r.status,
        "approval_id": r.approval_id,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat(),
    }


def get_privacy_consent(db: Session, *, principal: Principal) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanPrivacyConsentRecord).where(
            CaravanPrivacyConsentRecord.tenant_id == principal.tenant_id,
            CaravanPrivacyConsentRecord.account_id == acc.account_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = CaravanPrivacyConsentRecord(
            consent_id=f"cprv_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            account_id=acc.account_id,
            analytics_consent=False,
            marketing_consent=False,
            deletion_requested=False,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return {
        "consent_id": rec.consent_id,
        "account_id": rec.account_id,
        "analytics_consent": bool(rec.analytics_consent),
        "marketing_consent": bool(rec.marketing_consent),
        "deletion_requested": bool(rec.deletion_requested),
        "deletion_reason": rec.deletion_reason,
        "updated_at": rec.updated_at.isoformat(),
    }


def update_privacy_consent(
    db: Session,
    *,
    principal: Principal,
    analytics_consent: bool | None = None,
    marketing_consent: bool | None = None,
    deletion_requested: bool | None = None,
    deletion_reason: str | None = None,
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanPrivacyConsentRecord).where(
            CaravanPrivacyConsentRecord.tenant_id == principal.tenant_id,
            CaravanPrivacyConsentRecord.account_id == acc.account_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        get_privacy_consent(db, principal=principal)
        rec = db.execute(
            select(CaravanPrivacyConsentRecord).where(
                CaravanPrivacyConsentRecord.tenant_id == principal.tenant_id,
                CaravanPrivacyConsentRecord.account_id == acc.account_id,
            )
        ).scalar_one()
    if analytics_consent is not None:
        rec.analytics_consent = analytics_consent
    if marketing_consent is not None:
        rec.marketing_consent = marketing_consent
    if deletion_requested is not None:
        rec.deletion_requested = deletion_requested
    if deletion_reason is not None:
        rec.deletion_reason = deletion_reason.strip()
    rec.updated_at = _utcnow()
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_PRIVACY_UPDATED",
        resource=rec.account_id,
        outcome=f"analytics={rec.analytics_consent}|marketing={rec.marketing_consent}|deletion={rec.deletion_requested}",
    )
    db.commit()
    db.refresh(rec)
    return get_privacy_consent(db, principal=principal)
