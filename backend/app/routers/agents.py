"""Specialist Agent Catalog (60 Agents + Approved Extensions), manifests, inter-agent bus, and NEON routing endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.db.models import AgentRecord
from app.db.repositories import append_audit_log
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import (
    AgentInvokeRequest,
    AgentMessageRequest,
    RegisterAgentExtensionRequest,
    RoutePreviewRequest,
    UpdateAgentStateRequest,
)
from app.services.agent_service import (
    build_agent_manifest,
    list_agent_messages,
    propose_agent_extension,
    send_agent_message,
)
from app.services.neon_router import get_reasoning_tiers, invoke_agent_reasoning, route_objective

router = APIRouter(prefix="/api/v1/agents", tags=["Agents & NEON Router"])


def _serialize_agent(a: AgentRecord) -> dict:
    return {
        "agent_id": a.agent_id,
        "name": a.name,
        "tier": a.tier,
        "domain": a.domain,
        "role_description": a.role_description,
        "tools": json.loads(a.tools_json or "[]"),
        "permission_scope": a.permission_scope,
        "capability_state": a.capability_state,
        "default_reasoning_tier": a.default_reasoning_tier,
        "is_extension": a.is_extension,
        "approved": a.approved,
        "tasks_completed": a.tasks_completed,
        "tasks_failed": a.tasks_failed,
        "last_active": a.last_active.isoformat(),
    }


@router.get("")
def list_agents(
    tier: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    capability_state: str | None = Query(default=None),
    _principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(AgentRecord)
    if tier:
        stmt = stmt.where(AgentRecord.tier == tier.upper())
    if domain:
        stmt = stmt.where(AgentRecord.domain.ilike(f"%{domain}%"))
    if capability_state:
        stmt = stmt.where(AgentRecord.capability_state == capability_state.upper())
    rows = db.execute(stmt.order_by(AgentRecord.agent_id.asc())).scalars().all()
    return {"total": len(rows), "agents": [_serialize_agent(a) for a in rows]}


@router.get("/reasoning-tiers")
def list_reasoning_tiers(
    _principal: Principal = Depends(require_perm("agents:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"tiers": list(get_reasoning_tiers(settings).values())}


@router.post("/route")
def preview_route(
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_agent_extension(
    body: RegisterAgentExtensionRequest,
    principal: Principal = Depends(require_perm("agents:manage")),
    db: Session = Depends(get_db),
) -> dict:
    """Propose a dynamic extension agent gated by ApprovalGate before activation."""
    return propose_agent_extension(
        db,
        principal=principal,
        agent_id=body.agent_id,
        name=body.name,
        domain=body.domain,
        role_description=body.role_description,
        tools=body.tools,
        permission_scope=body.permission_scope,
        default_reasoning_tier=body.default_reasoning_tier,
    )


@router.post("/messages", status_code=status.HTTP_201_CREATED)
def api_send_agent_message(
    body: AgentMessageRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
) -> dict:
    return send_agent_message(
        db,
        principal=principal,
        from_agent_id=body.from_agent_id,
        to_agent_id=body.to_agent_id,
        subject=body.subject,
        payload=body.payload,
        task_id=body.task_id,
    )


@router.get("/messages")
def api_list_agent_messages(
    agent_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    msgs = list_agent_messages(db, tenant_id=principal.tenant_id, agent_id=agent_id, task_id=task_id)
    return {"total": len(msgs), "messages": msgs}


@router.get("/page-matrix")
def get_page_matrix(
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    from app.services.page_agent_registry import PAGE_INTEGRATION_MATRIX, validate_registry_integrity

    validation = validate_registry_integrity()
    return {
        "total_pages": len(PAGE_INTEGRATION_MATRIX),
        "valid": validation["valid"],
        "matrix": PAGE_INTEGRATION_MATRIX,
    }


@router.get("/pages/{page_id}")
def get_page_integration(
    page_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    from app.services.page_agent_registry import get_page_spec

    spec = get_page_spec(page_id)
    if not spec:
        raise NotFoundError(f"Page '{page_id}' not found in 112-page registry.")
    return spec


@router.get("/{agent_id}")
def get_agent(
    agent_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    agent = db.get(AgentRecord, agent_id.upper())
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found.")
    return _serialize_agent(agent)


@router.get("/{agent_id}/pages")
def get_agent_pages(
    agent_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.page_agent_registry import get_pages_for_agent

    agent = db.get(AgentRecord, agent_id.upper())
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found.")
    res = get_pages_for_agent(agent_id.upper())
    res["agent_name"] = agent.name
    res["tier"] = agent.tier
    return res


@router.get("/{agent_id}/manifest")
def get_agent_manifest(
    agent_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    agent = db.get(AgentRecord, agent_id.upper())
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found.")
    return build_agent_manifest(agent, settings)


@router.patch("/{agent_id}/state")
def update_agent_state(
    agent_id: str,
    body: UpdateAgentStateRequest,
    principal: Principal = Depends(require_perm("agents:manage")),
    db: Session = Depends(get_db),
) -> dict:
    agent = db.get(AgentRecord, agent_id.upper())
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found.")
    prev = agent.capability_state
    agent.capability_state = body.capability_state
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="AGENT_STATE_UPDATED",
        resource=agent.agent_id,
        outcome=f"{prev}->{body.capability_state}",
    )
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent)


@router.post("/{agent_id}/invoke")
def invoke_agent(
    agent_id: str,
    body: AgentInvokeRequest,
    principal: Principal = Depends(require_perm("agents:invoke")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = invoke_agent_reasoning(
        db,
        agent_id=agent_id.upper(),
        prompt=body.prompt,
        settings=settings,
        context=body.context,
        reasoning_tier=body.reasoning_tier,
        response_format=body.response_format,
        temperature=body.temperature,
        tenant_id=principal.tenant_id,
        actor=principal.username,
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="AGENT_INVOKED",
        resource=agent_id.upper(),
        outcome=result["execution_mode"],
        metadata={"reasoning_tier": result["reasoning_tier"], "model": result["model"]},
    )
    db.commit()
    return result
