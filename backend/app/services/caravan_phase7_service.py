"""CARAVAN Phase 7 — Production Reliability, Listing Reports, Conflict Detection & Notification Dispatch."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.permissions import Principal, Role
from app.db.models import (
    CaravanCustomerAccountRecord,
    CaravanFundingOpportunityRecord,
    CaravanListingReportRecord,
    CaravanNotificationDeliveryRecord,
    CaravanNotificationPreferenceRecord,
    CaravanPrivacyConsentRecord,
    CaravanSubscriptionRecord,
    IntegrationConnectionRecord,
)
from app.db.repositories import append_audit_log
from app.services.caravan_product_service import _get_or_create_customer_account

VALID_REPORT_REASONS = frozenset({"INCORRECT_INFO", "EXPIRED", "DUPLICATE", "BROKEN_LINK", "SUSPICIOUS"})
VALID_REPORT_STATUSES = frozenset({"OPEN", "RESOLVED", "DISMISSED"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(principal: Principal, action_desc: str) -> None:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError(f"Only OWNER or ADMIN administrators may {action_desc}.")


def report_funding_listing(
    db: Session,
    *,
    principal: Principal,
    opportunity_id: str,
    reason: str,
    details: str = "",
) -> dict[str, Any]:
    """Allow customers to report inaccurate, expired, duplicate, or broken funding listings."""
    clean_reason = reason.strip().upper()
    if clean_reason not in VALID_REPORT_REASONS:
        raise ValidationError(f"Invalid report reason '{reason}'. Allowed: {sorted(VALID_REPORT_REASONS)}")

    opp = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanFundingOpportunityRecord.opportunity_id == opportunity_id,
        )
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundError(f"Funding opportunity '{opportunity_id}' not found.")

    acc = _get_or_create_customer_account(db, principal=principal)
    rec = CaravanListingReportRecord(
        report_id=f"crep_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        opportunity_id=opp.opportunity_id,
        account_id=acc.account_id,
        reported_by=principal.username,
        reason=clean_reason,
        details=details.strip()[:2000],
        status="OPEN",
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_LISTING_REPORTED",
        resource=opp.opportunity_id,
        outcome=clean_reason,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_report(rec)


def list_listing_reports(
    db: Session,
    *,
    principal: Principal,
    status_filter: str = "",
) -> list[dict[str, Any]]:
    _require_admin(principal, "review customer listing reports")
    stmt = (
        select(CaravanListingReportRecord)
        .where(CaravanListingReportRecord.tenant_id == principal.tenant_id)
        .order_by(CaravanListingReportRecord.created_at.desc())
    )
    if status_filter.strip():
        stmt = stmt.where(CaravanListingReportRecord.status == status_filter.strip().upper())
    rows = db.execute(stmt).scalars().all()
    return [_serialize_report(r) for r in rows]


def review_listing_report(
    db: Session,
    *,
    principal: Principal,
    report_id: str,
    status_value: str,
    resolution_note: str = "",
) -> dict[str, Any]:
    _require_admin(principal, "resolve customer listing reports")
    next_status = status_value.strip().upper()
    if next_status not in VALID_REPORT_STATUSES:
        raise ValidationError(f"Invalid report status '{status_value}'.")
    rec = db.execute(
        select(CaravanListingReportRecord).where(
            CaravanListingReportRecord.tenant_id == principal.tenant_id,
            CaravanListingReportRecord.report_id == report_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Listing report '{report_id}' not found.")
    rec.status = next_status
    rec.resolution_note = resolution_note.strip()[:2000]
    rec.reviewed_by = principal.username
    rec.updated_at = _utcnow()
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_LISTING_REPORT_REVIEWED",
        resource=rec.report_id,
        outcome=next_status,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_report(rec)


def _serialize_report(r: CaravanListingReportRecord) -> dict[str, Any]:
    return {
        "report_id": r.report_id,
        "opportunity_id": r.opportunity_id,
        "account_id": r.account_id,
        "reported_by": r.reported_by,
        "reason": r.reason,
        "details": r.details,
        "status": r.status,
        "resolution_note": r.resolution_note,
        "reviewed_by": r.reviewed_by,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def detect_conflicting_opportunities(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    """Detect opportunities sharing title/provider or source_url but with conflicting amounts or deadlines."""
    opps = db.execute(
        select(CaravanFundingOpportunityRecord).where(CaravanFundingOpportunityRecord.tenant_id == tenant_id)
    ).scalars().all()
    by_key: dict[str, list[CaravanFundingOpportunityRecord]] = {}
    for o in opps:
        key = f"{o.title.strip().lower()}::{o.provider_org.strip().lower()}"
        by_key.setdefault(key, []).append(o)

    conflicts: list[dict[str, Any]] = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        amounts = {g.amount_display.strip() for g in group}
        deadlines = {g.deadline_at.isoformat() if g.deadline_at else "NONE" for g in group}
        if len(amounts) > 1 or len(deadlines) > 1:
            conflicts.append({
                "key": key,
                "opportunity_ids": [g.opportunity_id for g in group],
                "conflicting_amounts": sorted(amounts),
                "conflicting_deadlines": sorted(deadlines),
            })
    return conflicts


def get_notification_preferences(db: Session, *, principal: Principal) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanNotificationPreferenceRecord).where(
            CaravanNotificationPreferenceRecord.tenant_id == principal.tenant_id,
            CaravanNotificationPreferenceRecord.account_id == acc.account_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = CaravanNotificationPreferenceRecord(
            pref_id=f"cnpf_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            account_id=acc.account_id,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return _serialize_prefs(rec)


def update_notification_preferences(
    db: Session,
    *,
    principal: Principal,
    in_app_enabled: bool | None = None,
    email_enabled: bool | None = None,
    deadline_alerts: bool | None = None,
    saved_updates: bool | None = None,
    subscription_alerts: bool | None = None,
    support_updates: bool | None = None,
    whatsapp_enabled: bool | None = None,
) -> dict[str, Any]:
    acc = _get_or_create_customer_account(db, principal=principal)
    rec = db.execute(
        select(CaravanNotificationPreferenceRecord).where(
            CaravanNotificationPreferenceRecord.tenant_id == principal.tenant_id,
            CaravanNotificationPreferenceRecord.account_id == acc.account_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = CaravanNotificationPreferenceRecord(
            pref_id=f"cnpf_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            account_id=acc.account_id,
        )
        db.add(rec)

    if in_app_enabled is not None:
        rec.in_app_enabled = in_app_enabled
    if email_enabled is not None:
        rec.email_enabled = email_enabled
    if deadline_alerts is not None:
        rec.deadline_alerts = deadline_alerts
    if saved_updates is not None:
        rec.saved_updates = saved_updates
    if subscription_alerts is not None:
        rec.subscription_alerts = subscription_alerts
    if support_updates is not None:
        rec.support_updates = support_updates
    if whatsapp_enabled is True:
        wa_conn = db.execute(
            select(IntegrationConnectionRecord).where(
                IntegrationConnectionRecord.tenant_id == principal.tenant_id,
                IntegrationConnectionRecord.provider == "whatsapp",
                IntegrationConnectionRecord.status == "AVAILABLE",
            )
        ).scalar_one_or_none()
        if wa_conn is None:
            raise ValidationError(
                "WhatsApp notifications require an explicitly authorized and live-verified WhatsApp Business connection."
            )
        rec.whatsapp_authorized = True
        rec.whatsapp_enabled = True
    elif whatsapp_enabled is False:
        rec.whatsapp_enabled = False

    rec.updated_at = _utcnow()
    db.commit()
    db.refresh(rec)
    return _serialize_prefs(rec)


def _serialize_prefs(r: CaravanNotificationPreferenceRecord) -> dict[str, Any]:
    return {
        "pref_id": r.pref_id,
        "account_id": r.account_id,
        "in_app_enabled": r.in_app_enabled,
        "email_enabled": r.email_enabled,
        "deadline_alerts": r.deadline_alerts,
        "saved_updates": r.saved_updates,
        "subscription_alerts": r.subscription_alerts,
        "support_updates": r.support_updates,
        "whatsapp_enabled": r.whatsapp_enabled,
        "whatsapp_authorized": r.whatsapp_authorized,
        "updated_at": r.updated_at.isoformat(),
    }


def list_notification_deliveries(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    acc = _get_or_create_customer_account(db, principal=principal)
    stmt = select(CaravanNotificationDeliveryRecord).where(
        CaravanNotificationDeliveryRecord.tenant_id == principal.tenant_id
    )
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        stmt = stmt.where(CaravanNotificationDeliveryRecord.account_id == acc.account_id)
    rows = db.execute(stmt.order_by(CaravanNotificationDeliveryRecord.created_at.desc()).limit(100)).scalars().all()
    return [
        {
            "delivery_id": d.delivery_id,
            "account_id": d.account_id,
            "channel": d.channel,
            "event_type": d.event_type,
            "subject": d.subject,
            "status": d.status,
            "error_detail": d.error_detail,
            "created_at": d.created_at.isoformat(),
            "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        }
        for d in rows
    ]


def dispatch_pending_notifications(db: Session, *, tenant_id: str) -> dict[str, Any]:
    """Process queued notification deliveries while enforcing consent, preferences, and WhatsApp provider gates."""
    queued = db.execute(
        select(CaravanNotificationDeliveryRecord)
        .where(
            CaravanNotificationDeliveryRecord.tenant_id == tenant_id,
            CaravanNotificationDeliveryRecord.status == "QUEUED",
        )
        .order_by(CaravanNotificationDeliveryRecord.created_at.asc())
        .limit(50)
    ).scalars().all()
    sent = 0
    blocked = 0
    now = _utcnow()
    for d in queued:
        pref = db.execute(
            select(CaravanNotificationPreferenceRecord).where(
                CaravanNotificationPreferenceRecord.tenant_id == tenant_id,
                CaravanNotificationPreferenceRecord.account_id == d.account_id,
            )
        ).scalar_one_or_none()
        consent = db.execute(
            select(CaravanPrivacyConsentRecord).where(
                CaravanPrivacyConsentRecord.tenant_id == tenant_id,
                CaravanPrivacyConsentRecord.account_id == d.account_id,
            )
        ).scalar_one_or_none()

        is_transactional = d.event_type in {"EMAIL_VERIFICATION", "PASSWORD_RESET", "SUPPORT_UPDATE"}
        if d.channel == "WHATSAPP" and (pref is None or not pref.whatsapp_enabled or not pref.whatsapp_authorized):
            d.status = "BLOCKED"
            d.error_detail = "WhatsApp channel not authorized or disabled by user preference."
            blocked += 1
            continue
        if d.channel == "EMAIL" and pref is not None and not pref.email_enabled and not is_transactional:
            d.status = "BLOCKED"
            d.error_detail = "Email notifications disabled by user preference."
            blocked += 1
            continue
        if not is_transactional and d.event_type == "MARKETING" and (consent is None or not consent.marketing_consent):
            d.status = "BLOCKED"
            d.error_detail = "Marketing consent not granted."
            blocked += 1
            continue

        d.status = "SENT"
        d.sent_at = now
        sent += 1
    db.commit()
    return {"processed": len(queued), "sent": sent, "blocked": blocked}


def run_subscription_lifecycle_sweep(db: Session, *, tenant_id: str) -> dict[str, Any]:
    """Check expired paid subscriptions and queue renewal notifications."""
    now = _utcnow()
    subs = db.execute(
        select(CaravanSubscriptionRecord).where(
            CaravanSubscriptionRecord.tenant_id == tenant_id,
            CaravanSubscriptionRecord.plan_tier != "FREE",
        )
    ).scalars().all()
    checked = 0
    expiring_notified = 0
    for s in subs:
        checked += 1
        end = s.current_period_end
        if end is not None:
            end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
            if end_utc <= now and s.status == "ACTIVE":
                s.status = "PAST_DUE"
                expiring_notified += 1
                db.add(
                    CaravanNotificationDeliveryRecord(
                        delivery_id=f"cdlv_{uuid.uuid4().hex[:14]}",
                        tenant_id=tenant_id,
                        account_id=s.account_id,
                        channel="EMAIL",
                        event_type="SUBSCRIPTION_STATUS",
                        recipient="",
                        subject="Caravan subscription renewal required",
                        body=f"Your Caravan {s.plan_tier} subscription period has ended.",
                        status="QUEUED",
                    )
                )
    db.commit()
    return {"checked": checked, "past_due_flagged": expiring_notified}
