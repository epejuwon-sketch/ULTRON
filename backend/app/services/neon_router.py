"""NEON 5-Tier Cognitive Router and live Gemini / honest deterministic fallback executor."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.security import classify_risk_level, sanitize_prompt_input
from app.db.models import AgentRecord
from app.integrations.gemini import GeminiClient

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
            "purpose": "Low-latency status checks, telemetry triage, and direct deterministic actions.",
        },
        2: {
            "tier": 2,
            "name": "Tier 2: Standard Reasoning",
            "primary_model": settings.gemini_model_standard,
            "purpose": "Routine reasoning, single-domain execution, and structured summaries.",
        },
        3: {
            "tier": 3,
            "name": "Tier 3: Complex Engineering & Problem Solving",
            "primary_model": settings.gemini_model_standard,
            "purpose": "Multi-step planning, debugging, workflow design, and code synthesis.",
        },
        4: {
            "tier": 4,
            "name": "Tier 4: Deep Research & Risk Analysis",
            "primary_model": settings.gemini_model_reasoning,
            "purpose": "Financial modeling, legal/security analysis, and deep evidence synthesis.",
        },
        5: {
            "tier": 5,
            "name": "Tier 5: Multi-Agent Executive Orchestration",
            "primary_model": settings.gemini_model_reasoning,
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
        for keywords, agent_id in DOMAIN_ROUTING_RULES:
            if any(kw in lowered for kw in keywords):
                selected_agent = agent_id
                break

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
        "risk_level": risk_level,
        "requires_approval_gate": risk_level == "HIGH" or financial_amount_usd > settings.approval_soft_limit_usd,
    }


def invoke_agent_reasoning(
    db: Session,
    *,
    agent_id: str,
    prompt: str,
    settings: Settings,
    context: dict[str, Any] | None = None,
    reasoning_tier: int | None = None,
    gemini_client: GeminiClient | None = None,
) -> dict[str, Any]:
    """Invoke a specialist agent via Gemini API when configured, or honest deterministic fallback."""
    agent = db.get(AgentRecord, agent_id)
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' not found in catalog.")

    clean_prompt = sanitize_prompt_input(prompt, reject_injection=True)
    tier = reasoning_tier or agent.default_reasoning_tier
    tier = max(1, min(5, int(tier)))
    tier_meta = get_reasoning_tiers(settings)[tier]
    model = tier_meta["primary_model"]

    client = gemini_client or GeminiClient(settings)
    started = time.perf_counter()

    full_prompt = clean_prompt
    if context:
        full_prompt = f"Context:\n{context}\n\nDirective:\n{clean_prompt}"

    if client.is_configured():
        try:
            response = client.generate_content(
                prompt=full_prompt,
                system_instruction=agent.system_instruction,
                model=model,
            )
            return {
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "domain": agent.domain,
                "reasoning_tier": tier,
                "model": response["model"],
                "execution_mode": "gemini_live",
                "output": response["text"],
                "latency_ms": response["latency_ms"],
                "usage": response["usage"],
            }
        except Exception as exc:
            # Honestly surface upstream failure and provide structured fallback note
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "domain": agent.domain,
                "reasoning_tier": tier,
                "model": model,
                "execution_mode": "degraded_fallback_after_provider_error",
                "provider_error": str(exc),
                "output": (
                    f"[{agent.agent_id} | {agent.name}] Upstream Gemini call failed ({exc}). "
                    f"Structured directive captured for domain '{agent.domain}': {clean_prompt}"
                ),
                "latency_ms": latency_ms,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "agent_id": agent.agent_id,
        "agent_name": agent.name,
        "domain": agent.domain,
        "reasoning_tier": tier,
        "model": model,
        "execution_mode": "local_deterministic_fallback",
        "output": (
            f"[{agent.agent_id} | {agent.name}] Processed directive in deterministic offline mode "
            f"(GEMINI_API_KEY not configured). Domain: {agent.domain}. Objective: {clean_prompt}"
        ),
        "latency_ms": latency_ms,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
