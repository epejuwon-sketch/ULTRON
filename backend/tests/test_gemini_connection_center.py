"""Tests for ULTRON Native Gemini Connection Center & Live Server-Side Verification."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import ProviderVerificationRecord, Tenant, User
from app.db.session import get_session_factory
from app.services.gemini_connection_service import (
    STANDARD_TEST_PROMPT,
    get_gemini_connection_card_data,
    get_gemini_connection_diagnostics,
    get_gemini_verification_history,
    run_gemini_connection_test,
)


def _mock_gemini_inference_transport(
    expected_model: str = "gemini-3.8-flash",
    text_reply: str = "ULTRON GEMINI CONNECTION VERIFIED.",
    status_code: int = 200,
    error_payload: dict | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        # Check API key header was provided
        if not request.headers.get("x-goog-api-key"):
            return httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid. Please pass a valid API key.", "status": "UNAUTHENTICATED"}})

        if status_code != 200:
            payload = error_payload or {"error": {"code": status_code, "message": "Simulated Google API error", "status": "INTERNAL"}}
            return httpx.Response(status_code, json=payload)

        # GET /models
        if "/models" in url_str and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": f"models/{expected_model}", "displayName": "Gemini Model", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-4-argon", "displayName": "Gemini 4 Argon", "supportedGenerationMethods": ["generateContent"]},
                    ]
                },
            )

        # POST /models/{model}:generateContent
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": text_reply}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 14,
                    "candidatesTokenCount": 8,
                    "totalTokenCount": 22,
                },
                "modelVersion": expected_model,
            },
        )

    return httpx.MockTransport(handler)


def test_missing_gemini_credential_honest_reporting(client: TestClient, auth_headers: dict) -> None:
    """When GEMINI_API_KEY is missing, card reports NOT CONFIGURED and test fails honestly."""
    # Ensure no credentials
    resp = client.get("/api/v1/integrations/gemini/card", headers=auth_headers["owner"])
    assert resp.status_code == 200
    card = resp.json()
    assert card["provider"] == "Google Gemini"
    assert card["connection_status"] in ("NOT CONFIGURED", "CONFIGURED")
    assert card["credential_status"]["configured"] is False
    assert "GEMINI_API_KEY" in card["credential_status"]["missing_env_vars"]
    assert card["models"]["standard"] == "gemini-3.8-flash"
    assert card["models"]["reasoning"] == "gemini-4-argon"

    # Test standard inference without credential
    test_res = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])
    assert test_res.status_code == 200
    data = test_res.json()
    assert data["result"] == "FAILED"
    assert data["error_code"] == "CREDENTIAL_NOT_CONFIGURED"
    assert "not configured" in data["error_message"].lower()

    # History contains the persisted failure
    hist_res = client.get("/api/v1/integrations/gemini/history", headers=auth_headers["owner"])
    assert hist_res.status_code == 200
    hist = hist_res.json()["history"]
    assert len(hist) >= 1
    assert hist[0]["result"] == "FAILED"
    assert hist[0]["error_code"] == "CREDENTIAL_NOT_CONFIGURED"


def test_successful_standard_inference_flow(monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict) -> None:
    """With valid credential, standard inference returns VERIFIED, latency, and token counts."""
    from app.core.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyForTesting1234567890")
    get_settings.cache_clear()
    transport = _mock_gemini_inference_transport(expected_model="gemini-3.8-flash")

    from app.services import gemini_connection_service

    orig_test = gemini_connection_service.run_gemini_connection_test

    def patched_test(db, *, principal, settings, test_type="STANDARD_INFERENCE", http_client=None):
        mock_http = httpx.Client(transport=transport)
        return orig_test(db, principal=principal, settings=settings, test_type=test_type, http_client=mock_http)

    monkeypatch.setattr(gemini_connection_service, "run_gemini_connection_test", patched_test)

    resp = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "VERIFIED"
    assert data["model"] == "gemini-3.8-flash"
    assert data["test_type"] == "STANDARD_INFERENCE"
    assert data["response_matched"] is True
    assert "ULTRON GEMINI CONNECTION VERIFIED" in data["response_text"]
    assert data["tokens"]["total_tokens"] == 22
    assert data["latency_ms"] >= 0
    assert data["provenance"]["verification_status"] == "LIVE_VERIFIED"

    # Card now reports CONNECTED with valid latency
    card_res = client.get("/api/v1/integrations/gemini/card", headers=auth_headers["owner"])
    assert card_res.status_code == 200
    card = card_res.json()
    assert card["connection_status"] == "CONNECTED"
    assert card["last_successful_verification"] is not None
    assert card["last_successful_verification"]["model"] == "gemini-3.8-flash"


def test_tier5_reasoning_inference_explicit_flow(monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict) -> None:
    """Tier 5 testing explicitly invokes gemini-4-argon."""
    from app.core.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyForTesting1234567890")
    get_settings.cache_clear()
    transport = _mock_gemini_inference_transport(expected_model="gemini-4-argon", text_reply="ULTRON GEMINI CONNECTION VERIFIED.")

    from app.services import gemini_connection_service

    orig_test = gemini_connection_service.run_gemini_connection_test

    def patched_test(db, *, principal, settings, test_type="TIER5_REASONING", http_client=None):
        mock_http = httpx.Client(transport=transport)
        return orig_test(db, principal=principal, settings=settings, test_type=test_type, http_client=mock_http)

    monkeypatch.setattr(gemini_connection_service, "run_gemini_connection_test", patched_test)

    resp = client.post("/api/v1/integrations/gemini/test-tier5", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "VERIFIED"
    assert data["model"] == "gemini-4-argon"
    assert data["test_type"] == "TIER5_REASONING"


def test_invalid_revoked_credential_reporting(monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict) -> None:
    """Invalid credentials report AUTHENTICATION_FAILED safely without exposing secrets."""
    from app.core.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyInvalidKeyRevoked12345")
    get_settings.cache_clear()
    transport = _mock_gemini_inference_transport(
        status_code=401,
        error_payload={"error": {"code": 401, "message": "API key not valid. Please pass a valid API key.", "status": "UNAUTHENTICATED"}},
    )

    from app.services import gemini_connection_service

    orig_test = gemini_connection_service.run_gemini_connection_test

    def patched_test(db, *, principal, settings, test_type="STANDARD_INFERENCE", http_client=None):
        mock_http = httpx.Client(transport=transport)
        return orig_test(db, principal=principal, settings=settings, test_type=test_type, http_client=mock_http)

    monkeypatch.setattr(gemini_connection_service, "run_gemini_connection_test", patched_test)

    resp = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "FAILED"
    assert data["error_code"] == "AUTHENTICATION_FAILED"
    # Ensure no secret key appears in error message
    assert "AIzaSy" not in (data["error_message"] or "")


def test_timeout_and_error_sanitization(monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict) -> None:
    """Provider timeout reports TIMEOUT safely."""
    from app.core.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyValidKey12345")
    get_settings.cache_clear()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out after 20.0s")

    transport = httpx.MockTransport(timeout_handler)

    from app.services import gemini_connection_service

    orig_test = gemini_connection_service.run_gemini_connection_test

    def patched_test(db, *, principal, settings, test_type="STANDARD_INFERENCE", http_client=None):
        mock_http = httpx.Client(transport=transport)
        return orig_test(db, principal=principal, settings=settings, test_type=test_type, http_client=mock_http)

    monkeypatch.setattr(gemini_connection_service, "run_gemini_connection_test", patched_test)

    resp = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "FAILED"
    assert data["error_code"] == "TIMEOUT"


def test_unauthorized_user_access_blocked(client: TestClient, auth_headers: dict) -> None:
    """Users without 'integrations:verify' permission receive HTTP 403."""
    # VIEWER role lacks integrations:verify
    resp = client.get("/api/v1/integrations/gemini/card", headers=auth_headers["viewer"])
    assert resp.status_code == 403

    resp2 = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["viewer"])
    assert resp2.status_code == 403


def test_tenant_isolation_in_verification_history(client: TestClient, auth_headers: dict) -> None:
    """History records are tenant-isolated; tenant B cannot view tenant A records."""
    # Insert a record directly for another tenant
    from app.core.config import get_settings

    settings = get_settings()
    with get_session_factory(settings)() as db:
        other_tenant = db.get(Tenant, "other-tenant-uuid")
        if not other_tenant:
            db.add(Tenant(tenant_id="other-tenant-uuid", name="Other Org"))
            db.flush()
        db.add(
            ProviderVerificationRecord(
                verification_id="pvr_secret_tenant_b",
                tenant_id="other-tenant-uuid",
                provider="gemini",
                model="gemini-3.8-flash",
                test_type="STANDARD_INFERENCE",
                result="VERIFIED",
                latency_ms=120,
                trace_id="trc_other_org",
                environment="test",
            )
        )
        db.commit()

    resp = client.get("/api/v1/integrations/gemini/history", headers=auth_headers["owner"])
    assert resp.status_code == 200
    hist = resp.json()["history"]
    # Confirm tenant A does not see tenant B's record
    assert not any(r["verification_id"] == "pvr_secret_tenant_b" for r in hist)


def test_technical_diagnostics_endpoint(client: TestClient, auth_headers: dict) -> None:
    """Diagnostics endpoint returns full 5-tier model matrix, deprecation notices, and provider isolation."""
    resp = client.get("/api/v1/integrations/gemini/diagnostics", headers=auth_headers["owner"])
    assert resp.status_code == 200
    diag = resp.json()
    assert diag["provider"] == "Google Gemini"
    assert len(diag["tier_hierarchy"]) == 5
    assert diag["tier_hierarchy"][0]["primary_model"] == "gemini-3.5-flash-lite"
    assert diag["tier_hierarchy"][1]["primary_model"] == "gemini-3.8-flash"
    assert diag["tier_hierarchy"][4]["primary_model"] == "gemini-4-argon"
    assert diag["isolation_audit"]["isolation_verified"] is True
    assert diag["isolation_audit"]["carbon_present"] is False
    assert "NEON Intelligence Layer" in diag["isolation_audit"]["note"]


def test_rate_limiting_enforcement(client: TestClient, auth_headers: dict) -> None:
    """Rapid repeated verification requests are rate-limited with HTTP 429."""
    from app.services import gemini_connection_service

    # Clear timestamps first
    gemini_connection_service._TENANT_TEST_TIMESTAMPS.clear()

    # Issue requests up to limit
    for _ in range(gemini_connection_service._MAX_TESTS_PER_MINUTE):
        client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])

    # Next request triggers RateLimitError (HTTP 429)
    resp = client.post("/api/v1/integrations/gemini/test-standard", headers=auth_headers["owner"])
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "rate limit exceeded" in body["error"]["message"].lower()

    # Clean up
    gemini_connection_service._TENANT_TEST_TIMESTAMPS.clear()


def test_gemini_intra_provider_fallback_policy(client: TestClient, auth_headers: dict) -> None:
    """Verify intra-Gemini fallback chain: Tier 2 gemini-3.8-flash falls back to gemini-3.5-flash-lite."""
    from app.core.config import get_settings
    from app.services.neon_providers import build_gemini_tier_fallback_chain

    settings = get_settings()
    chain = build_gemini_tier_fallback_chain("gemini-3.8-flash", settings, reasoning_tier=2)
    assert chain[0] == "gemini-3.8-flash"
    assert "gemini-3.5-flash-lite" in chain
    # Ensure no unauthorized providers or Carbon in chain
    assert not any("openai" in m or "anthropic" in m or "carbon" in m for m in chain)
