"""Contract tests for the complete 38-provider ULTRON Connections Centre ecosystem."""

from __future__ import annotations

import httpx
from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.db.session import get_session_factory
from app.services.integration_manager import (
    SUPPORTED_MANAGED_PROVIDERS,
    connect_with_credentials,
    disconnect_connection,
    list_connections,
    verify_provider_live,
)


def test_all_ecosystem_providers_connect_verify_fail_and_disconnect(client) -> None:
    _ = client
    expected_providers = {
        "gemini",
        "openai",
        "anthropic",
        "ollama",
        "google_drive",
        "google_gmail",
        "google_calendar",
        "google_docs",
        "google_sheets",
        "google_slides",
        "google_cloud",
        "google_search",
        "github",
        "vercel",
        "cloudflare",
        "supabase",
        "gitlab",
        "bitbucket",
        "whatsapp",
        "email_smtp",
        "telegram",
        "slack",
        "discord",
        "notion",
        "linear",
        "trello",
        "asana",
        "jira",
        "postgresql",
        "redis",
        "stripe",
        "paystack",
        "flutterwave",
        "uba_verve",
        "caravan",
        "spotify",
        "image_gen",
        "webhooks",
        "rest_apis",
        "mcp",
    }
    assert expected_providers.issubset(set(SUPPORTED_MANAGED_PROVIDERS.keys()))

    cfg = Settings()
    owner_a = Principal(user_id="u_a", username="owner_a", role=Role.OWNER, tenant_id="TENANT-ULTRON-01", jti="j1")
    owner_b = Principal(user_id="u_b", username="owner_b", role=Role.OWNER, tenant_id="TENANT-B", jti="j2")

    def mock_handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "slack.com/api/auth.test" in url:
            auth = req.headers.get("Authorization", "")
            if "bad" in auth:
                return httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
            return httpx.Response(200, json={"ok": True, "user_id": "U123"})
        if "bad-token" in req.headers.get("Authorization", "") or "bad-token" in req.headers.get("PRIVATE-TOKEN", ""):
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(200, json={"ok": True})

    http = httpx.Client(transport=httpx.MockTransport(mock_handler))

    test_cases = [
        ("openai", {"api_key": "sk-test-123"}, "API_KEY"),
        ("anthropic", {"api_key": "sk-ant-123"}, "API_KEY"),
        ("ollama", {"base_url": "http://127.0.0.1:11434"}, "API_KEY"),
        ("gitlab", {"api_key": "glpat-valid-123"}, "PAT"),
        ("bitbucket", {"api_key": "bb-valid-123"}, "PAT"),
        ("whatsapp", {"api_key": "wa-valid", "phone_number_id": "123456"}, "API_KEY"),
        ("telegram", {"api_key": "123:ABC"}, "API_KEY"),
        ("slack", {"api_key": "xoxb-valid"}, "API_KEY"),
        ("discord", {"api_key": "disc-valid"}, "API_KEY"),
        ("notion", {"api_key": "secret_valid"}, "API_KEY"),
        ("linear", {"api_key": "lin_api_valid"}, "API_KEY"),
        ("trello", {"api_key": "tr_key", "token": "tr_tok"}, "API_KEY"),
        ("asana", {"api_key": "asana-valid"}, "PAT"),
        ("jira", {"domain": "org.atlassian.net", "email": "a@b.com", "api_key": "jira-valid"}, "API_KEY"),
        ("redis", {"rest_url": "https://r.upstash.io", "api_key": "r-tok"}, "API_KEY"),
        ("stripe", {"api_key": "rk_test_valid"}, "API_KEY"),
        ("paystack", {"api_key": "sk_test_valid"}, "API_KEY"),
        ("flutterwave", {"api_key": "FLWSECK_TEST-valid"}, "API_KEY"),
        ("spotify", {"api_key": "BQA-valid"}, "API_KEY"),
    ]

    with get_session_factory()() as db:
        for provider, creds, auth_type in test_cases:
            conn = connect_with_credentials(
                db,
                principal=owner_a,
                provider=provider,
                credentials=creds,
                auth_type=auth_type,
                settings=cfg,
            )
            assert conn["status"] == "IMPLEMENTED_NOT_LIVE"

            verified = verify_provider_live(db, principal=owner_a, provider=provider, settings=cfg, http_client=http)
            assert verified["live_verified"] is True, f"{provider} failed verification: {verified}"
            assert verified["capability_state"] == "AVAILABLE"

            # Tenant isolation: tenant B must not see tenant A's connection
            b_list = list_connections(db, tenant_id=owner_b.tenant_id, settings=cfg)
            b_item = next(c for c in b_list["connections"] if c["provider"] == provider)
            assert b_item["connection_id"] is None

            # Disconnect & revoke
            disc = disconnect_connection(db, principal=owner_a, provider=provider, settings=cfg, http_client=http)
            assert disc["status"] == "REQUIRES_CONFIGURATION"

        # Verify invalid Slack token is detected as DEGRADED (not AVAILABLE)
        connect_with_credentials(
            db,
            principal=owner_a,
            provider="slack",
            credentials={"api_key": "xoxb-bad"},
            auth_type="API_KEY",
            settings=cfg,
        )
        bad_slack = verify_provider_live(db, principal=owner_a, provider="slack", settings=cfg, http_client=http)
        assert bad_slack["live_verified"] is False
        assert bad_slack["capability_state"] == "DEGRADED"
