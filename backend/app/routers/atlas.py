"""ATLAS Personal Assistant, Orders, World Intelligence & Daily Briefing API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.atlas_service import (
    ORDER_STATUSES,
    create_order_request,
    fetch_weather_snapshot,
    generate_daily_briefing,
    list_briefings,
    list_intelligence_topics,
    list_orders,
    research_products,
    update_order_tracking,
    upsert_intelligence_topic,
)

router = APIRouter(prefix="/api/v1/atlas", tags=["ATLAS Personal & World Intelligence"])


class ProductResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=10)


class CreateOrderRequest(BaseModel):
    vendor: str = Field(min_length=2, max_length=160)
    item_summary: str = Field(min_length=2, max_length=1000)
    amount_usd: float = Field(ge=0.0)
    currency: str = Field(default="USD", max_length=12)
    payment_method_id: str | None = None
    carrier: str = Field(default="", max_length=120)
    tracking_number: str = Field(default="", max_length=120)
    estimated_delivery: str = Field(default="", max_length=64)
    require_purchase_approval: bool = True


class UpdateOrderTrackingRequest(BaseModel):
    status: str = Field(min_length=4, max_length=32)
    tracking_source: str = Field(default="USER_RECORDED", max_length=64)
    note: str = Field(default="", max_length=300)
    carrier: str | None = None
    tracking_number: str | None = None
    estimated_delivery: str | None = None


class UpsertTopicRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=2, max_length=120)
    region: str = Field(default="GLOBAL", max_length=64)
    enabled: bool = True
    priority: int = Field(default=5, ge=1, le=100)


class GenerateBriefingRequest(BaseModel):
    include_live_fetch: bool = False


@router.post("/shopping/research")
def api_product_research(
    body: ProductResearchRequest,
    _principal: Principal = Depends(require_perm("atlas:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return research_products(query=body.query, settings=settings, max_results=body.max_results)


@router.get("/orders")
def api_list_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    principal: Principal = Depends(require_perm("atlas:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_orders(db, tenant_id=principal.tenant_id, status_filter=status_filter)
    return {
        "total": len(items),
        "supported_statuses": list(ORDER_STATUSES),
        "orders": items,
        "empty_state": None if items else "No orders recorded yet.",
    }


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def api_create_order(
    body: CreateOrderRequest,
    principal: Principal = Depends(require_perm("atlas:write")),
    db: Session = Depends(get_db),
) -> dict:
    return create_order_request(
        db,
        principal=principal,
        vendor=body.vendor,
        item_summary=body.item_summary,
        amount_usd=body.amount_usd,
        currency=body.currency,
        payment_method_id=body.payment_method_id,
        carrier=body.carrier,
        tracking_number=body.tracking_number,
        estimated_delivery=body.estimated_delivery,
        require_purchase_approval=body.require_purchase_approval,
    )


@router.patch("/orders/{order_id}/tracking")
def api_update_order_tracking(
    order_id: str,
    body: UpdateOrderTrackingRequest,
    principal: Principal = Depends(require_perm("atlas:write")),
    db: Session = Depends(get_db),
) -> dict:
    return update_order_tracking(
        db,
        principal=principal,
        order_id=order_id,
        status_value=body.status,
        tracking_source=body.tracking_source,
        note=body.note,
        carrier=body.carrier,
        tracking_number=body.tracking_number,
        estimated_delivery=body.estimated_delivery,
    )


@router.get("/intelligence/topics")
def api_list_topics(
    principal: Principal = Depends(require_perm("atlas:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_intelligence_topics(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "topics": items}


@router.put("/intelligence/topics")
def api_upsert_topic(
    body: UpsertTopicRequest,
    principal: Principal = Depends(require_perm("atlas:write")),
    db: Session = Depends(get_db),
) -> dict:
    return upsert_intelligence_topic(
        db,
        principal=principal,
        slug=body.slug,
        label=body.label,
        region=body.region,
        enabled=body.enabled,
        priority=body.priority,
    )


@router.get("/intelligence/weather")
def api_weather(
    latitude: float = Query(default=6.5244, ge=-90.0, le=90.0),
    longitude: float = Query(default=3.3792, ge=-180.0, le=180.0),
    city: str = Query(default="Lagos", max_length=120),
    _principal: Principal = Depends(require_perm("atlas:read")),
) -> dict:
    return fetch_weather_snapshot(latitude=latitude, longitude=longitude, city=city)


@router.post("/briefings/generate", status_code=status.HTTP_201_CREATED)
def api_generate_briefing(
    body: GenerateBriefingRequest,
    principal: Principal = Depends(require_perm("atlas:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return generate_daily_briefing(
        db,
        principal=principal,
        settings=settings,
        include_live_fetch=body.include_live_fetch,
    )


@router.get("/briefings")
def api_list_briefings(
    limit: int = Query(default=14, ge=1, le=60),
    principal: Principal = Depends(require_perm("atlas:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_briefings(db, tenant_id=principal.tenant_id, limit=limit)
    return {"total": len(items), "briefings": items}
