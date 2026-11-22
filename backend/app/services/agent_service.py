"""Specialist Agent management: manifests, inter-agent messaging, performance metrics, and ApprovalGate extension registration."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.db.models import AgentMessageRecord, AgentRecord
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval


def build_agent_manifest(agent: AgentRecord, settings: Settings) -> dict[str, Any]:
    """Return full agent manifest with honest execution backing classification."""
    llm_configured = bool(
        (settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
        or (settings.openai_api_key and settings.openai_api_key.get_secret_value().strip())
        or (settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value().strip())
        or settings.ollama_base_url.strip()
    )
    custom = json.loads(agent.manifest_json or "{}")
    avg_latency = round(agent.total_latency_ms / agent.tasks_completed, 2) if agent.tasks_completed else 0.0
    total_runs = agent.tasks_completed + agent.tasks_failed
    success_rate = round((agent.tasks_completed / total_runs) * 100.0, 2) if total_runs else 100.0

    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "tier": agent.tier,
        "domain": agent.domain,
        "role_description": agent.role_description,
        "tools": json.loads(agent.tools_json or "[]"),
        "permission_scope": agent.permission_scope,
        "capability_state": agent.capability_state,
        "default_reasoning_tier": agent.default_reasoning_tier,
        "is_extension": agent.is_extension,
        "approved": agent.approved,
        "execution_backing": "LLM_BACKED_CONFIGURED" if llm_configured else "RULE_AND_TOOL_BACKED_OFFLINE",
        "metrics": {
            "tasks_completed": agent.tasks_completed,
            "tasks_failed": agent.tasks_failed,
            "success_rate_pct": success_rate,
            "avg_latency_ms": avg_latency,
            "last_active": agent.last_active.isoformat(),
        },
        "contract": custom or {
            "version": "2026.2",
            "isolation": "TENANT_SCOPED_STATELESS_CONTEXT",
            "requires_verification": True,
        },
    }


def send_agent_message(
    db: Session,
    *,
    principal: Principal,
    from_agent_id: str,
    to_agent_id: str,
    subject: str,
    payload: dict[str, Any],
    task_id: str | None = None,
) -> dict[str, Any]:
    """Deliver a structured tenant-isolated message between two specialist agents."""
    src = db.get(AgentRecord, from_agent_id.upper())
    dst = db.get(AgentRecord, to_agent_id.upper())
    if src is None or dst is None:
        raise NotFoundError("Both source and target agents must exist in the registry.")
    if not src.approved or not dst.approved:
        raise ConflictError("Unapproved extension agents cannot exchange messages.")

    msg = AgentMessageRecord(
        message_id=f"amsg_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        from_agent_id=src.agent_id,
        to_agent_id=dst.agent_id,
        task_id=task_id,
        subject=subject.strip()[:200],
        payload_json=json.dumps(payload, default=str),
        status="DELIVERED",
    )
    db.add(msg)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="AGENT_MESSAGE_SENT",
        resource=f"{src.agent_id}->{dst.agent_id}",
        outcome=msg.message_id,
    )
    db.commit()
    db.refresh(msg)
    return _serialize_agent_message(msg)


def list_agent_messages(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str | None = None,
    task_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(AgentMessageRecord).where(AgentMessageRecord.tenant_id == tenant_id)
    if agent_id:
        aid = agent_id.upper()
        stmt = stmt.where((AgentMessageRecord.to_agent_id == aid) | (AgentMessageRecord.from_agent_id == aid))
    if task_id:
        stmt = stmt.where(AgentMessageRecord.task_id == task_id)
    rows = db.execute(stmt.order_by(AgentMessageRecord.created_at.desc()).limit(limit)).scalars().all()
    return [_serialize_agent_message(r) for r in rows]


def propose_agent_extension(
    db: Session,
    *,
    principal: Principal,
    agent_id: str,
    name: str,
    domain: str,
    role_description: str,
    tools: list[str],
    permission_scope: str = "TIER_2_READ",
    default_reasoning_tier: int = 2,
) -> dict[str, Any]:
    """Register a dynamic specialist agent extension gated behind ApprovalGate sign-off."""
    clean_id = agent_id.strip().upper()
    if db.get(AgentRecord, clean_id) is not None:
        raise ConflictError(f"Agent ID '{clean_id}' already exists in the registry.")

    now = datetime.now(timezone.utc)
    sys_inst = (
        f"You are extension agent {name} ({clean_id}) in domain {domain}. "
        f"{role_description} Operate strictly within scope {permission_scope}."
    )
    agent = AgentRecord(
        agent_id=clean_id,
        name=name.strip(),
        tier="DYNAMIC_EXTENSION",
        domain=domain.strip(),
        role_description=role_description.strip(),
        system_instruction=sys_inst,
        tools_json=json.dumps(tools),
        manifest_json=json.dumps({"version": "1.0.0", "proposed_by": principal.username}),
        permission_scope=permission_scope,
        capability_state="REQUIRES_APPROVAL",
        default_reasoning_tier=max(1, min(5, default_reasoning_tier)),
        is_extension=True,
        approved=False,
        last_active=now,
    )
    db.add(agent)
    db.flush()

    approval = create_approval_request(
        db,
        tenant_id=principal.tenant_id,
        requested_by=principal.username,
        action_type="AGENT_EXTENSION_REGISTRATION",
        reason=f"Dynamic extension agent '{clean_id}' ({name}) requires OWNER/ADMIN approval before activation.",
        risk_level="HIGH",
        resource_ref=clean_id,
        payload={"agent_id": clean_id, "name": name, "domain": domain, "tools": tools},
        commit=False,
    )
    db.commit()
    return {
        "agent_id": clean_id,
        "approved": False,
        "capability_state": "REQUIRES_APPROVAL",
        "approval": serialize_approval(approval),
    }


def _serialize_agent_message(m: AgentMessageRecord) -> dict[str, Any]:
    return {
        "message_id": m.message_id,
        "tenant_id": m.tenant_id,
        "from_agent_id": m.from_agent_id,
        "to_agent_id": m.to_agent_id,
        "task_id": m.task_id,
        "subject": m.subject,
        "payload": json.loads(m.payload_json or "{}"),
        "status": m.status,
        "created_at": m.created_at.isoformat(),
    }
