"""Modular Tool Registry & Governed Execution Harness for ULTRON OS 2026."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
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
        description="Inspect live database connectivity, agent counts, and 14-capability integration status.",
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
    "file_parse": ToolDefinition(
        name="file_parse",
        description="Parse JSON, CSV, or plain text/Markdown content and compute SHA-256 digest & stats.",
        risk_level="LOW",
        required_permission="tools:execute",
        requires_approval_gate=False,
        input_schema={
            "type": "object",
            "required": ["format", "content"],
            "properties": {
                "format": {"type": "string", "enum": ["json", "csv", "text", "markdown"]},
                "content": {"type": "string"},
            },
        },
    ),
    "code_analyze_python": ToolDefinition(
        name="code_analyze_python",
        description="Perform real Python AST syntax, complexity, and unsafe-call static security analysis.",
        risk_level="LOW",
        required_permission="tools:execute",
        requires_approval_gate=False,
        input_schema={
            "type": "object",
            "required": ["source_code"],
            "properties": {"source_code": {"type": "string"}},
        },
    ),
    "email_dispatch_request": ToolDefinition(
        name="email_dispatch_request",
        description="Draft and request ApprovalGate sign-off before sending any external email.",
        risk_level="HIGH",
        required_permission="tools:execute",
        requires_approval_gate=True,
        input_schema={
            "type": "object",
            "required": ["to", "subject", "body"],
            "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
        },
    ),
    "whatsapp_dispatch_request": ToolDefinition(
        name="whatsapp_dispatch_request",
        description="Draft and request ApprovalGate sign-off before sending any external WhatsApp message.",
        risk_level="HIGH",
        required_permission="tools:execute",
        requires_approval_gate=True,
        input_schema={
            "type": "object",
            "required": ["to_phone", "message"],
            "properties": {"to_phone": {"type": "string"}, "message": {"type": "string"}},
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


def analyze_python_ast(source_code: str) -> dict[str, Any]:
    """Static Python AST parser reporting functions, classes, imports, and unsafe call flags."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return {
            "syntax_valid": False,
            "error": f"SyntaxError at line {exc.lineno}: {exc.msg}",
            "functions": [],
            "classes": [],
            "security_findings": [],
        }

    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    findings: list[str] = []
    unsafe_calls = {"eval", "exec", "compile", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in unsafe_calls:
                findings.append(f"Line {node.lineno}: Dangerous builtin '{node.func.id}()' detected.")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "popen"}:
                findings.append(f"Line {node.lineno}: Shell execution call '.{node.func.attr}()' detected.")

    return {
        "syntax_valid": True,
        "line_count": len(source_code.splitlines()),
        "functions": sorted(set(functions)),
        "classes": sorted(set(classes)),
        "imports": sorted(set(imports)),
        "security_findings": findings,
    }


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
            tenant_id=principal.tenant_id,
            actor=principal.username,
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

    elif tool.name == "file_parse":
        fmt = str(arguments.get("format", "text")).lower()
        content = str(arguments.get("content", ""))
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if fmt == "json":
            try:
                parsed = json.loads(content)
                output = {
                    "format": "json",
                    "valid": True,
                    "sha256": sha256,
                    "top_level_type": type(parsed).__name__,
                    "key_count": len(parsed) if isinstance(parsed, (dict, list)) else 1,
                }
            except json.JSONDecodeError as exc:
                output = {"format": "json", "valid": False, "sha256": sha256, "error": str(exc)}
        elif fmt == "csv":
            rows = list(csv.reader(io.StringIO(content)))
            output = {
                "format": "csv",
                "valid": True,
                "sha256": sha256,
                "row_count": len(rows),
                "headers": rows[0] if rows else [],
            }
        else:
            output = {
                "format": fmt,
                "valid": True,
                "sha256": sha256,
                "line_count": len(content.splitlines()),
                "word_count": len(content.split()),
                "char_count": len(content),
            }

    elif tool.name == "code_analyze_python":
        source_code = str(arguments.get("source_code", ""))
        if not source_code.strip():
            raise ValidationError("code_analyze_python requires non-empty 'source_code'.")
        output = analyze_python_ast(source_code)

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

    elif tool.name in {"email_dispatch_request", "whatsapp_dispatch_request"}:
        channel = "EMAIL" if tool.name == "email_dispatch_request" else "WHATSAPP"
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type=f"EXTERNAL_COMM_{channel}",
            reason=f"External {channel} communication requires ApprovalGate authorization before dispatch.",
            risk_level="HIGH",
            tool_name=tool.name,
            payload=arguments,
            commit=False,
        )
        approval_id = approval.approval_id
        status = "WAITING_FOR_APPROVAL"
        output = {
            "gated": True,
            "channel": channel,
            "approval": serialize_approval(approval),
            "message": f"External {channel} draft queued at ApprovalGate; never sent without authorization.",
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
