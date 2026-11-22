"""Modular Tool Registry & Governed Execution Harness for ULTRON OS 2026."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal, require_permission
from app.core.security import validate_outbound_url
from app.db.models import AgentRecord, ToolExecutionRecord
from app.db.repositories import append_audit_log
from app.db.session import check_database_health
from app.integrations.registry import IntegrationRegistry
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.memory_service import search_memories
from app.services.neon_router import invoke_agent_reasoning


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    risk_level: str
    required_permission: str
    requires_approval_gate: bool
    input_schema: dict[str, Any]


TOOL_CATALOG: dict[str, ToolDefinition] = {
    "system_diagnostics": ToolDefinition(
        name="system_diagnostics",
        description="Inspect live database connectivity, agent counts, and cloud integration configuration.",
        risk_level="LOW",
        required_permission="tools:execute",
        requires_approval_gate=False,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    "memory_query": ToolDefinition(
        name="memory_query",
        description="Run tenant-scoped semantic and lexical recall across ULTRON memory stores.",
        risk_level="LOW",
        required_permission="memory:read",
        requires_approval_gate=False,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "namespace": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
        },
    ),
    "gemini_analyze": ToolDefinition(
        name="gemini_analyze",
        description="Run specialist agent analysis through the NEON Gemini router (or honest offline fallback).",
        risk_level="LOW",
        required_permission="agents:invoke",
        requires_approval_gate=False,
        input_schema={
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "agent_id": {"type": "string", "default": "AGT-01"},
                "reasoning_tier": {"type": "integer", "minimum": 1, "maximum": 5},
            },
        },
    ),
    "http_fetch_public": ToolDefinition(
        name="http_fetch_public",
        description="SSRF-protected outbound HTTP GET fetch for public web resources only.",
        risk_level="MEDIUM",
        required_permission="tools:execute",
        requires_approval_gate=False,
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 15},
            },
        },
    ),
    "financial_transfer_request": ToolDefinition(
        name="financial_transfer_request",
        description="Submit a governed financial transfer request subject to ApprovalGate ($50 soft limit).",
        risk_level="HIGH",
        required_permission="tools:execute",
        requires_approval_gate=True,
        input_schema={
            "type": "object",
            "required": ["amount_usd", "currency", "destination"],
            "properties": {
                "amount_usd": {"type": "number", "minimum": 0.01},
                "currency": {"type": "string"},
                "destination": {"type": "string"},
                "memo": {"type": "string"},
            },
        },
    ),
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "risk_level": t.risk_level,
            "required_permission": t.required_permission,
            "requires_approval_gate": t.requires_approval_gate,
            "input_schema": t.input_schema,
        }
        for t in TOOL_CATALOG.values()
    ]


def execute_tool(
    db: Session,
    *,
    principal: Principal,
    tool_name: str,
    arguments: dict[str, Any],
    settings: Settings,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Execute a registered tool with permission checks, SSRF guards, ApprovalGate, and audit logs."""
    tool = TOOL_CATALOG.get(tool_name)
    if tool is None:
        raise NotFoundError(f"Tool '{tool_name}' is not registered.")

    require_permission(principal, tool.required_permission)

    started = time.perf_counter()
    execution_id = f"tex_{uuid.uuid4().hex[:16]}"
    approval_id: str | None = None
    status = "COMPLETED"
    output: dict[str, Any]

    if tool.name == "system_diagnostics":
        db_ok, db_msg = check_database_health(settings)
        agent_count = db.execute(select(func.count()).select_from(AgentRecord)).scalar_one()
        integrations = IntegrationRegistry(settings).get_static_status()
        output = {
            "database": {"healthy": db_ok, "detail": db_msg, "backend": settings.database_backend},
            "registered_agents": agent_count,
            "integrations": integrations,
        }

    elif tool.name == "memory_query":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValidationError("memory_query requires a non-empty 'query' argument.")
        output = search_memories(
            db,
            tenant_id=principal.tenant_id,
            query=query,
            namespace=arguments.get("namespace"),
            limit=int(arguments.get("limit", 5)),
            settings=settings,
        )

    elif tool.name == "gemini_analyze":
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            raise ValidationError("gemini_analyze requires a non-empty 'prompt' argument.")
        output = invoke_agent_reasoning(
            db,
            agent_id=str(arguments.get("agent_id") or agent_id or "AGT-01"),
            prompt=prompt,
            settings=settings,
            reasoning_tier=arguments.get("reasoning_tier"),
        )

    elif tool.name == "http_fetch_public":
        raw_url = str(arguments.get("url", "")).strip()
        safe_url = validate_outbound_url(raw_url)
        timeout = min(15.0, max(1.0, float(arguments.get("timeout_seconds", 8.0))))
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                resp = client.get(safe_url)
            output = {
                "url": safe_url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "body_preview": resp.text[:1000],
            }
        except httpx.HTTPError as exc:
            status = "FAILED"
            output = {"url": safe_url, "error": f"HTTP fetch failed: {type(exc).__name__}"}

    elif tool.name == "financial_transfer_request":
        amount_usd = float(arguments.get("amount_usd", 0.0))
        currency = str(arguments.get("currency", "USD")).upper()
        destination = str(arguments.get("destination", "")).strip()
        if amount_usd <= 0 or not destination:
            raise ValidationError("financial_transfer_request requires positive 'amount_usd' and 'destination'.")
        if amount_usd > settings.approval_soft_limit_usd:
            approval = create_approval_request(
                db,
                tenant_id=principal.tenant_id,
                requested_by=principal.username,
                action_type="FINANCIAL_TRANSFER",
                reason=f"Transfer of ${amount_usd:.2f} {currency} to '{destination}' exceeds soft limit ${settings.approval_soft_limit_usd:.2f}.",
                risk_level="HIGH",
                financial_amount_usd=amount_usd,
                tool_name=tool.name,
                payload={"amount_usd": amount_usd, "currency": currency, "destination": destination},
                commit=False,
            )
            approval_id = approval.approval_id
            status = "WAITING_FOR_APPROVAL"
            output = {
                "gated": True,
                "approval": serialize_approval(approval),
                "message": "Transfer halted at ApprovalGate awaiting authorized sign-off.",
            }
        else:
            output = {
                "gated": False,
                "auto_approved": True,
                "amount_usd": amount_usd,
                "currency": currency,
                "destination": destination,
                "note": "Below soft limit; logged to immutable audit trail (no live bank rail connected).",
            }

    else:
        raise NotFoundError(f"No handler registered for tool '{tool_name}'.")

    duration_ms = int((time.perf_counter() - started) * 1000)
    record = ToolExecutionRecord(
        execution_id=execution_id,
        tenant_id=principal.tenant_id,
        tool_name=tool.name,
        actor=principal.username,
        agent_id=agent_id,
        input_json=json.dumps(arguments, default=str),
        output_json=json.dumps(output, default=str),
        status=status,
        approval_id=approval_id,
        duration_ms=duration_ms,
    )
    db.add(record)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="TOOL_EXECUTED",
        resource=f"{tool.name}:{execution_id}",
        outcome=status,
        metadata={"approval_id": approval_id, "duration_ms": duration_ms},
    )
    db.commit()
    return {
        "execution_id": execution_id,
        "tool_name": tool.name,
        "status": status,
        "approval_id": approval_id,
        "duration_ms": duration_ms,
        "output": output,
    }


def list_tool_executions(db: Session, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ToolExecutionRecord)
        .where(ToolExecutionRecord.tenant_id == tenant_id)
        .order_by(ToolExecutionRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "execution_id": r.execution_id,
            "tool_name": r.tool_name,
            "actor": r.actor,
            "agent_id": r.agent_id,
            "status": r.status,
            "approval_id": r.approval_id,
            "duration_ms": r.duration_ms,
            "input": json.loads(r.input_json or "{}"),
            "output": json.loads(r.output_json or "{}"),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
