"""NEON 5-Tier Intelligence Engine: routing, failover, structured outputs, tool calling, streaming, conversations, and cost tracking."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.core.security import classify_risk_level, sanitize_prompt_input
from app.db.models import AgentRecord, ConversationMessageRecord, ConversationRecord, LLMUsageLog
from app.integrations.gemini import GeminiClient
from app.services.neon_providers import (
    BaseLLMProvider,
    GeminiLLMProvider,
    estimate_cost_usd,
    execute_with_failover,
    get_model_capability_registry,
)

DOMAIN_ROUTING_RULES: list[tuple[tuple[str, ...], str]] = [
    (("code", "python", "fastapi", "typescript", "react", "refactor", "endpoint"), "AGT-03"),
    (("debug", "traceback", "stack trace", "bug", "exception", "crash"), "AGT-04"),
    (("architecture", "blueprint", "topology", "schema", "microservice"), "AGT-05"),
    (("finance", "treasury", "fx", "transfer", "budget", "payroll", "usd", "ngn", "gbp"), "AGT-08"),
    (("legal", "contract", "compliance", "gdpr", "cac", "regulatory"), "AGT-10"),
    (("security", "vault", "auth", "jwt", "pentest", "owasp", "vulnerability"), "AGT-20"),
    (("memory", "knowledge", "vector", "embedding", "recall"), "AGT-21"),
    (("test", "pytest", "coverage", "qa", "regression"), "AGT-25"),
    (("supabase", "postgres", "sqlite", "sql", "migration", "index"), "AGT-28"),
    (("vercel", "cloudflare", "deploy", "docker", "kubernetes", "cloud"), "AGT-30"),
    (("research", "paper", "market", "competitor", "grant", "funding"), "AGT-02"),
    (("email", "whatsapp", "message", "draft", "inbox"), "AGT-16"),
    (("diagnostics", "health", "telemetry", "latency", "monitor"), "AGT-59"),
]


def get_reasoning_tiers(settings: Settings) -> dict[int, dict[str, Any]]:
    return {
        1: {
            "tier": 1,
            "name": "Tier 1: Fast Operations",
            "primary_model": settings.gemini_model_fast,
            "fallback_models": [settings.ollama_model_local, settings.openai_model_fallback],
            "purpose": "Low-latency status checks, telemetry triage, and direct deterministic actions.",
        },
        2: {
            "tier": 2,
            "name": "Tier 2: Standard Reasoning",
            "primary_model": settings.gemini_model_standard,
            "fallback_models": [settings.openai_model_fallback, settings.ollama_model_local],
            "purpose": "Routine reasoning, single-domain execution, and structured summaries.",
        },
        3: {
            "tier": 3,
            "name": "Tier 3: Complex Engineering & Problem Solving",
            "primary_model": settings.gemini_model_standard,
            "fallback_models": [settings.anthropic_model_fallback, settings.openai_model_fallback],
            "purpose": "Multi-step planning, debugging, workflow design, and code synthesis.",
        },
        4: {
            "tier": 4,
            "name": "Tier 4: Deep Research & Risk Analysis",
            "primary_model": settings.gemini_model_reasoning,
            "fallback_models": [settings.anthropic_model_fallback, settings.openai_model_fallback],
            "purpose": "Financial modeling, legal/security analysis, and deep evidence synthesis.",
        },
        5: {
            "tier": 5,
            "name": "Tier 5: Multi-Agent Executive Orchestration",
            "primary_model": settings.gemini_model_reasoning,
            "fallback_models": [settings.anthropic_model_fallback],
            "purpose": "Cross-domain DAG orchestration, governance enforcement, and executive synthesis.",
        },
    }


def route_objective(
    objective: str,
    *,
    financial_amount_usd: float = 0.0,
    settings: Settings,
    preferred_agent_id: str | None = None,
) -> dict[str, Any]:
    """Analyze an objective, select reasoning tier, primary specialist agent, and risk level."""
    clean = sanitize_prompt_input(objective, reject_injection=True)
    lowered = clean.lower()

    selected_agent = preferred_agent_id or "AGT-01"
    if not preferred_agent_id:
        best_score = 0
        for keywords, agent_id in DOMAIN_ROUTING_RULES:
            score = sum(1 for kw in keywords if kw in lowered)
            if score > best_score:
                best_score = score
                selected_agent = agent_id

    risk_level = classify_risk_level(
        clean,
        financial_amount_usd=financial_amount_usd,
        soft_limit_usd=settings.approval_soft_limit_usd,
    )

    word_count = len(clean.split())
    if risk_level == "HIGH" or word_count > 45:
        tier = 5
    elif selected_agent in {"AGT-02", "AGT-05", "AGT-08", "AGT-10", "AGT-20"} or word_count > 25:
        tier = 4
    elif selected_agent in {"AGT-03", "AGT-04", "AGT-25", "AGT-28", "AGT-30"} or word_count > 12:
        tier = 3
    elif word_count > 5:
        tier = 2
    else:
        tier = 1

    tier_meta = get_reasoning_tiers(settings)[tier]
    return {
        "sanitized_objective": clean,
        "selected_agent_id": selected_agent,
        "reasoning_tier": tier,
        "tier_name": tier_meta["name"],
        "selected_model": tier_meta["primary_model"],
        "fallback_models": tier_meta["fallback_models"],
        "risk_level": risk_level,
        "requires_approval_gate": risk_level == "HIGH" or financial_amount_usd > settings.approval_soft_limit_usd,
    }


def _record_usage_log(
    db: Session,
    *,
    tenant_id: str,
    actor: str,
    agent_id: str,
    provider: str,
    model: str,
    reasoning_tier: int,
    execution_mode: str,
    usage: dict[str, int],
    latency_ms: int,
) -> float:
    pt = int(usage.get("prompt_tokens", 0))
    ct = int(usage.get("completion_tokens", 0))
    tt = int(usage.get("total_tokens", pt + ct))
    cost = estimate_cost_usd(model, pt, ct) if execution_mode.endswith("_live") else 0.0
    db.add(
        LLMUsageLog(
            usage_id=f"usg_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            actor=actor,
            agent_id=agent_id,
            provider=provider,
            model=model,
            reasoning_tier=reasoning_tier,
            execution_mode=execution_mode,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
        )
    )
    db.flush()
    return cost


def invoke_agent_reasoning(
    db: Session,
    *,
    agent_id: str,
    prompt: str,
    settings: Settings,
    context: dict[str, Any] | None = None,
    reasoning_tier: int | None = None,
    response_format: str = "text",
    temperature: float = 0.2,
    max_output_tokens: int = 1024,
    tenant_id: str | None = None,
    actor: str = "SYSTEM",
    gemini_client: GeminiClient | None = None,
    providers: list[BaseLLMProvider] | None = None,
) -> dict[str, Any]:
    """Invoke a specialist agent via NEON multi-provider failover chain or honest deterministic fallback."""
    agent = db.get(AgentRecord, agent_id)
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found in catalog.")

    clean_prompt = sanitize_prompt_input(prompt, reject_injection=True)
    interception = intercept_and_redact_secrets(
        clean_prompt,
        db=db if tenant_id else None,
        principal=None,
        settings=settings,
        source_context=f"neon:{agent_id}",
        auto_vault=False,
    )
    clean_prompt = interception.sanitized_text
    tier = max(1, min(5, int(reasoning_tier or agent.default_reasoning_tier)))
    tier_meta = get_reasoning_tiers(settings)[tier]
    primary_model = tier_meta["primary_model"]

    full_prompt = clean_prompt
    if context:
        full_prompt = f"Context:\n{json.dumps(context, default=str)}\n\nDirective:\n{clean_prompt}"
    if response_format == "json":
        full_prompt += "\n\nRespond ONLY with valid JSON."

    provider_chain = providers
    if provider_chain is None and gemini_client is not None:
        wrapper = GeminiLLMProvider(settings)
        wrapper._client = gemini_client
        provider_chain = [wrapper]

    started = time.perf_counter()
    llm_response, failover_errors = execute_with_failover(
        settings=settings,
        prompt=full_prompt,
        system_instruction=agent.system_instruction,
        primary_model=primary_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        providers=provider_chain,
    )

    if llm_response is not None:
        provider_name = llm_response["provider"]
        exec_mode = f"{provider_name}_live"
        raw_text = llm_response["text"]
        structured_output: Any = None
        if response_format == "json":
            try:
                structured_output = json.loads(raw_text)
            except json.JSONDecodeError:
                structured_output = {"raw_text": raw_text, "json_valid": False}

        cost = 0.0
        if tenant_id:
            cost = _record_usage_log(
                db,
                tenant_id=tenant_id,
                actor=actor,
                agent_id=agent.agent_id,
                provider=provider_name,
                model=llm_response["model"],
                reasoning_tier=tier,
                execution_mode=exec_mode,
                usage=llm_response["usage"],
                latency_ms=llm_response["latency_ms"],
            )
        agent.total_latency_ms += llm_response["latency_ms"]
        agent.last_active = datetime.now(timezone.utc)
        return {
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "domain": agent.domain,
            "reasoning_tier": tier,
            "provider": provider_name,
            "model": llm_response["model"],
            "execution_mode": exec_mode,
            "output": raw_text,
            "structured_output": structured_output,
            "failover_errors": failover_errors,
            "latency_ms": llm_response["latency_ms"],
            "usage": llm_response["usage"],
            "estimated_cost_usd": cost,
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    if failover_errors:
        import logging

        last_err = failover_errors[-1]
        safe_reason = f"{last_err.get('provider', 'llm')}/{last_err.get('model', primary_model)}: {last_err.get('error', 'unknown')}"
        logging.getLogger("ultron.neon").warning(
            "NEON degraded fallback after upstream provider errors: agent=%s tier=%s attempts=%d errors=%s",
            agent.agent_id,
            tier,
            len(failover_errors),
            failover_errors,
        )
        exec_mode = "degraded_fallback_after_provider_error"
        output_text = (
            f"[{agent.agent_id} | {agent.name}] Upstream LLM providers failed "
            f"({len(failover_errors)} attempts; last error: {safe_reason}). "
            f"Structured directive captured for '{agent.domain}': {clean_prompt}"
        )
    else:
        exec_mode = "local_deterministic_fallback"
        output_text = (
            f"[{agent.agent_id} | {agent.name}] Processed directive in deterministic offline mode "
            f"(no live LLM provider configured). Domain: {agent.domain}. Objective: {clean_prompt}"
        )

    structured_fallback = (
        {
            "agent_id": agent.agent_id,
            "domain": agent.domain,
            "execution_mode": exec_mode,
            "summary": output_text,
            "live_model_executed": False,
        }
        if response_format == "json"
        else None
    )

    if tenant_id:
        _record_usage_log(
            db,
            tenant_id=tenant_id,
            actor=actor,
            agent_id=agent.agent_id,
            provider="local_fallback",
            model=primary_model,
            reasoning_tier=tier,
            execution_mode=exec_mode,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            latency_ms=latency_ms,
        )

    agent.total_latency_ms += latency_ms
    agent.last_active = datetime.now(timezone.utc)
    return {
        "agent_id": agent.agent_id,
        "agent_name": agent.name,
        "domain": agent.domain,
        "reasoning_tier": tier,
        "provider": "local_fallback",
        "model": primary_model,
        "execution_mode": exec_mode,
        "output": output_text,
        "structured_output": structured_fallback,
        "failover_errors": failover_errors,
        "latency_ms": latency_ms,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "estimated_cost_usd": 0.0,
    }


def stream_neon_events(result: dict[str, Any]) -> Generator[str, None, None]:
    """Yield SSE (`text/event-stream`) frames cleanly representing streamed NEON tokens & completion."""
    meta = {
        "agent_id": result["agent_id"],
        "provider": result["provider"],
        "model": result["model"],
        "execution_mode": result["execution_mode"],
        "reasoning_tier": result["reasoning_tier"],
    }
    yield f"event: metadata\ndata: {json.dumps(meta)}\n\n"
    words = (result.get("output") or "").split(" ")
    chunk_size = 6
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
    yield f"event: done\ndata: {json.dumps({'usage': result.get('usage', {}), 'estimated_cost_usd': result.get('estimated_cost_usd', 0.0)})}\n\n"


def create_conversation(
    db: Session,
    *,
    principal: Principal,
    title: str,
    agent_id: str = "AGT-01",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if db.get(AgentRecord, agent_id) is None:
        raise NotFoundError(f"Agent '{agent_id}' not found.")
    conv = ConversationRecord(
        conversation_id=f"cnv_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        agent_id=agent_id,
        title=title.strip()[:200],
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(conv, [])


def list_conversations(db: Session, *, principal: Principal, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ConversationRecord)
        .where(ConversationRecord.tenant_id == principal.tenant_id)
        .order_by(ConversationRecord.updated_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_serialize_conversation(r, None) for r in rows]


def get_conversation(db: Session, *, principal: Principal, conversation_id: str) -> dict[str, Any]:
    conv = db.execute(
        select(ConversationRecord).where(
            ConversationRecord.conversation_id == conversation_id,
            ConversationRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError(f"Conversation '{conversation_id}' not found.")
    msgs = db.execute(
        select(ConversationMessageRecord)
        .where(ConversationMessageRecord.conversation_id == conversation_id)
        .order_by(ConversationMessageRecord.created_at.asc())
    ).scalars().all()
    return _serialize_conversation(conv, list(msgs))


def send_conversation_message(
    db: Session,
    *,
    principal: Principal,
    conversation_id: str,
    content: str,
    settings: Settings,
    reasoning_tier: int | None = None,
) -> dict[str, Any]:
    conv = db.execute(
        select(ConversationRecord).where(
            ConversationRecord.conversation_id == conversation_id,
            ConversationRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError(f"Conversation '{conversation_id}' not found.")

    raw_clean = sanitize_prompt_input(content, reject_injection=True)
    interception = intercept_and_redact_secrets(
        raw_clean,
        db=db,
        principal=principal,
        settings=settings,
        source_context=f"conversation:{conversation_id}",
        auto_vault=True,
    )
    clean_content = interception.sanitized_text
    history_rows = db.execute(
        select(ConversationMessageRecord)
        .where(ConversationMessageRecord.conversation_id == conversation_id)
        .order_by(ConversationMessageRecord.created_at.desc())
        .limit(12)
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

    user_msg = ConversationMessageRecord(
        message_id=f"cmsg_{uuid.uuid4().hex[:16]}",
        conversation_id=conversation_id,
        role="user",
        content=clean_content,
        token_count=len(clean_content.split()),
    )
    db.add(user_msg)
    db.flush()

    reply = invoke_agent_reasoning(
        db,
        agent_id=conv.agent_id,
        prompt=clean_content,
        settings=settings,
        context={"conversation_history": history},
        reasoning_tier=reasoning_tier,
        tenant_id=principal.tenant_id,
        actor=principal.username,
    )

    asst_msg = ConversationMessageRecord(
        message_id=f"cmsg_{uuid.uuid4().hex[:16]}",
        conversation_id=conversation_id,
        role="assistant",
        content=reply["output"],
        model=reply["model"],
        token_count=int(reply["usage"].get("completion_tokens", 0)),
    )
    db.add(asst_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "conversation_id": conversation_id,
        "user_message_id": user_msg.message_id,
        "assistant_message_id": asst_msg.message_id,
        "sanitized_user_message": clean_content,
        "secret_interception": {
            "secrets_vaulted": interception.secrets_vaulted,
            "payment_data_blocked": interception.payment_data_blocked,
            "warnings": interception.warnings,
        },
        "reply": reply,
    }


def get_usage_summary(db: Session, *, tenant_id: str) -> dict[str, Any]:
    totals = db.execute(
        select(
            func.count(LLMUsageLog.usage_id),
            func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0),
            func.coalesce(func.avg(LLMUsageLog.latency_ms), 0.0),
        ).where(LLMUsageLog.tenant_id == tenant_id)
    ).one()

    by_provider_rows = db.execute(
        select(
            LLMUsageLog.provider,
            LLMUsageLog.execution_mode,
            func.count(LLMUsageLog.usage_id),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0),
        )
        .where(LLMUsageLog.tenant_id == tenant_id)
        .group_by(LLMUsageLog.provider, LLMUsageLog.execution_mode)
    ).all()

    return {
        "tenant_id": tenant_id,
        "total_calls": int(totals[0]),
        "prompt_tokens": int(totals[1]),
        "completion_tokens": int(totals[2]),
        "total_tokens": int(totals[3]),
        "estimated_cost_usd": round(float(totals[4]), 6),
        "avg_latency_ms": round(float(totals[5]), 2),
        "breakdown": [
            {
                "provider": r[0],
                "execution_mode": r[1],
                "calls": int(r[2]),
                "total_tokens": int(r[3]),
                "estimated_cost_usd": round(float(r[4]), 6),
            }
            for r in by_provider_rows
        ],
    }


def _serialize_conversation(
    conv: ConversationRecord,
    messages: list[ConversationMessageRecord] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "conversation_id": conv.conversation_id,
        "tenant_id": conv.tenant_id,
        "user_id": conv.user_id,
        "agent_id": conv.agent_id,
        "title": conv.title,
        "metadata": json.loads(conv.metadata_json or "{}"),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }
    if messages is not None:
        out["messages"] = [
            {
                "message_id": m.message_id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    return out


__all__ = [
    "create_conversation",
    "get_conversation",
    "get_model_capability_registry",
    "get_reasoning_tiers",
    "get_usage_summary",
    "invoke_agent_reasoning",
    "list_conversations",
    "route_objective",
    "send_conversation_message",
    "stream_neon_events",
]
