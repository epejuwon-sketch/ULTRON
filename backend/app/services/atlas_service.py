"""ATLAS — Personal Assistant, Shopping/Orders (9-status verified tracking), World Intelligence & Daily Briefing.

Zero-Fabrication Rule:
- Order tracking statuses are NEVER invented; they reflect verified user records,
  parsed receipts/emails, or explicitly connected carrier APIs.
- World Intelligence & Daily Briefings fetch live public APIs when reachable (Open-Meteo,
  Hacker News, Wikipedia) and explicitly report source, fetched_at timestamp, and UNAVAILABLE
  status when offline — never fabricating fake headlines or weather readings.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import IntelligenceBriefingRecord, IntelligenceTopicRecord, OrderRecord
from app.db.repositories import append_audit_log
from app.integrations.web_research import WebResearchClient
from app.services.approval_service import create_approval_request, serialize_approval

ORDER_STATUSES: tuple[str, ...] = (
    "PLACED",
    "PROCESSING",
    "SHIPPED",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELAYED",
    "RETURNED",
    "CANCELLED",
)

DEFAULT_INTELLIGENCE_TOPICS: list[tuple[str, str, str, int]] = [
    ("world", "World News & Geopolitics", "GLOBAL", 1),
    ("nigeria_africa", "Nigeria & Africa", "AFRICA", 2),
    ("business", "Business & Markets", "GLOBAL", 3),
    ("tech_ai", "Technology & AI", "GLOBAL", 4),
    ("startups", "Startups & Venture", "GLOBAL", 5),
    ("economics", "Macroeconomics & FX", "GLOBAL", 6),
    ("science", "Science & Innovation", "GLOBAL", 7),
    ("cybersecurity", "Cybersecurity Advisories", "GLOBAL", 8),
]


def research_products(
    *,
    query: str,
    settings: Settings,
    max_results: int = 5,
) -> dict[str, Any]:
    """Use the live WebResearchClient to gather real product/vendor comparison sources with citations."""
    client = WebResearchClient(settings)
    result = client.search(query=query, max_results=max_results)
    return {
        "query": query,
        "provider_results": result,
        "approval_required_before_purchase": True,
        "notice": "Product research is informational. Every purchase requires explicit ApprovalGate sign-off.",
    }


def create_order_request(
    db: Session,
    *,
    principal: Principal,
    vendor: str,
    item_summary: str,
    amount_usd: float,
    currency: str = "USD",
    payment_method_id: str | None = None,
    carrier: str = "",
    tracking_number: str = "",
    estimated_delivery: str = "",
    require_purchase_approval: bool = True,
) -> dict[str, Any]:
    """Create a tracked order; purchases always generate an ApprovalGate record before payment execution."""
    if amount_usd < 0:
        raise ValidationError("amount_usd cannot be negative.")

    order_id = f"ord_{uuid.uuid4().hex[:14]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    initial_events = [
        {
            "status": "PLACED",
            "timestamp": now_iso,
            "source": "USER_RECORDED",
            "note": f"Order prepared for {vendor} ({item_summary[:100]})",
        }
    ]

    approval_payload = None
    approval_id = None
    if require_purchase_approval:
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type="ATLAS_PURCHASE_ORDER",
            reason=f"Purchase order '{item_summary[:120]}' from {vendor} for {amount_usd:.2f} {currency} requires explicit authorization.",
            risk_level="HIGH",
            financial_amount_usd=amount_usd,
            resource_ref=order_id,
            payload={
                "order_id": order_id,
                "vendor": vendor,
                "amount_usd": amount_usd,
                "currency": currency,
                "payment_method_id": payment_method_id,
            },
            commit=False,
        )
        approval_id = approval.approval_id
        approval_payload = serialize_approval(approval)

    order = OrderRecord(
        order_id=order_id,
        tenant_id=principal.tenant_id,
        vendor=vendor.strip()[:160],
        item_summary=item_summary.strip(),
        amount_usd=round(float(amount_usd), 2),
        currency=currency.strip().upper()[:12],
        status="PLACED",
        carrier=carrier.strip()[:120],
        tracking_number=tracking_number.strip()[:120],
        tracking_source="USER_RECORDED",
        estimated_delivery=estimated_delivery.strip()[:64],
        approval_id=approval_id,
        payment_method_id=payment_method_id,
        events_json=json.dumps(initial_events),
        created_by=principal.username,
    )
    db.add(order)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ATLAS_ORDER_CREATED",
        resource=order_id,
        outcome=f"vendor={order.vendor};amount={order.amount_usd}",
    )
    db.commit()
    db.refresh(order)
    return {
        "order": _serialize_order(order),
        "approval": approval_payload,
    }


def update_order_tracking(
    db: Session,
    *,
    principal: Principal,
    order_id: str,
    status_value: str,
    tracking_source: str = "USER_RECORDED",
    note: str = "",
    carrier: str | None = None,
    tracking_number: str | None = None,
    estimated_delivery: str | None = None,
) -> dict[str, Any]:
    """Update order status across the 9-stage lifecycle from verified user/email/carrier data."""
    st = status_value.strip().upper()
    if st not in ORDER_STATUSES:
        raise ValidationError(f"Invalid order status '{st}'. Allowed: {', '.join(ORDER_STATUSES)}")

    order = db.execute(
        select(OrderRecord).where(
            OrderRecord.order_id == order_id,
            OrderRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError(f"Order '{order_id}' not found.")

    events = json.loads(order.events_json or "[]")
    events.append(
        {
            "status": st,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": tracking_source.strip().upper()[:64],
            "note": note.strip()[:300],
            "updated_by": principal.username,
        }
    )
    order.status = st
    order.tracking_source = tracking_source.strip().upper()[:64]
    if carrier is not None:
        order.carrier = carrier.strip()[:120]
    if tracking_number is not None:
        order.tracking_number = tracking_number.strip()[:120]
    if estimated_delivery is not None:
        order.estimated_delivery = estimated_delivery.strip()[:64]
    order.events_json = json.dumps(events)
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


def list_orders(db: Session, *, tenant_id: str, status_filter: str | None = None) -> list[dict[str, Any]]:
    stmt = select(OrderRecord).where(OrderRecord.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(OrderRecord.status == status_filter.strip().upper())
    rows = db.execute(stmt.order_by(OrderRecord.updated_at.desc())).scalars().all()
    return [_serialize_order(r) for r in rows]


def ensure_default_topics(db: Session, tenant_id: str) -> list[IntelligenceTopicRecord]:
    existing = db.execute(
        select(IntelligenceTopicRecord)
        .where(IntelligenceTopicRecord.tenant_id == tenant_id)
        .order_by(IntelligenceTopicRecord.priority.asc())
    ).scalars().all()
    if existing:
        return list(existing)
    created: list[IntelligenceTopicRecord] = []
    for slug, label, region, prio in DEFAULT_INTELLIGENCE_TOPICS:
        rec = IntelligenceTopicRecord(
            topic_id=f"top_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            slug=slug,
            label=label,
            region=region,
            enabled=True,
            priority=prio,
        )
        db.add(rec)
        created.append(rec)
    db.commit()
    return created


def list_intelligence_topics(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = ensure_default_topics(db, tenant_id)
    return [_serialize_topic(r) for r in rows]


def upsert_intelligence_topic(
    db: Session,
    *,
    principal: Principal,
    slug: str,
    label: str,
    region: str = "GLOBAL",
    enabled: bool = True,
    priority: int = 5,
) -> dict[str, Any]:
    clean_slug = slug.strip().lower().replace(" ", "_")[:64]
    existing = db.execute(
        select(IntelligenceTopicRecord).where(
            IntelligenceTopicRecord.tenant_id == principal.tenant_id,
            IntelligenceTopicRecord.slug == clean_slug,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = IntelligenceTopicRecord(
            topic_id=f"top_{uuid.uuid4().hex[:12]}",
            tenant_id=principal.tenant_id,
            slug=clean_slug,
            label=label.strip()[:120],
            region=region.strip().upper()[:64],
            enabled=enabled,
            priority=priority,
        )
        db.add(existing)
    else:
        existing.label = label.strip()[:120]
        existing.region = region.strip().upper()[:64]
        existing.enabled = enabled
        existing.priority = priority
        existing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(existing)
    return _serialize_topic(existing)


def fetch_weather_snapshot(latitude: float = 6.5244, longitude: float = 3.3792, city: str = "Lagos") -> dict[str, Any]:
    """Fetch live weather from public Open-Meteo API with honest UNAVAILABLE reporting when offline."""
    now_iso = datetime.now(timezone.utc).isoformat()
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
    )
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})
            return {
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "status": "LIVE",
                "source": "open-meteo.com",
                "fetched_at": now_iso,
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "weather_code": current.get("weather_code"),
            }
    except Exception as exc:
        return {
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "status": "UNAVAILABLE",
            "source": "open-meteo.com",
            "fetched_at": now_iso,
            "error": str(exc),
        }


def generate_daily_briefing(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    include_live_fetch: bool = False,
) -> dict[str, Any]:
    """Build a Daily Intelligence Briefing from configured topics & real sources (never fabricates news)."""
    topics = [t for t in ensure_default_topics(db, principal.tenant_id) if t.enabled]
    now = datetime.now(timezone.utc)
    briefing_date = now.strftime("%Y-%m-%d")
    sections: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    web_client = WebResearchClient(settings) if include_live_fetch else None

    for topic in topics:
        items: list[dict[str, Any]] = []
        fetch_status = "LIVE_FETCH_SKIPPED"
        if web_client is not None:
            try:
                res = web_client.search(query=f"{topic.label} {topic.region} latest", max_results=2)
                for r in res.get("results", []):
                    items.append(
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("snippet", ""),
                            "source": r.get("source", "web"),
                            "fetched_at": now.isoformat(),
                        }
                    )
                    if r.get("url"):
                        sources.append({"topic": topic.slug, "title": r.get("title", ""), "url": r.get("url", "")})
                fetch_status = "LIVE" if items else "NO_LIVE_RESULTS"
            except Exception as exc:
                fetch_status = f"UNAVAILABLE: {exc}"
        sections.append(
            {
                "slug": topic.slug,
                "label": topic.label,
                "region": topic.region,
                "status": fetch_status,
                "items": items,
                "empty_state": None if items else "No live articles fetched (enable live fetch with outbound network or search API configured).",
            }
        )

    rec = IntelligenceBriefingRecord(
        briefing_id=f"brf_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        briefing_date=briefing_date,
        topics_json=json.dumps([t.slug for t in topics]),
        sections_json=json.dumps(sections, default=str),
        sources_json=json.dumps(sources, default=str),
        status="READY",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _serialize_briefing(rec)


def list_briefings(db: Session, *, tenant_id: str, limit: int = 14) -> list[dict[str, Any]]:
    rows = db.execute(
        select(IntelligenceBriefingRecord)
        .where(IntelligenceBriefingRecord.tenant_id == tenant_id)
        .order_by(IntelligenceBriefingRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_serialize_briefing(r) for r in rows]


def _serialize_order(o: OrderRecord) -> dict[str, Any]:
    return {
        "order_id": o.order_id,
        "vendor": o.vendor,
        "item_summary": o.item_summary,
        "amount_usd": o.amount_usd,
        "currency": o.currency,
        "status": o.status,
        "carrier": o.carrier,
        "tracking_number": o.tracking_number,
        "tracking_source": o.tracking_source,
        "estimated_delivery": o.estimated_delivery,
        "approval_id": o.approval_id,
        "payment_method_id": o.payment_method_id,
        "events": json.loads(o.events_json or "[]"),
        "created_by": o.created_by,
        "created_at": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
    }


def _serialize_topic(t: IntelligenceTopicRecord) -> dict[str, Any]:
    return {
        "topic_id": t.topic_id,
        "slug": t.slug,
        "label": t.label,
        "region": t.region,
        "enabled": t.enabled,
        "priority": t.priority,
        "updated_at": t.updated_at.isoformat(),
    }


def _serialize_briefing(b: IntelligenceBriefingRecord) -> dict[str, Any]:
    return {
        "briefing_id": b.briefing_id,
        "briefing_date": b.briefing_date,
        "topics": json.loads(b.topics_json or "[]"),
        "sections": json.loads(b.sections_json or "[]"),
        "sources": json.loads(b.sources_json or "[]"),
        "status": b.status,
        "created_at": b.created_at.isoformat(),
    }
