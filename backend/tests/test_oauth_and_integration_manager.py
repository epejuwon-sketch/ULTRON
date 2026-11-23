"""Tests for unified IntegrationManager, OAuth 2.0 + PKCE, token refresh, revocation, and Antigravity adapter."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.db.session import get_session_factory
from app.integrations.antigravity import inspect_antigravity_environment
from app.services.integration_manager import (
    complete_oauth_callback,
    disconnect_connection,
    refresh_connection_token,
    start_oauth_flow,
    verify_provider_live,
)


def test_integration_manager_api_key_encrypt_list_and_disconnect(client: TestClient, auth_headers: dict) -> None:
    # OPERATOR cannot manage connections
    assert (
        client.post(
            "/api/v1/integrations/gemini/connect",
            headers=auth_headers["operator"],
            json={"credentials": {"api_key": "AIzaTestEncrypted1234567890"}},
        ).status_code
        == 403
    )

    # OWNER connects encrypted credentials -> never returned in response
    conn = client.post(
        "/api/v1/integrations/gemini/connect",
        headers=auth_headers["owner"],
        json={"credentials": {"api_key": "AIzaTestEncrypted1234567890"}, "account_label": "Primary AI Studio"},
    )
    assert conn.status_code == 200
    body = conn.json()
    assert body["status"] == "IMPLEMENTED_NOT_LIVE"
    assert "AIzaTestEncrypted1234567890" not in str(body)

    listed = client.get("/api/v1/integrations/connections", headers=auth_headers["owner"]).json()
    assert listed["total_managed_providers"] == 16
    assert "AIzaTestEncrypted1234567890" not in str(listed)

    # Disconnect wipes credentials
    disc = client.post("/api/v1/integrations/gemini/disconnect", headers=auth_headers["owner"])
    assert disc.status_code == 200
    assert disc.json()["status"] == "REQUIRES_CONFIGURATION"
    assert disc.json()["disconnected_at"] is not None


def test_oauth2_pkce_full_lifecycle_exchange_refresh_verify_and_revoke(client: TestClient, auth_headers: dict) -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        ULTRON_JWT_SECRET="test-jwt-secret-key-with-at-least-40-characters-0001",
        ULTRON_VAULT_MASTER_KEY="test-vault-master-key-with-at-least-40-characters-0001",
        GOOGLE_OAUTH_CLIENT_ID="test-client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="test-client-secret",
    )
    principal = Principal(
        user_id="usr_owner",
        username="owner_admin",
        role=Role.OWNER,
        tenant_id="TENANT-ULTRON-01",
        jti="jti_test",
    )

    def oauth_handler(req: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(req.url):
            body_text = req.content.decode("utf-8")
            if "grant_type=authorization_code" in body_text:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29_initial_token",
                        "refresh_token": "1//refresh_token_01",
                        "expires_in": 3600,
                        "scope": "https://www.googleapis.com/auth/drive.file",
                    },
                )
            if "grant_type=refresh_token" in body_text:
                return httpx.Response(200, json={"access_token": "ya29_refreshed_token", "expires_in": 3600})
        if "oauth2.googleapis.com/revoke" in str(req.url):
            return httpx.Response(200, json={})
        if "googleapis.com/drive/v3/about" in str(req.url):
            return httpx.Response(200, json={"user": {"displayName": "ULTRON Owner"}})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(oauth_handler))
    with get_session_factory()() as db:
        started = start_oauth_flow(db, principal=principal, provider="google_drive", settings=cfg)
        assert "code_challenge_method=S256" in started["authorization_url"]
        assert "drive.file" in started["authorization_url"]

        connected = complete_oauth_callback(
            db,
            principal=principal,
            provider="google_drive",
            code="auth-code-123",
            state=started["state"],
            settings=cfg,
            http_client=http,
        )
        assert connected["auth_type"] == "OAUTH2"
        assert connected["status"] == "IMPLEMENTED_NOT_LIVE"

        verified = verify_provider_live(db, principal=principal, provider="google_drive", settings=cfg, http_client=http)
        assert verified["live_verified"] is True
        assert verified["capability_state"] == "AVAILABLE"

        refreshed = refresh_connection_token(db, principal=principal, provider="google_drive", settings=cfg, http_client=http)
        assert refreshed["provider"] == "google_drive"

        revoked = disconnect_connection(db, principal=principal, provider="google_drive", settings=cfg, http_client=http)
        assert revoked["upstream_revoked"] is True
        assert revoked["status"] == "REQUIRES_CONFIGURATION"


def test_antigravity_adapter_reports_honestly(client: TestClient, auth_headers: dict) -> None:
    report = inspect_antigravity_environment(run_live_auth_checks=False)
    assert "unsupported_interfaces" in report
    assert report["unsupported_interfaces"]["antigravity_rest_control_plane"]["status"] == "UNAVAILABLE"

    api_resp = client.get("/api/v1/integrations/antigravity", headers=auth_headers["owner"])
    assert api_resp.status_code == 200
    assert "connected_plugin_adapters" in api_resp.json()
