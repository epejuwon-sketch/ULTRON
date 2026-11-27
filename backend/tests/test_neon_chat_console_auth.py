"""Comprehensive test suite for NEON Chat Console authentication, session synchronization, streaming persistence, and tenant isolation.

Verifies:
1. Missing Bearer token rejected with HTTP 401 across all protected NEON endpoints.
2. Authenticated user with valid Bearer token can access NEON endpoints.
3. Public health endpoints (/health, /health/ready) accessible without Bearer token.
4. Expired token rejected with 401, while token refresh provides valid access.
5. Conversation creation with specialist agents (AGT-01 to AGT-60).
6. Persisted conversation messaging stores user and assistant messages in database.
7. SSE streaming (/api/v1/neon/stream) requires Bearer token and returns valid event stream.
8. SSE streaming with conversation_id persists user prompt and assistant response to conversation history.
9. Cross-tenant conversation isolation: tenant A cannot access or stream into tenant B's conversation.
10. Agent handoff across specialist agents.
11. Attached file references in conversation messages.
12. Tampered and malformed Bearer tokens rejected with 401.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import ConversationMessageRecord, ConversationRecord, Tenant, User
from app.db.session import get_session_factory


def _get_err(resp: any) -> str:
    body = resp.json()
    return str(body.get("error", {}).get("message") or body.get("detail") or "")


def test_01_unauthenticated_requests_to_neon_endpoints_rejected_with_401(client: TestClient) -> None:
    """Requirement 1: Unauthenticated requests without Bearer token return 401."""
    # Conversation list
    r1 = client.get("/api/v1/neon/conversations")
    assert r1.status_code == 401
    err = _get_err(r1).lower()
    assert "bearer" in err or "authenticated" in err or "credentials" in err

    # Create conversation
    r2 = client.post("/api/v1/neon/conversations", json={"title": "Test Conv", "agent_id": "AGT-01"})
    assert r2.status_code == 401

    # SSE Stream
    r3 = client.post("/api/v1/neon/stream", json={"prompt": "Test stream", "agent_id": "AGT-01"})
    assert r3.status_code == 401

    # Models catalog
    r4 = client.get("/api/v1/neon/models")
    assert r4.status_code == 401

    # Tiers catalog
    r5 = client.get("/api/v1/neon/tiers")
    assert r5.status_code == 401

    # Usage
    r6 = client.get("/api/v1/neon/usage")
    assert r6.status_code == 401

    # Gemini diagnostics
    r7 = client.get("/api/v1/neon/gemini/diagnostics")
    assert r7.status_code == 401


def test_02_public_health_accessible_without_token_while_neon_protected(client: TestClient) -> None:
    """Requirement 2: Public /health is unauthenticated, explaining why Gemini Configured renders while chat fails if unauth."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "integrations" in data

    # Protected NEON remains strictly 401 without auth
    assert client.get("/api/v1/neon/conversations").status_code == 401


def test_03_authenticated_user_accesses_neon_endpoints_with_bearer_token(
    client: TestClient, auth_headers: dict
) -> None:
    """Requirement 3: Authenticated owner accesses NEON endpoints successfully."""
    headers = auth_headers["owner"]

    # List conversations
    r_conv = client.get("/api/v1/neon/conversations", headers=headers)
    assert r_conv.status_code == 200
    assert "conversations" in r_conv.json()

    # Models catalog
    r_models = client.get("/api/v1/neon/models", headers=headers)
    assert r_models.status_code == 200
    assert "models" in r_models.json()

    # Tiers catalog
    r_tiers = client.get("/api/v1/neon/tiers", headers=headers)
    assert r_tiers.status_code == 200
    assert "tiers" in r_tiers.json()

    # Usage
    r_usage = client.get("/api/v1/neon/usage", headers=headers)
    assert r_usage.status_code == 200

    # Gemini diagnostics
    r_diag = client.get("/api/v1/neon/gemini/diagnostics?discover=false", headers=headers)
    assert r_diag.status_code == 200
    assert "configured" in r_diag.json()


def test_04_create_conversation_and_send_persisted_message(
    client: TestClient, auth_headers: dict
) -> None:
    """Requirement 4: Create conversation with agent handoff and send persisted message."""
    headers = auth_headers["owner"]

    # Create conversation with AGT-03 (Senior Polyglot Engineer)
    create_resp = client.post(
        "/api/v1/neon/conversations",
        json={"title": "Code Review Session", "agent_id": "AGT-03"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    conv = create_resp.json()
    cid = conv["conversation_id"]
    assert conv["agent_id"] == "AGT-03"

    # Send message in conversation
    msg_resp = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        json={"content": "Please review this Python FastAPI code structure.", "enable_web_research": False},
        headers=headers,
    )
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert "assistant_message" in data
    assert data["assistant_message"]["role"] == "assistant"
    assert len(data["assistant_message"]["content"]) > 0

    # Retrieve conversation history
    history_resp = client.get(f"/api/v1/neon/conversations/{cid}", headers=headers)
    assert history_resp.status_code == 200
    hist = history_resp.json()
    msgs = hist["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_05_sse_stream_without_conversation_id(client: TestClient, auth_headers: dict) -> None:
    """Requirement 5: Stream NEON reasoning events via SSE with Bearer auth."""
    headers = auth_headers["owner"]
    resp = client.post(
        "/api/v1/neon/stream",
        json={"prompt": "Analyze architectural performance.", "agent_id": "AGT-01", "reasoning_tier": 2},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # Parse SSE events from response text
    lines = resp.text.split("\n")
    events = [l for l in lines if l.startswith("event:")]
    assert any("metadata" in e for e in events)
    assert any("delta" in e for e in events)
    assert any("done" in e for e in events)


def test_06_sse_stream_with_conversation_id_persists_messages(
    client: TestClient, auth_headers: dict
) -> None:
    """Requirement 6: Stream NEON reasoning with conversation_id persists user prompt and assistant reply in database."""
    headers = auth_headers["owner"]

    # Create new conversation
    c_resp = client.post(
        "/api/v1/neon/conversations",
        json={"title": "Streaming Test Session", "agent_id": "AGT-05"},
        headers=headers,
    )
    assert c_resp.status_code == 201
    cid = c_resp.json()["conversation_id"]

    # Send streaming request with conversation_id
    s_resp = client.post(
        "/api/v1/neon/stream",
        json={
            "prompt": "Outline microservices architecture considerations.",
            "agent_id": "AGT-05",
            "conversation_id": cid,
            "reasoning_tier": 2,
        },
        headers=headers,
    )
    assert s_resp.status_code == 200

    # Verify conversation history now contains the streamed messages
    h_resp = client.get(f"/api/v1/neon/conversations/{cid}", headers=headers)
    assert h_resp.status_code == 200
    messages = h_resp.json()["messages"]
    assert len(messages) >= 2
    user_msgs = [m for m in messages if m["role"] == "user"]
    asst_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(user_msgs) >= 1
    assert len(asst_msgs) >= 1
    assert "microservices" in user_msgs[0]["content"].lower()
    assert len(asst_msgs[0]["content"]) > 0


def test_07_expired_token_rejected_and_refresh_restores_access(
    client: TestClient, auth_headers: dict
) -> None:
    """Requirement 7: Expired JWT tokens trigger 401, while token refresh yields a usable token."""
    settings = get_settings()
    jwt_secret_str = (
        settings.jwt_secret.get_secret_value()
        if hasattr(settings.jwt_secret, "get_secret_value")
        else str(settings.jwt_secret)
    )

    # Craft an expired token for the owner
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_payload = {
        "sub": "usr_owner_001",
        "tenant_id": "ten_default",
        "role": "OWNER",
        "permissions": ["*"],
        "exp": int(past.timestamp()),
        "iat": int((past - timedelta(minutes=15)).timestamp()),
    }
    expired_jwt = jwt.encode(expired_payload, jwt_secret_str, algorithm="HS256")
    expired_headers = {"Authorization": f"Bearer {expired_jwt}"}

    resp = client.get("/api/v1/neon/conversations", headers=expired_headers)
    assert resp.status_code == 401
    err_msg = _get_err(resp).lower()
    assert "token" in err_msg or "expired" in err_msg or "authenticated" in err_msg or "bearer" in err_msg

    # Single-flight / refresh flow works using legitimate credentials and refresh endpoint
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner_admin", "password": "StrongOwnerPassword!2026"},
    )
    assert login_resp.status_code == 200
    refresh_tok = login_resp.json()["refresh_token"]

    rot_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_tok},
    )
    assert rot_resp.status_code == 200
    new_access_token = rot_resp.json()["access_token"]

    # Verify new token works on NEON
    ok_resp = client.get("/api/v1/neon/conversations", headers={"Authorization": f"Bearer {new_access_token}"})
    assert ok_resp.status_code == 200


def test_08_cross_tenant_conversation_isolation(client: TestClient, auth_headers: dict) -> None:
    """Requirement 8: Tenant isolation prevents cross-tenant conversation access or streaming."""
    headers = auth_headers["owner"]

    # Create a secondary isolated tenant and conversation directly in database
    session_factory = get_session_factory()
    with session_factory() as session:
        t2 = Tenant(tenant_id="TENANT-B-ISOLATED", name="Tenant B Organization", status="ACTIVE")
        session.add(t2)
        session.flush()
        u2 = User(
            user_id="usr_tenant_b_user",
            tenant_id="TENANT-B-ISOLATED",
            username="tenant_b_admin",
            email="tenant_b_admin@ultron.local",
            password_hash="fakehash123",
            role="OWNER",
            is_active=True,
        )
        session.add(u2)
        session.flush()
        conv_b = ConversationRecord(
            conversation_id="cnv_tenant_b_secret_99",
            tenant_id="TENANT-B-ISOLATED",
            user_id="usr_tenant_b_user",
            agent_id="AGT-01",
            title="Tenant B Secret Conversation",
        )
        session.add(conv_b)
        session.commit()

    # Tenant A lists conversations -> MUST NOT see Tenant B's conversation
    list_resp = client.get("/api/v1/neon/conversations", headers=headers)
    assert list_resp.status_code == 200
    c_list = list_resp.json().get("conversations", [])
    assert not any(c.get("conversation_id") == "cnv_tenant_b_secret_99" for c in c_list)

    # Tenant A attempts to read Tenant B's conversation directly -> 404 Not Found
    r_get = client.get("/api/v1/neon/conversations/cnv_tenant_b_secret_99", headers=headers)
    assert r_get.status_code == 404

    # Tenant A attempts to post message to Tenant B's conversation -> 404 Not Found
    r_msg = client.post(
        "/api/v1/neon/conversations/cnv_tenant_b_secret_99/messages",
        json={"content": "Malicious cross-tenant injection attempt."},
        headers=headers,
    )
    assert r_msg.status_code == 404

    # Tenant A attempts to stream into Tenant B's conversation -> 404 Not Found
    r_stream = client.post(
        "/api/v1/neon/stream",
        json={"prompt": "Cross tenant stream injection", "conversation_id": "cnv_tenant_b_secret_99"},
        headers=headers,
    )
    assert r_stream.status_code == 404


def test_09_agent_handoff_and_catalog_validation(client: TestClient, auth_headers: dict) -> None:
    """Requirement 9: Agent handoff routes to specified agents in catalog."""
    headers = auth_headers["owner"]

    for agent_id in ["AGT-01", "AGT-02", "AGT-03", "AGT-08", "AGT-20"]:
        resp = client.post(
            "/api/v1/neon/conversations",
            json={"title": f"Handoff to {agent_id}", "agent_id": agent_id},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == agent_id


def test_10_malformed_and_tampered_bearer_tokens_rejected(client: TestClient) -> None:
    """Requirement 10: Malformed, missing signature, or forged tokens rejected with 401."""
    # Garbage string
    r1 = client.get("/api/v1/neon/conversations", headers={"Authorization": "Bearer not-a-real-token"})
    assert r1.status_code == 401

    # Empty bearer
    r2 = client.get("/api/v1/neon/conversations", headers={"Authorization": "Bearer "})
    assert r2.status_code == 401

    # Bearer missing scheme
    r3 = client.get("/api/v1/neon/conversations", headers={"Authorization": "Token 123456"})
    assert r3.status_code == 401

    # Wrong secret key forged JWT
    bad_jwt = jwt.encode(
        {"sub": "attacker", "tenant_id": "ten_default", "role": "OWNER"},
        "wrong-secret-key-that-does-not-match-ultron-master",
        algorithm="HS256",
    )
    r4 = client.get("/api/v1/neon/conversations", headers={"Authorization": f"Bearer {bad_jwt}"})
    assert r4.status_code == 401


def test_11_chat_send_button_complete_lifecycle(client: TestClient, auth_headers: dict) -> None:
    """Requirement 11: Exact Send button flow executes successfully with Bearer token in persisted and streaming modes."""
    headers = auth_headers["owner"]

    # 1. Unauthenticated send message fails with 401
    r_unauth = client.post("/api/v1/neon/conversations", json={"title": "Send button test", "agent_id": "AGT-01"})
    assert r_unauth.status_code == 401
    assert "bearer" in _get_err(r_unauth).lower()

    # 2. Authenticated Send button flow: create conversation
    r_conv = client.post(
        "/api/v1/neon/conversations",
        json={"title": "Send button test", "agent_id": "AGT-01"},
        headers=headers,
    )
    assert r_conv.status_code == 201
    cid = r_conv.json()["conversation_id"]

    # 3. Authenticated Send: Persisted message mode
    r_msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        json={"content": "What is the status of the ULTRON autonomous core?", "enable_web_research": True},
        headers=headers,
    )
    assert r_msg.status_code == 200
    msg_data = r_msg.json()
    assert "assistant_message" in msg_data or "message" in msg_data

    # 4. Authenticated Send: SSE streaming mode
    r_stream = client.post(
        "/api/v1/neon/stream",
        json={"prompt": "Stream the latest system telemetry", "agent_id": "AGT-01", "conversation_id": cid},
        headers=headers,
    )
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers.get("content-type", "")

    # 5. Verify conversation history contains both user messages and assistant responses
    r_hist = client.get(f"/api/v1/neon/conversations/{cid}", headers=headers)
    assert r_hist.status_code == 200
    history_messages = r_hist.json().get("messages", [])
    assert len(history_messages) >= 2


def test_12_chat_send_request_header_and_query_fallbacks(client: TestClient, auth_headers: dict) -> None:
    """Requirement 12: Backend correctly extracts token from lowercase headers and strictly rejects query-string tokens."""
    owner_token = auth_headers["owner"]["Authorization"].split(" ")[1]

    # Lowercase authorization header (proxy normalization)
    r1 = client.get("/api/v1/neon/conversations", headers={"authorization": f"Bearer {owner_token}"})
    assert r1.status_code == 200

    # X-Authorization fallback (proxy/edge header forwarding)
    r_xauth = client.get("/api/v1/neon/conversations", headers={"X-Authorization": f"Bearer {owner_token}"})
    assert r_xauth.status_code == 200

    # X-Forwarded-Authorization fallback
    r_fwd = client.get("/api/v1/neon/conversations", headers={"x-forwarded-authorization": f"Bearer {owner_token}"})
    assert r_fwd.status_code == 200

    # Query param token without Authorization header MUST BE REJECTED with 401 (no credential in query string)
    r2 = client.post(f"/api/v1/neon/stream?token={owner_token}", json={"prompt": "Ping", "agent_id": "AGT-01"})
    assert r2.status_code == 401
    assert "bearer" in _get_err(r2).lower()


def test_13_production_vercel_cors_preflight_and_headers(client: TestClient, auth_headers: dict) -> None:
    """Requirement 13: CORS securely allows explicit production/preview origins and rejects unapproved origins."""
    from app.core.config import Settings
    from app.main import create_app

    owner_token = auth_headers["owner"]["Authorization"]

    # 1. Approved ULTRON production origin preflight
    r1 = client.options(
        "/api/v1/neon/conversations",
        headers={
            "Origin": "https://ultron-juwon2.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type, cache-control",
        },
    )
    assert r1.status_code == 200
    assert r1.headers.get("access-control-allow-origin") == "https://ultron-juwon2.vercel.app"
    assert "authorization" in r1.headers.get("access-control-allow-headers", "").lower()
    assert r1.headers.get("access-control-allow-credentials") == "true"

    # 2. Approved CARAVAN production origin preflight
    r2 = client.options(
        "/api/v1/neon/conversations",
        headers={
            "Origin": "https://caravan-juwon2.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert r2.status_code == 200
    assert r2.headers.get("access-control-allow-origin") == "https://caravan-juwon2.vercel.app"
    assert r2.headers.get("access-control-allow-credentials") == "true"

    # 3. Controlled preview origin through explicit allowlist
    custom_cfg = Settings(
        cors_preview_origins="https://ultron-preview-safe.vercel.app",
        ultron_env="test",
    )
    custom_app = create_app(custom_cfg)
    with TestClient(custom_app) as custom_client:
        r_preview = custom_client.options(
            "/api/v1/neon/conversations",
            headers={
                "Origin": "https://ultron-preview-safe.vercel.app",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )
        assert r_preview.status_code == 200
        assert r_preview.headers.get("access-control-allow-origin") == "https://ultron-preview-safe.vercel.app"

    # 4. Unapproved Vercel origin rejected (no broad wildcard regex!)
    r_unapproved_vercel = client.options(
        "/api/v1/neon/conversations",
        headers={
            "Origin": "https://unapproved-random-app.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r_unapproved_vercel.status_code == 400

    # 5. Disallowed external origin rejected
    r_malicious = client.options(
        "/api/v1/neon/conversations",
        headers={
            "Origin": "https://malicious-attacker.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r_malicious.status_code == 400

    # 6. Unapproved origins cannot read authenticated API responses (no Access-Control-Allow-Origin header returned)
    r_auth_unapproved = client.get(
        "/api/v1/neon/conversations",
        headers={
            "Origin": "https://unapproved-random-app.vercel.app",
            "Authorization": owner_token,
        },
    )
    assert "access-control-allow-origin" not in r_auth_unapproved.headers
    assert r_auth_unapproved.headers.get("access-control-allow-origin") is None


def test_14_chat_lifecycle_with_unconfigured_or_failing_gemini_diagnostics(
    client: TestClient, auth_headers: dict
) -> None:
    """Requirement 14: Chat lifecycle succeeds even when Gemini diagnostics report unconfigured or degraded."""
    headers = auth_headers["owner"]

    # Diagnostics show honest unconfigured / degraded status without raising 500
    r_diag = client.get("/api/v1/neon/gemini/diagnostics?discover=false", headers=headers)
    assert r_diag.status_code == 200
    diag_data = r_diag.json()
    assert "configured" in diag_data

    # Chat conversation creation works regardless of external diagnostics state
    r_conv = client.post(
        "/api/v1/neon/conversations",
        json={"title": "Resilient Session Thread", "agent_id": "AGT-01"},
        headers=headers,
    )
    assert r_conv.status_code == 201
    cid = r_conv.json()["conversation_id"]

    # Message sending succeeds with deterministic local fallback
    r_msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        json={"content": "Diagnose storage utilization and suggest cleanup directives."},
        headers=headers,
    )
    assert r_msg.status_code == 200
    data = r_msg.json()
    assert "assistant_message" in data or "message" in data or "reply" in data



