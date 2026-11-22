"""NEON Intelligence Engine routes: models, tiers, completion, tool-calling, SSE streaming, conversations, and cost/usage tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import (
    CreateConversationRequest,
    NeonCompleteRequest,
    RoutePreviewRequest,
    SendConversationMessageRequest,
)
from app.services.neon_router import (
    create_conversation,
    get_conversation,
    get_gemini_diagnostics,
    get_model_capability_registry,
    get_reasoning_tiers,
    get_usage_summary,
    invoke_agent_reasoning,
    list_conversations,
    route_objective,
    run_gemini_verification_suite,
    send_conversation_message,
    stream_live_neon_events,
)
from app.services.tool_service import execute_tool

router = APIRouter(prefix="/api/v1/neon", tags=["NEON Intelligence Engine"])


@router.get("/models")
def api_neon_models(
    _principal: Principal = Depends(require_perm("agents:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    models = get_model_capability_registry(settings)
    return {"total": len(models), "models": models}


@router.get("/tiers")
def api_neon_tiers(
    _principal: Principal = Depends(require_perm("agents:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"tiers": list(get_reasoning_tiers(settings).values())}


@router.get("/gemini/diagnostics")
def api_neon_gemini_diagnostics(
    discover: bool = Query(default=False),
    principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return honest Gemini primary intelligence diagnostics, 5-tier model matrix, and optional live catalog discovery."""
    return get_gemini_diagnostics(
        db,
        tenant_id=principal.tenant_id,
        settings=settings,
        discover_live=discover,
    )


@router.post("/gemini/verify-suite")
def api_neon_gemini_verify_suite(
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Execute safe live verification across all 5 reasoning tiers, structured JSON, tool calling, streaming, fallback, and ApprovalGate."""
    return run_gemini_verification_suite(
        db,
        principal=principal,
        settings=settings,
    )


@router.post("/route")
def api_neon_route(
    body: RoutePreviewRequest,
    _principal: Principal = Depends(require_perm("agents:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return route_objective(
        body.objective,
        financial_amount_usd=body.financial_amount_usd,
        settings=settings,
        preferred_agent_id=body.preferred_agent_id,
    )


@router.post("/complete")
def api_neon_complete(
    body: NeonCompleteRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Execute NEON reasoning with optional governed tool call, structured output, and usage tracking."""
    routing = route_objective(body.prompt, settings=settings, preferred_agent_id=body.agent_id)
    target_agent = body.agent_id or routing["selected_agent_id"]
    tier = body.reasoning_tier or routing["reasoning_tier"]

    tool_result = None
    merged_context = dict(body.context or {})
    if body.tool_name:
        tool_result = execute_tool(
            db,
            principal=principal,
            tool_name=body.tool_name,
            arguments=body.tool_arguments or {},
            settings=settings,
            agent_id=target_agent,
        )
        merged_context["tool_result"] = tool_result

    result = invoke_agent_reasoning(
        db,
        agent_id=target_agent,
        prompt=body.prompt,
        settings=settings,
        context=merged_context or None,
        reasoning_tier=tier,
        response_format=body.response_format,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
        tenant_id=principal.tenant_id,
        actor=principal.username,
    )
    db.commit()
    result["tool_execution"] = tool_result
    return result


@router.post("/stream")
def api_neon_stream(
    body: NeonCompleteRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Stream NEON reasoning events over Server-Sent Events (`text/event-stream`), using live Gemini streaming when available."""
    routing = route_objective(body.prompt, settings=settings, preferred_agent_id=body.agent_id)
    target_agent = body.agent_id or routing["selected_agent_id"]
    tier = body.reasoning_tier or routing["reasoning_tier"]
    return StreamingResponse(
        stream_live_neon_events(
            db,
            agent_id=target_agent,
            prompt=body.prompt,
            settings=settings,
            context=body.context,
            reasoning_tier=tier,
            response_format=body.response_format,
            temperature=body.temperature,
            max_output_tokens=body.max_output_tokens,
            tenant_id=principal.tenant_id,
            actor=principal.username,
        ),
        media_type="text/event-stream",
    )


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def api_create_conversation(
    body: CreateConversationRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
) -> dict:
    return create_conversation(
        db,
        principal=principal,
        title=body.title,
        agent_id=body.agent_id,
        metadata=body.metadata,
    )


@router.get("/conversations")
def api_list_conversations(
    principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    convs = list_conversations(db, principal=principal)
    return {"total": len(convs), "conversations": convs}


@router.get("/conversations/{conversation_id}")
def api_get_conversation(
    conversation_id: str,
    principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_conversation(db, principal=principal, conversation_id=conversation_id)


@router.post("/conversations/{conversation_id}/messages")
def api_send_conversation_message(
    conversation_id: str,
    body: SendConversationMessageRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return send_conversation_message(
        db,
        principal=principal,
        conversation_id=conversation_id,
        content=body.content,
        settings=settings,
        reasoning_tier=body.reasoning_tier,
    )


@router.get("/usage")
def api_neon_usage(
    principal: Principal = Depends(require_perm("monitoring:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_usage_summary(db, tenant_id=principal.tenant_id)
