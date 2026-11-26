"""Tests for health probes, security headers, and honest cloud integration verifiers."""

from __future__ import annotations

import hashlib
import hmac

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.integrations.base import HonestCapabilityState
from app.integrations.cloudflare import CloudflareClient
from app.integrations.gemini import GeminiClient
from app.integrations.supabase import SupabaseClient
from app.integrations.vercel import VercelClient


def test_health_endpoints_and_security_headers(client: TestClient) -> None:
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert live.headers["X-Frame-Options"] == "DENY"
    assert live.headers["X-Request-ID"].startswith("req_")

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["database"]["healthy"] is True
    assert body["database"]["backend"] == "sqlite"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["integrations"]["configured_count"] == 0


def test_honest_unconfigured_integrations_never_fabricate_live_pass(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.post("/api/v1/integrations/verify", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured_count"] == 0
    assert data["live_verified_count"] == 0
    for name in ("supabase", "gemini", "vercel", "cloudflare"):
        provider = data["providers"][name]
        assert provider["configured"] is False
        assert provider["live_verified"] is False
        assert provider["capability_state"] == HonestCapabilityState.DEFINED_NOT_INSTALLED.value
        assert len(provider["missing_env_vars"]) >= 1


def test_supabase_client_live_verification_and_error_classification() -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="demo-service-role-key",
    )

    ok_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"swagger": "2.0"}))
    ok_status = SupabaseClient(cfg, http_client=httpx.Client(transport=ok_transport)).verify_live()
    assert ok_status.live_verified is True
    assert ok_status.capability_state == HonestCapabilityState.AVAILABLE

    auth_fail_transport = httpx.MockTransport(lambda req: httpx.Response(401, json={"message": "bad key"}))
    fail_status = SupabaseClient(cfg, http_client=httpx.Client(transport=auth_fail_transport)).verify_live()
    assert fail_status.live_verified is False
    assert "PROVIDER_AUTH_ERROR" in fail_status.detail


def test_gemini_client_verify_generate_and_embed() -> None:
    cfg = Settings(ULTRON_ENV="test", GEMINI_API_KEY="AIzaDemoTestKey1234567890")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-goog-api-key") == "AIzaDemoTestKey1234567890"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [{"name": "models/gemini-2.0-flash"}]})
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": "Verified Gemini output"}]}}],
                    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 6, "totalTokenCount": 18},
                },
            )
        if request.url.path.endswith(":embedContent"):
            return httpx.Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    gemini = GeminiClient(cfg, http_client=http)

    status = gemini.verify_live()
    assert status.live_verified is True
    assert status.capability_state == HonestCapabilityState.AVAILABLE

    gen = gemini.generate_content(prompt="Say hello")
    assert gen["text"] == "Verified Gemini output"
    assert gen["usage"]["total_tokens"] == 18

    vec = gemini.embed_text("ULTRON memory")
    assert vec == [0.1, 0.2, 0.3]


def test_vercel_and_cloudflare_clients() -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        VERCEL_TOKEN="vrc_test_token",
        VERCEL_WEBHOOK_SECRET="whsec_test",
        CLOUDFLARE_API_TOKEN="cf_test_token",
        CLOUDFLARE_ACCOUNT_ID="acc_123",
        CLOUDFLARE_KV_NAMESPACE_ID="kv_456",
    )

    v_client = VercelClient(
        cfg,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"user": {}}))),
    )
    assert v_client.verify_live().live_verified is True
    payload = b'{"event":"deployment.created"}'
    sig = hmac.new(b"whsec_test", payload, hashlib.sha1).hexdigest()
    assert v_client.verify_webhook_signature(payload, sig) is True
    assert v_client.verify_webhook_signature(payload, "invalid-sig") is False

    cf_client = CloudflareClient(
        cfg,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"success": True, "result": {}}))
        ),
    )
    assert cf_client.verify_live().live_verified is True
    kv_res = cf_client.kv_put("health:key", "ok", ttl_seconds=60)
    assert kv_res["success"] is True
