"""Tests for unified IntegrationManager, OAuth 2.0 + PKCE, token refresh, revocation, and Antigravity adapter."""

from __future__ import annotations

import httpx
from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.db.session import get_session_factory
from app.integrations.antigravity import inspect_antigravity_environment
from app.services.integration_manager import (
    complete_oauth_callback,
    disconnect_connection,
    list_connections,
    refresh_connection_token,
    start_oauth_flow,
    verify_provider_live,
)
from fastapi.testclient import TestClient


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
        if "googleapis.com/oauth2/v2/userinfo" in str(req.url):
            return httpx.Response(200, json={"email": "owner@ultron.ai"})
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
        assert connected["live_verified"] is True
        assert connected["capability_state"] == "AVAILABLE"

        listed = list_connections(db, tenant_id=principal.tenant_id, settings=cfg)
        gd_entry = next(c for c in listed["connections"] if c["provider"] == "google_drive")
        assert gd_entry["account_label"] == "owner@ultron.ai"
        assert gd_entry["oauth_client_configured"] is True

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


def test_oauth_redirect_uri_consistency_user_isolation_and_replay(client: TestClient) -> None:
    import pytest
    from app.core.exceptions import ConflictError, ValidationError

    cfg = Settings(
        google_oauth_client_id="google-client-id-test",
        google_oauth_client_secret="google-client-secret-test",
    )
    owner = Principal(
        user_id="usr_owner_1",
        username="owner",
        role=Role.OWNER,
        tenant_id="TENANT-ULTRON-01",
        jti="jti_1",
    )
    other_user_same_tenant = Principal(
        user_id="usr_admin_2",
        username="admin2",
        role=Role.ADMIN,
        tenant_id="TENANT-ULTRON-01",
        jti="jti_2",
    )

    def oauth_handler(req: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(req.url):
            return httpx.Response(200, json={"access_token": "ya29_test", "refresh_token": "1//rt", "expires_in": 3600})
        if "googleapis.com/oauth2/v2/userinfo" in str(req.url):
            return httpx.Response(200, json={"email": "owner@ultron.ai"})
        if "googleapis.com/drive/v3/about" in str(req.url):
            return httpx.Response(200, json={"user": {"displayName": "ULTRON Owner"}})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(oauth_handler))
    with get_session_factory()() as db:
        # 1. Reject non-canonical redirect_uri
        with pytest.raises(ValidationError):
            start_oauth_flow(
                db,
                principal=owner,
                provider="google_drive",
                redirect_uri="https://evil.example.com/steal",
                settings=cfg,
            )

        # 2. Start with canonical /oauth/callback
        canonical_uri = "http://localhost:5173/oauth/callback"
        started = start_oauth_flow(
            db,
            principal=owner,
            provider="google_drive",
            redirect_uri=canonical_uri,
            settings=cfg,
        )

        # 3. Reject wrong-user callback in same tenant
        with pytest.raises(ConflictError):
            complete_oauth_callback(
                db,
                principal=other_user_same_tenant,
                provider="google_drive",
                code="auth-code-xyz",
                state=started["state"],
                redirect_uri=canonical_uri,
                settings=cfg,
                http_client=http,
            )

        # 4. Reject mismatched redirect_uri
        with pytest.raises(ConflictError):
            complete_oauth_callback(
                db,
                principal=owner,
                provider="google_drive",
                code="auth-code-xyz",
                state=started["state"],
                redirect_uri="https://other.example.com/oauth/callback",
                settings=cfg,
                http_client=http,
            )

        # 5. Exact user + exact redirect_uri succeeds
        ok = complete_oauth_callback(
            db,
            principal=owner,
            provider="google_drive",
            code="auth-code-xyz",
            state=started["state"],
            redirect_uri=canonical_uri,
            settings=cfg,
            http_client=http,
        )
        assert ok["live_verified"] is True

        # 5b. Unified /api/v1/integrations/status reflects the same connected VAULT OAuth state
        # without requiring GOOGLE_DRIVE_ACCESS_TOKEN
        from app.routers.health import integrations_status

        unified_status = integrations_status(principal=owner, db=db, settings=cfg)
        gd_cap = unified_status["capabilities"]["google_drive"]
        assert gd_cap["configured"] is True
        assert gd_cap["live_verified"] is True
        assert gd_cap["missing_env_vars"] == []
        assert "GOOGLE_DRIVE_ACCESS_TOKEN" not in gd_cap["detail"]

        # 6. Replay with same state is rejected
        with pytest.raises(ConflictError):
            complete_oauth_callback(
                db,
                principal=owner,
                provider="google_drive",
                code="auth-code-xyz",
                state=started["state"],
                redirect_uri=canonical_uri,
                settings=cfg,
                http_client=http,
            )


def test_admin_vault_oauth_app_configuration_and_lifecycle(client: TestClient, auth_headers: dict) -> None:
    # 1. Without admin config, google_drive is SUPPORTED and OAuth start fails cleanly
    conns_before = client.get("/api/v1/integrations/connections", headers=auth_headers["owner"]).json()
    gd_before = next(c for c in conns_before["connections"] if c["provider"] == "google_drive")
    assert gd_before["oauth_client_configured"] is False
    assert gd_before["lifecycle_stage"] == "SUPPORTED"

    start_fail = client.post(
        "/api/v1/integrations/oauth/google_drive/start",
        headers=auth_headers["owner"],
        json={"redirect_uri": "http://localhost:5173/oauth/callback"},
    )
    assert start_fail.status_code >= 400
    assert "Administrator configuration is required" in start_fail.text

    # 2. Non-admin VIEWER cannot configure OAuth app credentials
    viewer_try = client.post(
        "/api/v1/integrations/oauth/admin/google/configure",
        headers=auth_headers["viewer"],
        json={
            "client_id": "12345678-apps.googleusercontent.com",
            "client_secret": "GOCSPX-secret-value-1234",
            "redirect_uri": "http://localhost:5173/oauth/callback",
        },
    )
    assert viewer_try.status_code == 403

    # 3. OWNER configures Google OAuth app credentials in VAULT (secret never echoed back)
    secret_val = "GOCSPX-super-secret-value-9999"
    admin_ok = client.post(
        "/api/v1/integrations/oauth/admin/google/configure",
        headers=auth_headers["owner"],
        json={
            "client_id": "12345678-apps.googleusercontent.com",
            "client_secret": secret_val,
            "redirect_uri": "http://localhost:5173/oauth/callback",
        },
    )
    assert admin_ok.status_code == 200, admin_ok.text
    assert admin_ok.json()["configured"] is True
    assert admin_ok.json()["source"] == "vault"
    assert secret_val not in admin_ok.text

    # 4. Status and Connections now advance google_drive to Stage 2 (CONFIGURED)
    app_stat = client.get("/api/v1/integrations/oauth/admin/google/status", headers=auth_headers["owner"])
    assert app_stat.status_code == 200
    assert app_stat.json()["configured"] is True
    assert secret_val not in app_stat.text

    conns_after = client.get("/api/v1/integrations/connections", headers=auth_headers["owner"]).json()
    gd_after = next(c for c in conns_after["connections"] if c["provider"] == "google_drive")
    assert gd_after["oauth_client_configured"] is True
    assert gd_after["lifecycle_stage"] == "CONFIGURED"

    # 5. Now OAuth start succeeds using VAULT-stored OAuth app credentials
    start_ok = client.post(
        "/api/v1/integrations/oauth/google_drive/start",
        headers=auth_headers["owner"],
        json={"redirect_uri": "http://localhost:5173/oauth/callback"},
    )
    assert start_ok.status_code == 200, start_ok.text
    assert "accounts.google.com/o/oauth2/v2/auth" in start_ok.json()["authorization_url"]
    assert "drive.file" in start_ok.json()["authorization_url"]


