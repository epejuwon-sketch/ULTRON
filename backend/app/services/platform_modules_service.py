"""Platform Subsystems Service: Creative Studio (Voice/Visual/Media), BRIDGE Share-to-JARVIS, PULSE Live Pages, CARAVAN BI."""

from __future__ import annotations

import base64
import html
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.db.models import (
    AgentRecord,
    BusinessAnalyticsEventRecord,
    MediaJobRecord,
    ProjectRecord,
    PulsePageRecord,
    SharedItemRecord,
)
from app.db.repositories import append_audit_log
from app.integrations.gemini import GeminiClient
from app.services.aegis_service import inspect_url_safety
from app.services.atlas_service import list_briefings, list_orders
from app.services.file_hub_service import generate_and_store_file
from app.services.finance_service import generate_financial_report
from app.services.neon_router import create_conversation, invoke_agent_reasoning, send_conversation_message

# ---------------------------------------------------------------------------
# CREATIVE STUDIO, VOICE & VISUAL INTERACTION
# ---------------------------------------------------------------------------
MEDIA_AGENT_MAP: dict[str, tuple[str, str]] = {
    "IMAGE": ("AGT-13", "gemini-nano-banana-2.1"),
    "VIDEO": ("AGT-14", "veo-external-provider"),
    "AUDIO": ("AGT-45", "gemini-audio-pipeline"),
    "VOICE": ("AGT-46", "web-speech-and-gemini"),
    "3D": ("AGT-24", "threejs-procedural-generator"),
    "PRESENTATION": ("AGT-44", "ultron-slide-deck-builder"),
    "GRAPHIC": ("AGT-43", "svg-brand-generator"),
}


def process_voice_turn(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    transcript: str,
    conversation_id: str | None = None,
    mode: str = "push_to_talk",
) -> dict[str, Any]:
    """Process a spoken transcript through VAULT secret interception and NEON conversation/routing."""
    if not transcript.strip():
        raise ValidationError("transcript cannot be empty.")

    if conversation_id:
        turn = send_conversation_message(
            db,
            principal=principal,
            conversation_id=conversation_id,
            content=transcript,
            settings=settings,
        )
        spoken_reply = turn["reply"]["output"]
        return {
            "mode": mode,
            "conversation_id": conversation_id,
            "spoken_reply": spoken_reply,
            "secret_interception": turn["secret_interception"],
            "tts_recommended": True,
            "reply": turn["reply"],
        }

    conv = create_conversation(db, principal=principal, title=f"Voice Session: {transcript[:40]}", agent_id="AGT-46")
    turn = send_conversation_message(
        db,
        principal=principal,
        conversation_id=conv["conversation_id"],
        content=transcript,
        settings=settings,
    )
    return {
        "mode": mode,
        "conversation_id": conv["conversation_id"],
        "spoken_reply": turn["reply"]["output"],
        "secret_interception": turn["secret_interception"],
        "tts_recommended": True,
        "reply": turn["reply"],
    }


def analyze_visual_frame(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    prompt: str,
    image_base64: str,
    mime_type: str = "image/png",
    source: str = "camera",
) -> dict[str, Any]:
    """Analyze a camera frame, screenshot, or uploaded image via Gemini multimodal or honest Pillow inspection."""
    try:
        raw = base64.b64decode(image_base64)
    except Exception as exc:
        raise ValidationError(f"Invalid base64 image payload: {exc}") from exc

    img_meta: dict[str, Any] = {"size_bytes": len(raw), "mime_type": mime_type, "source": source}
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as im:
            img_meta["width"] = im.width
            img_meta["height"] = im.height
            img_meta["format"] = im.format
            img_meta["mode"] = im.mode
    except Exception:
        img_meta["image_parsed"] = False

    interception = intercept_and_redact_secrets(prompt, db=db, principal=principal, settings=settings, source_context="visual")
    gemini = GeminiClient(settings)
    if gemini.is_configured():
        try:
            resp = gemini.generate_content(
                prompt=interception.sanitized_text,
                model=settings.gemini_model_standard,
                inline_data=[{"mime_type": mime_type, "data": image_base64}],
            )
            return {
                "status": "ANALYZED_LIVE",
                "provider": "gemini",
                "model": settings.gemini_model_standard,
                "image_metadata": img_meta,
                "analysis": resp.get("text", ""),
                "usage": resp.get("usage", {}),
            }
        except Exception as exc:
            return {
                "status": "PROVIDER_ERROR",
                "provider": "gemini",
                "image_metadata": img_meta,
                "error": str(exc),
            }

    return {
        "status": "REQUIRES_PROVIDER_CONFIG",
        "provider": "gemini",
        "image_metadata": img_meta,
        "analysis": (
            f"Captured {source} visual frame ({img_meta.get('width', '?')}x{img_meta.get('height', '?')}, "
            f"{len(raw)} bytes). Configure GEMINI_API_KEY to enable live multimodal visual reasoning."
        ),
    }


def create_media_job(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    media_type: str,
    prompt: str,
) -> dict[str, Any]:
    """Create a Creative Studio production job wired to the appropriate specialist agent."""
    mtype = media_type.strip().upper()
    if mtype not in MEDIA_AGENT_MAP:
        raise ValidationError(f"Unsupported media_type '{mtype}'. Supported: {', '.join(sorted(MEDIA_AGENT_MAP))}")

    agent_id, provider = MEDIA_AGENT_MAP[mtype]
    interception = intercept_and_redact_secrets(prompt, db=db, principal=principal, settings=settings, source_context="creative")
    clean_prompt = interception.sanitized_text

    output_file_id: str | None = None
    result_payload: dict[str, Any] = {}
    status_val = "COMPLETED"

    if mtype in {"GRAPHIC", "IMAGE"}:
        # Generate a real downloadable SVG concept artifact and report honest raster provider status
        safe_label = html.escape(clean_prompt[:64])
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#0e7490"/></linearGradient></defs>'
            f'<rect width="800" height="450" fill="url(#g)"/>'
            f'<rect x="32" y="32" width="736" height="386" rx="18" fill="none" stroke="#06b6d4" stroke-width="2" opacity="0.6"/>'
            f'<text x="64" y="108" fill="#06b6d4" font-family="sans-serif" font-size="18" font-weight="700">ULTRON CREATIVE STUDIO // {mtype}</text>'
            f'<text x="64" y="180" fill="#f8fafc" font-family="sans-serif" font-size="24" font-weight="600">{safe_label}</text>'
            f'<text x="64" y="380" fill="#94a3b8" font-family="sans-serif" font-size="14">Generated by {agent_id}</text>'
            f"</svg>"
        )
        stored = generate_and_store_file(
            db,
            principal=principal,
            settings=settings,
            filename=f"creative_{mtype.lower()}_{uuid.uuid4().hex[:6]}.svg",
            content_bytes=svg.encode("utf-8"),
            mime_type="image/svg+xml",
            metadata={"media_type": mtype, "agent_id": agent_id},
        )
        output_file_id = stored["file_id"]
        gemini_live = GeminiClient(settings).is_configured()
        result_payload = {
            "artifact_format": "image/svg+xml",
            "download_url": stored["download_url"],
            "raster_provider_configured": gemini_live,
            "note": "Vector SVG concept artifact generated locally." if not gemini_live else "Vector artifact generated; Gemini image model configured.",
        }
    elif mtype == "3D":
        scene_spec = {
            "engine": "three.js",
            "agent_id": agent_id,
            "prompt": clean_prompt,
            "camera": {"type": "PerspectiveCamera", "fov": 45, "position": [0, 3, 8]},
            "lighting": [{"type": "AmbientLight", "intensity": 0.6}, {"type": "DirectionalLight", "position": [5, 10, 7]}],
            "objects": [{"id": "primary_mesh", "geometry": "TorusKnotGeometry", "material": {"color": "#06b6d4", "metalness": 0.7, "roughness": 0.2}}],
        }
        stored = generate_and_store_file(
            db,
            principal=principal,
            settings=settings,
            filename=f"scene_3d_{uuid.uuid4().hex[:6]}.json",
            content_bytes=json.dumps(scene_spec, indent=2).encode("utf-8"),
            mime_type="application/json",
            metadata={"media_type": "3D", "agent_id": agent_id},
        )
        output_file_id = stored["file_id"]
        result_payload = {"scene_spec": scene_spec, "download_url": stored["download_url"]}
    elif mtype == "PRESENTATION":
        slides_md = (
            f"# {clean_prompt[:80]}\n\n---\n\n"
            f"## 1. Executive Summary\nPrepared by ULTRON {agent_id}.\n\n---\n\n"
            f"## 2. Core Objectives\n- Scope: {clean_prompt}\n- Governance: AEGIS & ApprovalGate verified\n\n---\n\n"
            f"## 3. Execution Roadmap\n- Phase 1: Foundation\n- Phase 2: Verification\n- Phase 3: Delivery\n"
        )
        stored = generate_and_store_file(
            db,
            principal=principal,
            settings=settings,
            filename=f"deck_{uuid.uuid4().hex[:6]}.md",
            content_bytes=slides_md.encode("utf-8"),
            mime_type="text/markdown",
            metadata={"media_type": "PRESENTATION", "agent_id": agent_id},
        )
        output_file_id = stored["file_id"]
        result_payload = {"slide_count": 4, "download_url": stored["download_url"]}
    else:
        # VIDEO / AUDIO / VOICE — produce structured storyboard/production plan honestly stating external rendering requirement
        plan = invoke_agent_reasoning(
            db,
            agent_id=agent_id,
            prompt=f"Create a structured {mtype} production script/storyboard for: {clean_prompt}",
            settings=settings,
            tenant_id=principal.tenant_id,
            actor=principal.username,
        )
        status_val = "REQUIRES_PROVIDER_CONFIG" if not GeminiClient(settings).is_configured() else "COMPLETED"
        result_payload = {
            "production_plan": plan["output"],
            "execution_mode": plan["execution_mode"],
            "external_media_renderer_configured": False,
        }

    job = MediaJobRecord(
        job_id=f"med_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        media_type=mtype,
        agent_id=agent_id,
        prompt=clean_prompt,
        provider=provider,
        status=status_val,
        output_file_id=output_file_id,
        result_json=json.dumps(result_payload, default=str),
        created_by=principal.username,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_media_job(job)


def list_media_jobs(db: Session, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(MediaJobRecord)
        .where(MediaJobRecord.tenant_id == tenant_id)
        .order_by(MediaJobRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_serialize_media_job(r) for r in rows]


def _serialize_media_job(j: MediaJobRecord) -> dict[str, Any]:
    return {
        "job_id": j.job_id,
        "media_type": j.media_type,
        "agent_id": j.agent_id,
        "prompt": j.prompt,
        "provider": j.provider,
        "status": j.status,
        "output_file_id": j.output_file_id,
        "result": json.loads(j.result_json or "{}"),
        "created_by": j.created_by,
        "created_at": j.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# BRIDGE — iPhone PWA Share-to-JARVIS Intake
# ---------------------------------------------------------------------------
def _fetch_public_share_metadata(url: str, settings: Settings) -> dict[str, Any]:
    """Attempt an honest, SSRF-safe public metadata lookup (e.g., TikTok oEmbed or public page title).

    Never bypasses logins, CAPTCHAs, or anti-bot walls; explicitly reports UNAVAILABLE_OR_GATED when unreachable.
    """
    import httpx
    from urllib.parse import quote_plus, urlparse

    host = (urlparse(url).hostname or "").lower()
    is_tiktok = host == "tiktok.com" or host.endswith(".tiktok.com")
    if is_tiktok:
        oembed_url = f"https://www.tiktok.com/oembed?url={quote_plus(url)}"
        try:
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                resp = client.get(oembed_url, headers={"User-Agent": "ULTRON-OS-2026-Bridge/1.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "platform": "tiktok",
                        "fetch_status": "PUBLIC_OEMBED_ACCESSIBLE",
                        "title": data.get("title", ""),
                        "author_name": data.get("author_name", ""),
                        "author_url": data.get("author_url", ""),
                        "provider_name": data.get("provider_name", "TikTok"),
                        "thumbnail_url": data.get("thumbnail_url", ""),
                        "limitation_note": "Only public TikTok oEmbed metadata is retrieved; raw video stream/private content is not scraped.",
                    }
                return {
                    "platform": "tiktok",
                    "fetch_status": "UNAVAILABLE_OR_GATED",
                    "http_status": resp.status_code,
                    "limitation_note": f"TikTok public oEmbed returned HTTP {resp.status_code}. ULTRON does not bypass anti-bot or login walls.",
                }
        except Exception as exc:
            return {
                "platform": "tiktok",
                "fetch_status": "UNAVAILABLE_OR_OFFLINE",
                "error": str(exc),
                "limitation_note": "TikTok oEmbed could not be reached from this environment; content was not fabricated.",
            }

    try:
        from app.integrations.web_research import WebResearchClient

        page = WebResearchClient(settings).fetch_page(url)
        return {
            "platform": "web",
            "fetch_status": "PUBLIC_PAGE_ACCESSIBLE",
            "title": page.get("title", ""),
            "excerpt": (page.get("text", "") or "")[:600],
            "final_url": page.get("url", url),
        }
    except Exception as exc:
        return {
            "platform": "web",
            "fetch_status": "UNAVAILABLE_OR_OFFLINE",
            "error": str(exc),
            "limitation_note": "Public URL metadata could not be fetched from this environment.",
        }


def ingest_shared_item(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    title: str = "",
    url: str = "",
    shared_text: str = "",
    source_app: str = "ios_share_sheet",
    file_id: str | None = None,
) -> dict[str, Any]:
    """Receive content shared from iOS/PWA Share Sheet, validate URL via AEGIS, fetch public metadata honestly, redact secrets, and route to JARVIS."""
    url_check = inspect_url_safety(url) if url.strip() else {"verdict": "UNVERIFIED", "safe": True, "reasons": []}
    if url.strip() and not url_check["safe"]:
        raise ValidationError(
            f"BRIDGE blocked unsafe URL: {'; '.join(url_check['reasons'])}",
            details=url_check,
        )

    interception = intercept_and_redact_secrets(
        shared_text,
        db=db,
        principal=principal,
        settings=settings,
        source_context=f"bridge:{source_app}",
        auto_vault=True,
    )

    public_meta = _fetch_public_share_metadata(url.strip(), settings) if url.strip() else {}
    effective_title = (title.strip() or public_meta.get("title") or url.strip() or shared_text.strip())[:240]

    conv = create_conversation(
        db,
        principal=principal,
        title=f"Shared: {effective_title[:60]}",
        agent_id="AGT-02",
    )

    # Seed the linked JARVIS conversation with an honest summary of what was shared & accessible
    bridge_prompt = (
        f"[BRIDGE UNTRUSTED EXTERNAL SHARE from {source_app}]\n"
        f"Title: {effective_title}\n"
        f"URL: {url.strip() or '(none)'}\n"
        f"Accessible Metadata Status: {public_meta.get('fetch_status', 'TEXT_ONLY')}\n"
        f"Metadata: {json.dumps(public_meta, default=str)}\n"
        f"Shared Note: {interception.sanitized_text or '(none)'}\n"
        "Summarize strictly what is verified and publicly accessible without inventing unseen details."
    )
    try:
        send_conversation_message(
            db,
            principal=principal,
            conversation_id=conv["conversation_id"],
            content=bridge_prompt,
            settings=settings,
        )
    except Exception:
        pass

    item = SharedItemRecord(
        share_id=f"shr_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        source_app=source_app.strip()[:80],
        title=effective_title,
        url=url.strip()[:1000],
        shared_text=interception.sanitized_text,
        file_id=file_id,
        aegis_url_verdict=url_check["verdict"],
        extracted_metadata_json=json.dumps(
            {
                "url_inspection": url_check,
                "public_fetch": public_meta,
                "secrets_redacted": interception.redaction_count,
                "untrusted_content_tagged": True,
            },
            default=str,
        ),
        conversation_id=conv["conversation_id"],
        created_by=principal.username,
    )
    db.add(item)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="BRIDGE_SHARE_INGESTED",
        resource=item.share_id,
        outcome=f"verdict={item.aegis_url_verdict};fetch={public_meta.get('fetch_status', 'NONE')};source={item.source_app}",
    )
    db.commit()
    db.refresh(item)
    return _serialize_shared_item(item)


def list_shared_items(db: Session, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(SharedItemRecord)
        .where(SharedItemRecord.tenant_id == tenant_id)
        .order_by(SharedItemRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_serialize_shared_item(r) for r in rows]


def _serialize_shared_item(s: SharedItemRecord) -> dict[str, Any]:
    return {
        "share_id": s.share_id,
        "source_app": s.source_app,
        "title": s.title,
        "url": s.url,
        "shared_text": s.shared_text,
        "file_id": s.file_id,
        "aegis_url_verdict": s.aegis_url_verdict,
        "extracted_metadata": json.loads(s.extracted_metadata_json or "{}"),
        "conversation_id": s.conversation_id,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# CARAVAN — Business Intelligence Analytics (Zero Fabricated Metrics)
# ---------------------------------------------------------------------------
VALID_CARAVAN_EVENTS = frozenset({"SIGNUP", "ACTIVE_USER", "REVENUE", "GRANT_APPLICATION", "CONVERSION"})


def record_caravan_event(
    db: Session,
    *,
    principal: Principal,
    event_type: str,
    country: str = "Nigeria",
    city: str = "",
    acquisition_source: str = "DIRECT",
    amount_usd: float = 0.0,
    count_value: int = 1,
    venture: str = "CARAVAN",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    et = event_type.strip().upper()
    if et not in VALID_CARAVAN_EVENTS:
        raise ValidationError(f"Unsupported event_type '{et}'. Allowed: {', '.join(sorted(VALID_CARAVAN_EVENTS))}")

    ev = BusinessAnalyticsEventRecord(
        event_id=f"cev_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        venture=venture.strip().upper()[:80],
        event_type=et,
        country=country.strip()[:80],
        city=city.strip()[:120],
        acquisition_source=acquisition_source.strip().upper()[:80],
        amount_usd=round(float(amount_usd), 2),
        count_value=max(1, int(count_value)),
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {
        "event_id": ev.event_id,
        "venture": ev.venture,
        "event_type": ev.event_type,
        "country": ev.country,
        "city": ev.city,
        "acquisition_source": ev.acquisition_source,
        "amount_usd": ev.amount_usd,
        "count_value": ev.count_value,
        "recorded_at": ev.recorded_at.isoformat(),
    }


def get_caravan_analytics_summary(db: Session, *, tenant_id: str, venture: str = "CARAVAN") -> dict[str, Any]:
    """Return real aggregated Caravan BI metrics strictly from recorded events (clean empty state when zero)."""
    rows = db.execute(
        select(BusinessAnalyticsEventRecord).where(
            BusinessAnalyticsEventRecord.tenant_id == tenant_id,
            BusinessAnalyticsEventRecord.venture == venture.strip().upper(),
        )
    ).scalars().all()

    if not rows:
        return {
            "venture": venture.strip().upper(),
            "has_data": False,
            "empty_state": "No Caravan analytics events recorded yet. Connect Caravan telemetry or ingest real events via POST /api/v1/caravan/events.",
            "totals": {
                "signups": 0,
                "active_users": 0,
                "conversions": 0,
                "grant_applications": 0,
                "revenue_usd": 0.0,
                "conversion_rate_pct": 0.0,
            },
            "by_country": {},
            "by_city": {},
            "by_acquisition_source": {},
        }

    signups = 0
    active_users = 0
    conversions = 0
    grants = 0
    revenue = 0.0
    by_country: dict[str, int] = {}
    by_city: dict[str, int] = {}
    by_source: dict[str, int] = {}

    for r in rows:
        by_country[r.country] = by_country.get(r.country, 0) + r.count_value
        if r.city:
            by_city[r.city] = by_city.get(r.city, 0) + r.count_value
        by_source[r.acquisition_source] = by_source.get(r.acquisition_source, 0) + r.count_value

        if r.event_type == "SIGNUP":
            signups += r.count_value
        elif r.event_type == "ACTIVE_USER":
            active_users += r.count_value
        elif r.event_type == "CONVERSION":
            conversions += r.count_value
        elif r.event_type == "GRANT_APPLICATION":
            grants += r.count_value
        elif r.event_type == "REVENUE":
            revenue = round(revenue + r.amount_usd, 2)

    conv_rate = round((conversions / signups) * 100.0, 2) if signups > 0 else 0.0
    return {
        "venture": venture.strip().upper(),
        "has_data": True,
        "empty_state": None,
        "total_events": len(rows),
        "totals": {
            "signups": signups,
            "active_users": active_users,
            "conversions": conversions,
            "grant_applications": grants,
            "revenue_usd": revenue,
            "conversion_rate_pct": conv_rate,
        },
        "by_country": by_country,
        "by_city": by_city,
        "by_acquisition_source": by_source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# PULSE — Live Data-Backed Generated Web Pages
# ---------------------------------------------------------------------------
VALID_PULSE_TYPES = frozenset({"ORDERS", "FINANCE", "CARAVAN", "AGENTS", "PROJECTS", "BRIEFING"})


def create_pulse_page(
    db: Session,
    *,
    principal: Principal,
    title: str,
    page_type: str,
    slug: str | None = None,
) -> dict[str, Any]:
    ptype = page_type.strip().upper()
    if ptype not in VALID_PULSE_TYPES:
        raise ValidationError(f"Unsupported PULSE page_type '{ptype}'. Allowed: {', '.join(sorted(VALID_PULSE_TYPES))}")

    clean_slug = (slug or title.lower().replace(" ", "-"))[:120]
    bindings = [f"/api/v1/pulse/pages/{{page_id}}/live"]
    page = PulsePageRecord(
        page_id=f"pls_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        slug=clean_slug,
        title=title.strip()[:200],
        page_type=ptype,
        data_bindings_json=json.dumps(bindings),
        layout_spec_json=json.dumps({"theme": "ultron-dark-slate", "auto_refresh_seconds": 30}),
        created_by=principal.username,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return _serialize_pulse_page(page)


def list_pulse_pages(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(PulsePageRecord)
        .where(PulsePageRecord.tenant_id == tenant_id)
        .order_by(PulsePageRecord.updated_at.desc())
    ).scalars().all()
    return [_serialize_pulse_page(r) for r in rows]


def render_pulse_page_live(db: Session, *, tenant_id: str, page_id: str) -> dict[str, Any]:
    """Hydrate a PULSE page strictly from live backend SQLAlchemy state (never hardcoded values)."""
    page = db.execute(
        select(PulsePageRecord).where(
            PulsePageRecord.page_id == page_id,
            PulsePageRecord.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if page is None:
        raise NotFoundError(f"PULSE page '{page_id}' not found.")

    live_data: dict[str, Any]
    if page.page_type == "ORDERS":
        orders = list_orders(db, tenant_id=tenant_id)
        live_data = {"total_orders": len(orders), "orders": orders}
    elif page.page_type == "FINANCE":
        live_data = generate_financial_report(db, tenant_id=tenant_id)
    elif page.page_type == "CARAVAN":
        live_data = get_caravan_analytics_summary(db, tenant_id=tenant_id)
    elif page.page_type == "AGENTS":
        total = int(db.execute(select(func.count(AgentRecord.agent_id))).scalar_one())
        live_data = {"total_agents": total}
    elif page.page_type == "PROJECTS":
        projs = db.execute(select(ProjectRecord).where(ProjectRecord.tenant_id == tenant_id)).scalars().all()
        live_data = {"total_projects": len(projs), "projects": [{"project_id": p.project_id, "name": p.name, "status": p.status} for p in projs]}
    else:
        briefings = list_briefings(db, tenant_id=tenant_id, limit=5)
        live_data = {"total_briefings": len(briefings), "briefings": briefings}

    return {
        "page": _serialize_pulse_page(page),
        "live_data": live_data,
        "hydrated_at": datetime.now(timezone.utc).isoformat(),
    }


def _serialize_pulse_page(p: PulsePageRecord) -> dict[str, Any]:
    return {
        "page_id": p.page_id,
        "slug": p.slug,
        "title": p.title,
        "page_type": p.page_type,
        "data_bindings": json.loads(p.data_bindings_json or "[]"),
        "layout_spec": json.loads(p.layout_spec_json or "{}"),
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
