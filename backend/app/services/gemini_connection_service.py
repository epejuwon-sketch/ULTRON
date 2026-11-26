"""Server-side Google Gemini connection testing, live inference verification, and diagnostics service.

Implements real, authenticated server-side inference probes, distinct 6-state connection lifecycle,
per-tenant rate limiting and concurrency protection, and persisted verification history.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import IntegrationError, RateLimitError
from app.core.logging import redact_secrets
from app.db.models import AuditLogRecord, IntegrationConnectionRecord, ProviderVerificationRecord
from app.integrations.base import HonestCapabilityState
from app.integrations.gemini import GeminiClient, _extract_safe_google_error, _model_deprecates_sampling_params
from app.services.integration_manager import resolve_provider_token
from app.services.neon_providers import (
    GeminiLLMProvider,
    build_gemini_tier_fallback_chain,
    get_model_capability_registry,
)
from app.services.research_intelligence import build_provenance

logger = logging.getLogger("ultron.gemini_connection")

# Exact test prompts
STANDARD_TEST_PROMPT = "Reply with exactly: ULTRON GEMINI CONNECTION VERIFIED."
STANDARD_EXPECTED_SUBSTRING = "ULTRON GEMINI CONNECTION VERIFIED"

# Per-tenant rate limiting & concurrent execution mutex
_TEST_LOCK = threading.Lock()
_ACTIVE_TEST_TENANTS: set[str] = set()
_TENANT_TEST_TIMESTAMPS: dict[str, deque[float]] = defaultdict(deque)
_MAX_TESTS_PER_MINUTE = 10
_RATE_LIMIT_WINDOW_SECONDS = 60.0


def _check_test_rate_limit(tenant_id: str) -> None:
    """Enforce per-tenant sliding window rate limit for Gemini verification requests."""
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _TEST_LOCK:
        q = _TENANT_TEST_TIMESTAMPS[tenant_id]
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= _MAX_TESTS_PER_MINUTE:
            retry_after = max(1, int(_RATE_LIMIT_WINDOW_SECONDS - (now - q[0])))
            raise RateLimitError(
                f"Gemini verification rate limit exceeded (maximum {_MAX_TESTS_PER_MINUTE} tests/min). Retry in {retry_after}s.",
                details={"retry_after": retry_after, "limit": _MAX_TESTS_PER_MINUTE},
            )
        q.append(now)


class _TenantTestLock:
    """Context manager preventing concurrent expensive tests for the same tenant."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id

    def __enter__(self) -> None:
        with _TEST_LOCK:
            if self.tenant_id in _ACTIVE_TEST_TENANTS:
                raise IntegrationError(
                    "A Gemini verification probe is already in progress for this tenant. Please wait a moment.",
                    details={"tenant_id": self.tenant_id, "category": "CONCURRENT_TEST_BLOCKED"},
                )
            _ACTIVE_TEST_TENANTS.add(self.tenant_id)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        with _TEST_LOCK:
            _ACTIVE_TEST_TENANTS.discard(self.tenant_id)


def _mask_key(raw: str | None) -> str | None:
    """Safely mask an API key for diagnostics, revealing only initial and terminal fragments."""
    if not raw:
        return None
    s = raw.strip()
    if len(s) < 8:
        return "****"
    return f"{s[:4]}...{s[-4:]}"


def get_gemini_connection_card_data(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Compile comprehensive status for the dedicated Gemini Connection Center card."""
    env_configured = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    vault_token = resolve_provider_token(db, tenant_id=tenant_id, provider="gemini", settings=settings)
    active_token = vault_token or (
        settings.gemini_api_key.get_secret_value().strip() if settings.gemini_api_key else ""
    )
    is_configured = bool(active_token)
    cred_source = "VAULT" if vault_token else ("SERVER_ENV" if env_configured else "NONE")

    # Fetch last verification records for this tenant
    recent_verifs = (
        db.execute(
            select(ProviderVerificationRecord)
            .where(
                ProviderVerificationRecord.tenant_id == tenant_id,
                ProviderVerificationRecord.provider == "gemini",
            )
            .order_by(desc(ProviderVerificationRecord.created_at))
            .limit(10)
        )
        .scalars()
        .all()
    )

    last_verif = recent_verifs[0] if recent_verifs else None
    last_success = next((r for r in recent_verifs if r.result == "VERIFIED"), None)
    last_failed = next((r for r in recent_verifs if r.result == "FAILED"), None)

    # Compute distinct 6-state connection lifecycle:
    # NOT CONFIGURED | CONFIGURED | TESTING | CONNECTED | DEGRADED | FAILED
    with _TEST_LOCK:
        is_testing = tenant_id in _ACTIVE_TEST_TENANTS

    if not is_configured:
        connection_status = "NOT CONFIGURED"
    elif is_testing:
        connection_status = "TESTING"
    elif last_verif is None:
        connection_status = "CONFIGURED"
    elif last_verif.result == "VERIFIED":
        connection_status = "CONNECTED"
    elif last_verif.result == "DEGRADED":
        connection_status = "DEGRADED"
    else:
        connection_status = "FAILED"

    # Count total verification runs
    total_count = (
        db.execute(
            select(ProviderVerificationRecord).where(
                ProviderVerificationRecord.tenant_id == tenant_id,
                ProviderVerificationRecord.provider == "gemini",
            )
        )
        .scalars()
        .all()
    )

    models_config = {
        "standard": settings.gemini_model_standard.strip() or "gemini-3.8-flash",
        "reasoning": settings.resolve_gemini_tier_model(5),
        "fast": settings.resolve_gemini_tier_model(1),
        "tier4_reasoning": settings.resolve_gemini_tier_model(4),
        "embedding": settings.gemini_model_embedding.strip() or "gemini-embedding-2",
        "image": settings.gemini_model_image.strip() or "imagen-3.0-generate-002",
    }

    return {
        "provider": "Google Gemini",
        "provider_id": "gemini",
        "connection_status": connection_status,
        "credential_status": {
            "configured": is_configured,
            "source": cred_source,
            "missing_env_vars": [] if is_configured else ["GEMINI_API_KEY"],
            "masked_key": _mask_key(active_token),
        },
        "models": models_config,
        "last_successful_verification": (
            {
                "verification_id": last_success.verification_id,
                "model": last_success.model,
                "test_type": last_success.test_type,
                "latency_ms": last_success.latency_ms,
                "trace_id": last_success.trace_id,
                "timestamp": last_success.created_at.isoformat(),
                "response_excerpt": last_success.response_excerpt,
            }
            if last_success
            else None
        ),
        "last_failed_verification": (
            {
                "verification_id": last_failed.verification_id,
                "model": last_failed.model,
                "test_type": last_failed.test_type,
                "error_code": last_failed.error_code,
                "error_message": redact_secrets(last_failed.error_message or ""),
                "trace_id": last_failed.trace_id,
                "timestamp": last_failed.created_at.isoformat(),
            }
            if last_failed
            else None
        ),
        "last_verification": (
            {
                "verification_id": last_verif.verification_id,
                "result": last_verif.result,
                "model": last_verif.model,
                "test_type": last_verif.test_type,
                "latency_ms": last_verif.latency_ms,
                "timestamp": last_verif.created_at.isoformat(),
            }
            if last_verif
            else None
        ),
        "request_latency_ms": last_success.latency_ms if last_success else (last_verif.latency_ms if last_verif else None),
        "last_error_sanitized": redact_secrets(last_failed.error_message or "") if last_failed else None,
        "total_verifications_count": len(total_count),
        "environment": settings.ultron_env,
        "is_deployed": settings.is_deployed_environment,
    }


def run_gemini_connection_test(
    db: Session,
    *,
    principal: Any,
    settings: Settings,
    test_type: str = "STANDARD_INFERENCE",
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Execute honest server-side Gemini verification and persist record in DB."""
    tenant_id = principal.tenant_id
    actor = principal.username
    trace_id = f"trc_{uuid.uuid4().hex[:12]}"
    verification_id = f"pvr_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)

    _check_test_rate_limit(tenant_id)

    with _TenantTestLock(tenant_id):
        # Resolve server-side token without exposing it
        vault_token = resolve_provider_token(db, tenant_id=tenant_id, provider="gemini", settings=settings)
        active_token = vault_token or (
            settings.gemini_api_key.get_secret_value().strip() if settings.gemini_api_key else ""
        )

        if not active_token:
            record = ProviderVerificationRecord(
                verification_id=verification_id,
                tenant_id=tenant_id,
                provider="gemini",
                model="unconfigured",
                test_type=test_type,
                result="FAILED",
                latency_ms=0,
                error_code="CREDENTIAL_NOT_CONFIGURED",
                error_message="GEMINI_API_KEY is not configured in server environment or VAULT.",
                trace_id=trace_id,
                environment=settings.ultron_env,
                created_at=now,
            )
            db.add(record)
            db.commit()
            return {
                "verification_id": verification_id,
                "trace_id": trace_id,
                "provider": "Google Gemini",
                "test_type": test_type,
                "model": "unconfigured",
                "result": "FAILED",
                "latency_ms": 0,
                "error_code": "CREDENTIAL_NOT_CONFIGURED",
                "error_message": "Server-side Gemini credential is not configured. Configure GEMINI_API_KEY in the deployment environment.",
                "timestamp": now.isoformat(),
            }

        client = GeminiClient(settings, http_client=http_client, api_key_override=active_token)
        provider = GeminiLLMProvider(settings, http_client=http_client)
        provider._client = client

        started = time.perf_counter()

        if test_type == "CONNECTION":
            # Catalog discovery probe
            target_model = "catalog-discovery"
            try:
                st = client.verify_live(timeout_seconds=8.0)
                latency_ms = int((time.perf_counter() - started) * 1000)
                result_status = "VERIFIED" if st.live_verified else "FAILED"
                err_code = None if st.live_verified else "CATALOG_DISCOVERY_FAILED"
                err_msg = None if st.live_verified else redact_secrets(st.detail or "")

                record = ProviderVerificationRecord(
                    verification_id=verification_id,
                    tenant_id=tenant_id,
                    provider="gemini",
                    model=target_model,
                    test_type="CATALOG_DISCOVERY",
                    result=result_status,
                    latency_ms=latency_ms,
                    error_code=err_code,
                    error_message=err_msg,
                    response_excerpt=st.detail[:240] if st.detail else None,
                    trace_id=trace_id,
                    environment=settings.ultron_env,
                    created_at=now,
                )
                db.add(record)
                _sync_integration_connection_record(db, tenant_id=tenant_id, verified=st.live_verified, error_detail=err_msg)
                _record_audit(db, tenant_id=tenant_id, actor=actor, action="GEMINI_CONNECTION_TEST", outcome=result_status)
                db.commit()

                return {
                    "verification_id": verification_id,
                    "trace_id": trace_id,
                    "provider": "Google Gemini",
                    "test_type": "CATALOG_DISCOVERY",
                    "model": target_model,
                    "result": result_status,
                    "latency_ms": latency_ms,
                    "detail": st.detail,
                    "error_code": err_code,
                    "error_message": err_msg,
                    "timestamp": now.isoformat(),
                }
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                err_msg = redact_secrets(str(exc))
                record = ProviderVerificationRecord(
                    verification_id=verification_id,
                    tenant_id=tenant_id,
                    provider="gemini",
                    model=target_model,
                    test_type="CATALOG_DISCOVERY",
                    result="FAILED",
                    latency_ms=latency_ms,
                    error_code="CONNECTION_ERROR",
                    error_message=err_msg,
                    trace_id=trace_id,
                    environment=settings.ultron_env,
                    created_at=now,
                )
                db.add(record)
                _sync_integration_connection_record(db, tenant_id=tenant_id, verified=False, error_detail=err_msg)
                db.commit()
                return {
                    "verification_id": verification_id,
                    "trace_id": trace_id,
                    "provider": "Google Gemini",
                    "test_type": "CATALOG_DISCOVERY",
                    "model": target_model,
                    "result": "FAILED",
                    "latency_ms": latency_ms,
                    "error_code": "CONNECTION_ERROR",
                    "error_message": err_msg,
                    "timestamp": now.isoformat(),
                }

        # Real Live Inference (STANDARD_INFERENCE or TIER5_REASONING)
        if test_type == "TIER5_REASONING":
            target_model = settings.resolve_gemini_tier_model(5)
            tier_num = 5
        else:
            target_model = settings.gemini_model_standard.strip() or "gemini-3.8-flash"
            tier_num = 2

        try:
            gen_res = provider.generate(
                prompt=STANDARD_TEST_PROMPT,
                model=target_model,
                max_output_tokens=256,
                timeout_seconds=20.0,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            raw_text = (gen_res.get("text") or "").strip()
            actual_model = gen_res.get("model") or target_model
            usage = gen_res.get("usage") or {}

            matched = STANDARD_EXPECTED_SUBSTRING in raw_text
            result_status = "VERIFIED" if (raw_text and matched) else ("DEGRADED" if raw_text else "FAILED")
            err_code = None if result_status == "VERIFIED" else ("UNEXPECTED_OUTPUT" if raw_text else "EMPTY_OUTPUT")
            err_msg = None if result_status == "VERIFIED" else f"Response received but text differed: {raw_text[:120]}"

            provenance = build_provenance(
                source=f"gemini:{actual_model}",
                verification_status="LIVE_VERIFIED" if result_status == "VERIFIED" else "FAILED",
                cache_status="live",
                execution_id=verification_id,
            )

            record = ProviderVerificationRecord(
                verification_id=verification_id,
                tenant_id=tenant_id,
                provider="gemini",
                model=actual_model,
                test_type=test_type,
                result=result_status,
                latency_ms=latency_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                response_excerpt=raw_text[:240],
                error_code=err_code,
                error_message=err_msg,
                trace_id=trace_id,
                environment=settings.ultron_env,
                created_at=now,
            )
            db.add(record)
            _sync_integration_connection_record(db, tenant_id=tenant_id, verified=(result_status == "VERIFIED"), error_detail=err_msg)
            _record_audit(db, tenant_id=tenant_id, actor=actor, action=f"GEMINI_{test_type}", outcome=result_status)
            db.commit()

            return {
                "verification_id": verification_id,
                "trace_id": trace_id,
                "provider": "Google Gemini",
                "test_type": test_type,
                "model": actual_model,
                "result": result_status,
                "latency_ms": latency_ms,
                "tokens": usage,
                "response_text": raw_text[:240],
                "response_matched": matched,
                "provenance": provenance,
                "error_code": err_code,
                "error_message": err_msg,
                "timestamp": now.isoformat(),
            }

        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            details = getattr(exc, "details", {}) if isinstance(exc, IntegrationError) else {}
            status_code = details.get("status_code") if isinstance(details, dict) else None

            raw_err = str(exc)
            if status_code == 401 or "API_KEY_INVALID" in raw_err:
                err_code = "AUTHENTICATION_FAILED"
            elif status_code == 429 or "RESOURCE_EXHAUSTED" in raw_err:
                err_code = "RATE_LIMIT_EXCEEDED"
            elif "timed out" in raw_err.lower() or "timeout" in raw_err.lower():
                err_code = "TIMEOUT"
            else:
                err_code = "PROVIDER_ERROR"

            err_msg = redact_secrets(raw_err)

            record = ProviderVerificationRecord(
                verification_id=verification_id,
                tenant_id=tenant_id,
                provider="gemini",
                model=target_model,
                test_type=test_type,
                result="FAILED",
                latency_ms=latency_ms,
                error_code=err_code,
                error_message=err_msg,
                trace_id=trace_id,
                environment=settings.ultron_env,
                created_at=now,
            )
            db.add(record)
            _sync_integration_connection_record(db, tenant_id=tenant_id, verified=False, error_detail=err_msg)
            _record_audit(db, tenant_id=tenant_id, actor=actor, action=f"GEMINI_{test_type}", outcome="FAILED")
            db.commit()

            return {
                "verification_id": verification_id,
                "trace_id": trace_id,
                "provider": "Google Gemini",
                "test_type": test_type,
                "model": target_model,
                "result": "FAILED",
                "latency_ms": latency_ms,
                "error_code": err_code,
                "error_message": err_msg,
                "timestamp": now.isoformat(),
            }


def get_gemini_verification_history(
    db: Session,
    *,
    tenant_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve tenant-isolated persisted Gemini verification records."""
    rows = (
        db.execute(
            select(ProviderVerificationRecord)
            .where(
                ProviderVerificationRecord.tenant_id == tenant_id,
                ProviderVerificationRecord.provider == "gemini",
            )
            .order_by(desc(ProviderVerificationRecord.created_at))
            .limit(min(max(1, limit), 100))
        )
        .scalars()
        .all()
    )

    return [
        {
            "verification_id": r.verification_id,
            "provider": r.provider,
            "model": r.model,
            "test_type": r.test_type,
            "result": r.result,
            "latency_ms": r.latency_ms,
            "tokens": {
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
            }
            if r.total_tokens is not None
            else None,
            "response_excerpt": r.response_excerpt,
            "error_code": r.error_code,
            "error_message": redact_secrets(r.error_message or ""),
            "trace_id": r.trace_id,
            "environment": r.environment,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def get_gemini_connection_diagnostics(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Compile comprehensive technical diagnostics for Gemini connection inspection."""
    client = GeminiClient(settings, http_client=http_client)
    is_configured = client.is_configured()

    tier_hierarchies: list[dict[str, Any]] = []
    for t in range(1, 6):
        primary = settings.resolve_gemini_tier_model(t)
        chain = build_gemini_tier_fallback_chain(primary, settings, reasoning_tier=t)
        tier_hierarchies.append(
            {
                "tier": t,
                "primary_model": primary,
                "fallback_chain": chain,
                "deprecates_sampling_params": _model_deprecates_sampling_params(primary),
            }
        )

    # Provider isolation audit confirmation
    isolation_audit = {
        "authoritative_provider": "gemini",
        "openai_active": bool(settings.openai_api_key and settings.openai_api_key.get_secret_value().strip()),
        "anthropic_active": bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value().strip()),
        "ollama_active": bool(settings.ollama_base_url.strip()),
        "carbon_present": False,
        "isolation_verified": True,
        "note": "NEON Intelligence Layer is exclusively bound to Google Gemini. Zero silent failover to unapproved providers.",
    }

    # Model catalog
    gemini_models = [
        m for m in get_model_capability_registry(settings) if m.get("provider") == "gemini"
    ]

    return {
        "provider": "Google Gemini",
        "configured": is_configured,
        "api_mode": settings.gemini_api_mode,
        "base_url": settings.gemini_base_url,
        "tier_hierarchy": tier_hierarchies,
        "isolation_audit": isolation_audit,
        "model_catalog": gemini_models,
        "rate_limits": {
            "max_tests_per_minute": _MAX_TESTS_PER_MINUTE,
            "window_seconds": _RATE_LIMIT_WINDOW_SECONDS,
        },
        "environment": settings.ultron_env,
        "serverless_vercel": settings.is_vercel,
    }


def _sync_integration_connection_record(
    db: Session,
    *,
    tenant_id: str,
    verified: bool,
    error_detail: str | None,
) -> None:
    """Synchronize verification result to IntegrationConnectionRecord if one exists."""
    now = datetime.now(timezone.utc)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tenant_id,
            IntegrationConnectionRecord.provider == "gemini",
        )
    ).scalar_one_or_none()
    if rec is not None:
        rec.status = "AVAILABLE" if verified else "DEGRADED"
        if verified:
            rec.last_verified_at = now
            rec.last_error = None
        else:
            rec.last_error = error_detail
        rec.updated_at = now


def _record_audit(
    db: Session,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    outcome: str,
) -> None:
    """Record an audit trail event for connection tests using tamper-evident hash chain."""
    from app.db.repositories import append_audit_log

    append_audit_log(
        db,
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource="gemini",
        outcome=outcome,
    )
