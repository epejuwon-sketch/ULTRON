"""CARAVAN — Business Intelligence Analytics API routes (Zero Fabricated Metrics)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.platform_modules_service import (
    VALID_CARAVAN_EVENTS,
    get_caravan_analytics_summary,
    record_caravan_event,
)

router = APIRouter(prefix="/api/v1/caravan", tags=["CARAVAN Business Intelligence"])


class RecordCaravanEventRequest(BaseModel):
    event_type: str = Field(min_length=3, max_length=64)
    country: str = Field(default="Nigeria", max_length=80)
    city: str = Field(default="", max_length=120)
    acquisition_source: str = Field(default="DIRECT", max_length=80)
    amount_usd: float = Field(default=0.0, ge=0.0)
    count_value: int = Field(default=1, ge=1, le=100000)
    venture: str = Field(default="CARAVAN", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/events", status_code=status.HTTP_201_CREATED)
def api_record_caravan_event(
    body: RecordCaravanEventRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    return record_caravan_event(
        db,
        principal=principal,
        event_type=body.event_type,
        country=body.country,
        city=body.city,
        acquisition_source=body.acquisition_source,
        amount_usd=body.amount_usd,
        count_value=body.count_value,
        venture=body.venture,
        metadata=body.metadata,
    )


@router.get("/summary")
def api_caravan_summary(
    venture: str = Query(default="CARAVAN", max_length=80),
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    summary = get_caravan_analytics_summary(db, tenant_id=principal.tenant_id, venture=venture)
    summary["supported_event_types"] = sorted(VALID_CARAVAN_EVENTS)
    return summary


class CaravanBridgeActionRequest(BaseModel):
    action_category: str = Field(min_length=3, max_length=64)
    summary: str = Field(min_length=3, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/bridge/status")
def api_caravan_bridge_status(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.db.models import IntegrationConnectionRecord
    from app.services.operational_control_service import get_operational_control_policy

    conn = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == "caravan",
        )
    ).scalar_one_or_none()
    policy = get_operational_control_policy(db, tenant_id=principal.tenant_id)
    return {
        "bridge": "ultron-caravan-s2s",
        "caravan_repo_present": False,
        "connection_status": conn.status if conn is not None else "UNCONFIGURED",
        "degraded_mode_supported": True,
        "degraded_mode_note": "Caravan operates independently if ULTRON intelligence is temporarily unavailable.",
        "operational_control": policy,
    }


@router.post("/bridge/action")
def api_caravan_bridge_action(
    body: CaravanBridgeActionRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.operational_control_service import evaluate_operational_action

    return evaluate_operational_action(
        db,
        principal=principal,
        action_category=body.action_category,
        summary=body.summary,
        venture="CARAVAN",
        payload=body.payload,
    )


class CreateFundingSourceRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source_type: str = Field(default="PUBLIC_PORTAL", max_length=32)
    base_url: str = Field(min_length=4, max_length=500)
    connector_id: str | None = Field(default=None, max_length=64)
    verification_policy: str = Field(default="MANUAL_REVIEW", max_length=64)


class CreateOpportunityRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    provider_org: str = Field(min_length=2, max_length=180)
    funding_type: str = Field(default="GRANT", max_length=32)
    source_url: str = Field(min_length=8, max_length=500)
    eligibility_requirements: str = Field(min_length=4)
    geographic_restrictions: str = Field(default="Global / See source", max_length=240)
    amount_display: str = Field(default="Not specified by source", max_length=120)
    currency: str = Field(default="USD", max_length=16)
    deadline_at: str | None = None
    supporting_evidence: str = Field(default="")
    source_id: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list)


class VerifyOpportunityRequest(BaseModel):
    verification_status: str = Field(min_length=3, max_length=24)
    supporting_evidence: str = Field(default="")


class EligibilityRequest(BaseModel):
    opportunity_id: str = Field(min_length=4, max_length=64)


class CreateApplicationRequest(BaseModel):
    opportunity_id: str = Field(min_length=4, max_length=64)
    notes: str = Field(default="")


class UpdateApplicationRequest(BaseModel):
    status: str | None = Field(default=None, max_length=32)
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class SaveOpportunityRequest(BaseModel):
    opportunity_id: str = Field(min_length=4, max_length=64)
    notes: str = Field(default="")


class UpdateAccountRequest(BaseModel):
    organization_name: str | None = Field(default=None, max_length=180)
    entity_type: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=80)
    sector: str | None = Field(default=None, max_length=80)
    stage: str | None = Field(default=None, max_length=64)
    annual_revenue_band: str | None = Field(default=None, max_length=64)
    profile_summary: str | None = None
    onboarding_completed: bool | None = None


class UpdateSubscriptionRequest(BaseModel):
    plan_tier: str = Field(default="FREE", max_length=32)
    enable_live_payments: bool = False


class CreateSupportTicketRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=3)
    category: str = Field(default="GENERAL", max_length=64)
    priority: str = Field(default="NORMAL", max_length=24)


@router.get("/overview")
def api_caravan_overview(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import get_caravan_overview

    return get_caravan_overview(db, principal=principal)


@router.get("/sources")
def api_list_caravan_sources(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_funding_sources

    items = list_funding_sources(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "sources": items}


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def api_register_caravan_source(
    body: CreateFundingSourceRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import register_funding_source

    return register_funding_source(
        db,
        principal=principal,
        name=body.name,
        source_type=body.source_type,
        base_url=body.base_url,
        connector_id=body.connector_id,
        verification_policy=body.verification_policy,
    )


@router.get("/opportunities")
def api_list_caravan_opportunities(
    query: str = Query(default="", max_length=120),
    funding_type: str = Query(default="", max_length=32),
    verification_status: str = Query(default="", max_length=24),
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_funding_opportunities

    items = list_funding_opportunities(
        db,
        tenant_id=principal.tenant_id,
        query=query,
        funding_type=funding_type,
        verification_status=verification_status,
    )
    return {"total": len(items), "opportunities": items}


@router.post("/opportunities", status_code=status.HTTP_201_CREATED)
def api_create_caravan_opportunity(
    body: CreateOpportunityRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime

    from app.services.caravan_product_service import create_funding_opportunity

    deadline = datetime.fromisoformat(body.deadline_at) if body.deadline_at else None
    return create_funding_opportunity(
        db,
        principal=principal,
        title=body.title,
        provider_org=body.provider_org,
        funding_type=body.funding_type,
        source_url=body.source_url,
        eligibility_requirements=body.eligibility_requirements,
        geographic_restrictions=body.geographic_restrictions,
        amount_display=body.amount_display,
        currency=body.currency,
        deadline_at=deadline,
        supporting_evidence=body.supporting_evidence,
        source_id=body.source_id,
        tags=body.tags,
    )


@router.get("/opportunities/{opportunity_id}")
def api_get_caravan_opportunity(
    opportunity_id: str,
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import get_funding_opportunity

    return get_funding_opportunity(db, tenant_id=principal.tenant_id, opportunity_id=opportunity_id)


@router.post("/opportunities/{opportunity_id}/verify")
def api_verify_caravan_opportunity(
    opportunity_id: str,
    body: VerifyOpportunityRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import verify_funding_opportunity

    return verify_funding_opportunity(
        db,
        principal=principal,
        opportunity_id=opportunity_id,
        verification_status=body.verification_status,
        supporting_evidence=body.supporting_evidence,
    )


@router.get("/recommendations")
def api_caravan_recommendations(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import get_personalized_recommendations

    items = get_personalized_recommendations(db, principal=principal)
    return {"total": len(items), "recommendations": items}


@router.get("/assessments")
def api_list_caravan_assessments(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_eligibility_assessments

    items = list_eligibility_assessments(db, principal=principal)
    return {"total": len(items), "assessments": items}


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def api_run_caravan_assessment(
    body: EligibilityRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.core.config import get_settings
    from app.services.caravan_product_service import run_neon_eligibility_assessment

    return run_neon_eligibility_assessment(
        db,
        principal=principal,
        opportunity_id=body.opportunity_id,
        settings=get_settings(),
    )


@router.get("/applications")
def api_list_caravan_applications(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_applications

    items = list_applications(db, principal=principal)
    return {"total": len(items), "applications": items}


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def api_create_caravan_application(
    body: CreateApplicationRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import create_application

    return create_application(db, principal=principal, opportunity_id=body.opportunity_id, notes=body.notes)


@router.patch("/applications/{application_id}")
def api_update_caravan_application(
    application_id: str,
    body: UpdateApplicationRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import update_application

    return update_application(
        db,
        principal=principal,
        application_id=application_id,
        status_value=body.status,
        progress_pct=body.progress_pct,
        notes=body.notes,
    )


@router.get("/saved")
def api_list_caravan_saved(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_saved_opportunities

    items = list_saved_opportunities(db, principal=principal)
    return {"total": len(items), "saved": items}


@router.post("/saved", status_code=status.HTTP_201_CREATED)
def api_save_caravan_opportunity(
    body: SaveOpportunityRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import save_opportunity

    return save_opportunity(db, principal=principal, opportunity_id=body.opportunity_id, notes=body.notes)


@router.delete("/saved/{saved_id}")
def api_remove_caravan_saved(
    saved_id: str,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import remove_saved_opportunity

    return remove_saved_opportunity(db, principal=principal, saved_id=saved_id)


@router.put("/account")
def api_update_caravan_account(
    body: UpdateAccountRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import update_customer_account

    return update_customer_account(
        db,
        principal=principal,
        organization_name=body.organization_name,
        entity_type=body.entity_type,
        country=body.country,
        sector=body.sector,
        stage=body.stage,
        annual_revenue_band=body.annual_revenue_band,
        profile_summary=body.profile_summary,
        onboarding_completed=body.onboarding_completed,
    )


@router.put("/subscription")
def api_update_caravan_subscription(
    body: UpdateSubscriptionRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import update_subscription_plan

    return update_subscription_plan(
        db,
        principal=principal,
        plan_tier=body.plan_tier,
        enable_live_payments=body.enable_live_payments,
    )


@router.get("/support/tickets")
def api_list_caravan_tickets(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_support_tickets

    items = list_support_tickets(db, principal=principal)
    return {"total": len(items), "tickets": items}


@router.post("/support/tickets", status_code=status.HTTP_201_CREATED)
def api_create_caravan_ticket(
    body: CreateSupportTicketRequest,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import create_support_ticket

    return create_support_ticket(
        db,
        principal=principal,
        subject=body.subject,
        message=body.message,
        category=body.category,
        priority=body.priority,
    )


@router.get("/notifications")
def api_list_caravan_notifications(
    principal: Principal = Depends(require_perm("caravan:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import list_notifications

    items = list_notifications(db, principal=principal)
    return {"total": len(items), "notifications": items}


@router.post("/notifications/{notification_id}/read")
def api_read_caravan_notification(
    notification_id: str,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import mark_notification_read

    return mark_notification_read(db, principal=principal, notification_id=notification_id)


@router.post("/sources/{source_id}/verify")
def api_verify_caravan_source_live(
    source_id: str,
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import verify_funding_source_via_argon

    return verify_funding_source_via_argon(db, principal=principal, source_id=source_id)


@router.post("/opportunities/sweep-expired")
def api_sweep_expired_caravan_opportunities(
    principal: Principal = Depends(require_perm("caravan:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caravan_product_service import sweep_expired_opportunities

    return sweep_expired_opportunities(db, principal=principal)

