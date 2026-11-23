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

