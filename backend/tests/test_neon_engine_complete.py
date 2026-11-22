"""Comprehensive NEON intelligence engine tests: models, failover, structured JSON, tool calling, SSE streaming, conversations, and cost tracking."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.neon_providers import GeminiLLMProvider, OpenAILLMProvider, execute_with_failover


def test_neon_models_tiers_structured_tool_calling_and_usage(client: TestClient, auth_headers: dict) -> None:
    models = client.get("/api/v1/neon/models", headers=auth_headers["operator"])
    assert models.status_code == 200
    assert models.json()["total"] == 6
    assert all(m["configured"] is False for m in models.json()["models"])

    tiers = client.get("/api/v1/neon/tiers", headers=auth_headers["operator"])
    assert tiers.status_code == 200
    assert len(tiers.json()["tiers"]) == 5

    # Structured JSON output + tool call execution
    comp = client.post(
        "/api/v1/neon/complete",
        headers=auth_headers["operator"],
        json={
            "prompt": "Analyze diagnostics and return JSON summary",
            "response_format": "json",
            "tool_name": "system_diagnostics",
            "tool_arguments": {},
        },
    )
    assert comp.status_code == 200
    body = comp.json()
    assert body["execution_mode"] == "local_deterministic_fallback"
    assert body["structured_output"]["live_model_executed"] is False
    assert body["tool_execution"]["status"] == "COMPLETED"
    assert body["tool_execution"]["output"]["registered_agents"] == 60

    # Usage tracking logged the call
    usage = client.get("/api/v1/neon/usage", headers=auth_headers["operator"])
    assert usage.status_code == 200
    assert usage.json()["total_calls"] >= 1


def test_neon_sse_streaming_and_conversations(client: TestClient, auth_headers: dict) -> None:
    stream = client.post(
        "/api/v1/neon/stream",
        headers=auth_headers["operator"],
        json={"prompt": "Stream status overview for ULTRON OS 2026"},
    )
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    text = stream.text
    assert "event: metadata" in text
    assert "event: delta" in text
    assert "event: done" in text

    conv = client.post(
        "/api/v1/neon/conversations",
        headers=auth_headers["operator"],
        json={"title": "Architecture Session", "agent_id": "AGT-05"},
    )
    assert conv.status_code == 201
    cid = conv.json()["conversation_id"]

    turn1 = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        headers=auth_headers["operator"],
        json={"content": "Review our Supabase Postgres pooling config"},
    )
    assert turn1.status_code == 200
    assert turn1.json()["reply"]["agent_id"] == "AGT-05"

    fetched = client.get(f"/api/v1/neon/conversations/{cid}", headers=auth_headers["operator"])
    assert fetched.status_code == 200
    assert len(fetched.json()["messages"]) == 2


def test_neon_multi_provider_failover_chain() -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        GEMINI_API_KEY="AIzaTestPrimary1234567890",
        OPENAI_API_KEY="sk-test-fallback-1234567890",
    )

    failing_gemini = GeminiLLMProvider(
        cfg,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503, json={"error": "down"}))),
    )
    ok_openai = OpenAILLMProvider(
        cfg,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "Failover succeeded via OpenAI"}}],
                        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                    },
                )
            )
        ),
    )

    result, errors = execute_with_failover(
        settings=cfg,
        prompt="Test failover",
        system_instruction="Be concise",
        primary_model="gemini-2.0-flash",
        max_retries_per_provider=0,
        providers=[failing_gemini, ok_openai],
    )
    assert result is not None
    assert result["provider"] == "openai"
    assert result["text"] == "Failover succeeded via OpenAI"
    assert len(errors) == 1
    assert errors[0]["provider"] == "gemini"
