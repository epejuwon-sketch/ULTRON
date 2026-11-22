"""Comprehensive verification tests for ULTRON OS 2026 Google Gemini Primary Intelligence Configuration.

Covers:
1. 5-tier configurable Gemini model assignments and controlled intra-Gemini fallback chains.
2. Live model catalogue discovery & rich capability metadata parsing.
3. All 60 specialist agents routing through shared Gemini intelligence while preserving unique identity/instructions/tools/scopes.
4. Google Interactions API (/v1beta/interactions) adapter with store=false privacy default & non-breaking fallback to generateContent.
5. Structured JSON output (responseMimeType), native function/tool calling, SSE streaming, timeout/retry/fallback behavior.
6. Honest separation of catalog-check vs live-inference verification, zero secret exposure, and ApprovalGate immutability.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.db.models import AgentRecord
from app.db.session import get_session_factory
from app.integrations.gemini import GeminiClient
from app.services.neon_providers import build_gemini_tier_fallback_chain
from app.services.neon_router import (
    get_gemini_diagnostics,
    get_reasoning_tiers,
    invoke_agent_reasoning,
    run_gemini_verification_suite,
    stream_live_neon_events,
)


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "ULTRON_ENV": "development",
        "GEMINI_API_KEY": "AIza-test-never-leak-secret-key-2026",
    }
    base.update(overrides)
    return Settings(**base)


def test_five_reasoning_tiers_and_configurable_overrides() -> None:
    cfg = _make_settings()
    tiers = get_reasoning_tiers(cfg)
    assert set(tiers.keys()) == {1, 2, 3, 4, 5}
    assert tiers[1]["primary_model"] == "gemini-3.5-flash-lite"
    assert tiers[2]["primary_model"] == "gemini-3.8-flash"
    assert tiers[3]["primary_model"] == "gemini-3.8-flash"
    assert tiers[4]["primary_model"] == "gemini-4-hydrogen"
    assert tiers[5]["primary_model"] == "gemini-4-carbon"

    # Controlled fallback chain for Tier 5 degrades gracefully from paid Carbon/Argon to Free+Paid Hydrogen/Flash
    t5_chain = build_gemini_tier_fallback_chain("gemini-4-carbon", cfg, reasoning_tier=5)
    assert t5_chain[:4] == ["gemini-4-carbon", "gemini-4-argon", "gemini-4-hydrogen", "gemini-3.8-flash"]

    # Explicit env overrides per tier take precedence without code changes
    custom = _make_settings(
        GEMINI_MODEL_TIER_1="gemini-2.5-flash-lite",
        GEMINI_MODEL_TIER_4="gemini-3.8-flash",
        GEMINI_MODEL_TIER_5="gemini-4-hydrogen",
    )
    custom_tiers = get_reasoning_tiers(custom)
    assert custom_tiers[1]["primary_model"] == "gemini-2.5-flash-lite"
    assert custom_tiers[4]["primary_model"] == "gemini-3.8-flash"
    assert custom_tiers[5]["primary_model"] == "gemini-4-hydrogen"


def test_model_catalog_discovery_and_capability_metadata() -> None:
    cfg = _make_settings()

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers.get("x-goog-api-key") == "AIza-test-never-leak-secret-key-2026"
        assert "key=" not in str(req.url)
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.8-flash",
                        "displayName": "Gemini 3.8 Flash",
                        "supportedGenerationMethods": ["generateContent", "streamGenerateContent", "countTokens"],
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 65536,
                    },
                    {
                        "name": "models/gemini-2.5-flash",
                        "displayName": "Gemini 2.5 Flash",
                        "supportedGenerationMethods": ["generateContent"],
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 65536,
                    },
                    {
                        "name": "models/gemini-embedding-001",
                        "displayName": "Gemini Embedding 001",
                        "supportedGenerationMethods": ["embedContent"],
                        "inputTokenLimit": 2048,
                        "outputTokenLimit": 768,
                    },
                ]
            },
        )

    client = GeminiClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    models = client.list_models()
    assert len(models) == 3

    m38 = next(m for m in models if m["id"] == "gemini-3.8-flash")
    assert m38["supports_generate_content"] is True
    assert m38["supports_streaming"] is True
    assert m38["supports_structured_output"] is True
    assert m38["supports_tool_calling"] is True
    assert m38["supports_interactions_api"] is True
    assert m38["input_token_limit"] == 1048576
    assert m38["deprecation_notice"] is None

    m25 = next(m for m in models if m["id"] == "gemini-2.5-flash")
    assert m25["deprecation_notice"] and "Dec 1, 2026" in m25["deprecation_notice"]

    emb = next(m for m in models if m["id"] == "gemini-embedding-001")
    assert emb["supports_generate_content"] is False
    assert emb["output_modalities"] == ["embedding"]


def test_interactions_api_adapter_privacy_default_and_non_breaking_fallback() -> None:
    seen_calls: list[tuple[str, dict[str, Any]]] = []

    def ok_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode())
        seen_calls.append((req.url.path, body))
        if req.url.path.endswith("/interactions"):
            return httpx.Response(
                200,
                json={
                    "id": "int_test_001",
                    "outputs": [
                        {"type": "thought", "text": "internal reasoning hidden"},
                        {"type": "text", "text": "Interactions API reply verified."},
                    ],
                    "usage": {"total_input_tokens": 18, "total_output_tokens": 6, "total_tokens": 24},
                },
            )
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": "Unexpected path"}})

    cfg_int = _make_settings(GEMINI_API_MODE="interactions")
    client_ok = GeminiClient(cfg_int, http_client=httpx.Client(transport=httpx.MockTransport(ok_handler)))
    res = client_ok.generate(
        prompt="Status check",
        system_instruction="You are AGT-01 Executive Agent.",
        model="gemini-4-carbon",
    )
    assert res["api_interface"] == "interactions"
    assert res["interaction_id"] == "int_test_001"
    assert res["text"] == "Interactions API reply verified."
    assert seen_calls[0][1]["store"] is False  # Strict tenant privacy default!
    assert seen_calls[0][1]["system_instruction"] == "You are AGT-01 Executive Agent."

    # Now simulate HTTP 400 on /interactions -> non-breaking fallback to :generateContent
    fallback_paths: list[str] = []

    def fb_handler(req: httpx.Request) -> httpx.Response:
        fallback_paths.append(req.url.path)
        body = json.loads(req.content.decode())
        if req.url.path.endswith("/interactions"):
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "Schema unsupported"}})
        # Confirm deprecated `temperature` is omitted on Gemini 3.8+/4 models!
        assert "temperature" not in body.get("generationConfig", {})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Fallback generateContent succeeded."}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5, "totalTokenCount": 17},
            },
        )

    client_fb = GeminiClient(cfg_int, http_client=httpx.Client(transport=httpx.MockTransport(fb_handler)))
    res_fb = client_fb.generate(prompt="Test", model="gemini-3.8-flash", response_mime_type="application/json")
    assert res_fb["api_interface"] == "generate_content"
    assert res_fb["text"] == "Fallback generateContent succeeded."
    assert len(fallback_paths) == 2
    assert fallback_paths[0].endswith("/interactions")
    assert fallback_paths[1].endswith(":generateContent")


def test_all_60_agents_preserve_unique_contracts_via_shared_gemini(client: TestClient) -> None:
    """Verify all 60 specialist agents route through shared Gemini while retaining distinct identity & instructions."""
    cfg = _make_settings()
    captured_instructions: dict[str, str] = {}
    captured_models: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode())
        sys_inst = body.get("systemInstruction", {}).get("parts", [{}])[0].get("text", "")
        model_id = req.url.path.split("/models/")[-1].split(":")[0]
        # Simulate paid-only Carbon/Argon 429 on free tier so Tier 5 cleanly falls back to Hydrogen
        if model_id in ("gemini-4-carbon", "gemini-4-argon"):
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Paid tier required"}})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": f"OK via {model_id} | {sys_inst[:40]}"}]}}],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10, "totalTokenCount": 30},
            },
        )

    gem = GeminiClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    session_factory = get_session_factory()
    with session_factory() as db:
        agents = db.query(AgentRecord).order_by(AgentRecord.agent_id.asc()).all()
        assert len(agents) == 60
        for ag in agents:
            res = invoke_agent_reasoning(
                db,
                agent_id=ag.agent_id,
                prompt=f"Verify domain {ag.domain}",
                settings=cfg,
                tenant_id="TENANT-ULTRON-01",
                actor="audit",
                gemini_client=gem,
            )
            assert res["provider"] == "gemini"
            assert res["execution_mode"] == "gemini_live"
            assert res["agent_id"] == ag.agent_id
            assert res["domain"] == ag.domain
            captured_instructions[ag.agent_id] = ag.system_instruction
            captured_models[ag.agent_id] = res["model"]
            if res["reasoning_tier"] == 5:
                assert res["primary_model"] == "gemini-4-carbon"
                assert res["model"] == "gemini-4-hydrogen"
                assert res["fallback_used"] is True
        db.commit()

    # All 60 agents MUST retain 60 distinct system instructions (never collapsed to identical chat sessions)
    assert len(set(captured_instructions.values())) == 60
    assert len(captured_models) == 60


def test_full_verification_suite_streaming_tools_json_fallback_and_approval_gates(client: TestClient) -> None:
    """Exercise all 7 verification checks: 5 tiers, JSON, function calling, SSE stream, fallback/timeout, ApprovalGate."""
    cfg = _make_settings()
    seen_payloads: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent", "streamGenerateContent"], "inputTokenLimit": 1048576, "outputTokenLimit": 65536},
                        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent", "streamGenerateContent"], "inputTokenLimit": 1048576, "outputTokenLimit": 65536},
                    ]
                },
            )
        if ":streamGenerateContent" in path:
            sse = (
                'data: {"candidates":[{"content":{"parts":[{"text":"1, "}]}}]}\n\n'
                'data: {"candidates":[{"content":{"parts":[{"text":"2, 3"}]}}]}\n\n'
            )
            return httpx.Response(200, content=sse.encode(), headers={"Content-Type": "text/event-stream"})

        body = json.loads(req.content.decode())
        seen_payloads.append(body)
        model_id = path.split("/models/")[-1].split(":")[0]
        if model_id == "gemini-invalid-model-probe-404":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": "Model not found"}})
        if body.get("tools"):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "get_ultron_system_status",
                                            "args": {"subsystem": "NEON"},
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 12, "totalTokenCount": 42},
                },
            )
        if body.get("generationConfig", {}).get("responseMimeType") == "application/json":
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": '{"engine":"NEON","verified":true,"tier":2}'}]}}],
                    "usageMetadata": {"promptTokenCount": 25, "candidatesTokenCount": 15, "totalTokenCount": 40},
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": f"VERIFIED:{model_id}"}]}}],
                "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 8, "totalTokenCount": 23},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    principal = Principal(
        user_id="usr_verify",
        username="commander",
        role=Role.OWNER,
        tenant_id="TENANT-ULTRON-01",
        jti="jti_verify_suite",
    )

    session_factory = get_session_factory()
    with session_factory() as db:
        # Before running live inference, catalog discovery alone MUST NOT mark live_inference.verified=True!
        pre_diag = get_gemini_diagnostics(
            db,
            tenant_id=principal.tenant_id,
            settings=cfg,
            discover_live=True,
            http_client=http_client,
        )
        assert pre_diag["catalog"]["catalog_verified"] is True
        assert pre_diag["catalog"]["models_discovered"] == 2
        assert pre_diag["live_inference"]["verified"] is False
        assert pre_diag["live_inference"]["status"] == "NOT TESTED"

        # Execute full verification suite
        suite = run_gemini_verification_suite(db, principal=principal, settings=cfg, http_client=http_client)
        assert suite["configured"] is True
        assert suite["overall_status"] in ("LIVE VERIFIED", "LIVE VERIFIED WITH FALLBACK")
        assert len(suite["tier_results"]) == 5
        assert all(r["status"] == "LIVE VERIFIED" for r in suite["tier_results"])

        checks = {c["check"]: c for c in suite["capability_checks"]}
        assert checks["structured_output"]["status"] == "LIVE VERIFIED"
        assert checks["tool_calling"]["status"] == "LIVE VERIFIED"
        assert checks["tool_calling"]["function_calls_returned"] == 1
        assert checks["streaming"]["status"] == "LIVE VERIFIED"
        assert checks["streaming"]["chunks_received"] == 2
        assert checks["fallback_and_timeout"]["status"] == "LIVE VERIFIED WITH FALLBACK"
        assert checks["approval_gate_enforcement"]["status"] == "LIVE VERIFIED"
        assert checks["approval_gate_enforcement"]["requires_approval_gate"] is True

        # Live SSE endpoint generator streams real Gemini chunks
        frames = list(
            stream_live_neon_events(
                db,
                agent_id="AGT-01",
                prompt="Stream test",
                settings=cfg,
                reasoning_tier=1,
                tenant_id=principal.tenant_id,
                actor=principal.username,
                gemini_client=GeminiClient(cfg, http_client=http_client),
            )
        )
        joined = "".join(frames)
        assert "event: metadata" in joined
        assert "stream_generate_content" in joined
        assert "1, " in joined and "2, 3" in joined
        assert "event: done" in joined

        # After live inference, diagnostics now honestly reports LIVE VERIFIED + latency + last_successful_check_at
        post_diag = get_gemini_diagnostics(
            db,
            tenant_id=principal.tenant_id,
            settings=cfg,
            discover_live=False,
            http_client=http_client,
        )
        assert post_diag["live_inference"]["verified"] is True
        assert post_diag["live_inference"]["total_live_calls"] >= 8
        assert post_diag["live_inference"]["last_successful_check_at"] is not None
        # Ensure API key NEVER leaks into diagnostics payload
        assert "AIza-test-never-leak-secret-key-2026" not in json.dumps(post_diag)
        assert "AIza-test-never-leak-secret-key-2026" not in json.dumps(suite)


def test_timeout_handling_surfaces_clean_degraded_error(client: TestClient) -> None:
    """Confirm upstream timeout retries and returns honest degraded fallback without crashing."""
    cfg = _make_settings(GEMINI_REQUEST_TIMEOUT_SECONDS=3.0, GEMINI_MAX_RETRIES=1)

    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated upstream timeout")

    gem = GeminiClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(timeout_handler)))
    session_factory = get_session_factory()
    with session_factory() as db:
        res = invoke_agent_reasoning(
            db,
            agent_id="AGT-01",
            prompt="Timeout test",
            settings=cfg,
            reasoning_tier=1,
            tenant_id="TENANT-ULTRON-01",
            gemini_client=gem,
        )
        assert res["execution_mode"] == "degraded_fallback_after_provider_error"
        assert res["fallback_used"] is True
        assert len(res["failover_errors"]) >= 1
        assert "ReadTimeout" in res["failover_errors"][0]["error"]


@pytest.mark.parametrize("endpoint", ["/api/v1/neon/gemini/diagnostics", "/api/v1/neon/gemini/verify-suite"])
def test_gemini_diagnostics_and_suite_endpoints_require_auth(client: TestClient, endpoint: str) -> None:
    resp = client.get(endpoint) if endpoint.endswith("diagnostics") else client.post(endpoint)
    assert resp.status_code == 401
