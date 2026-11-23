"""Tests for Universal Connections Centre 2.0: Registry, 4 Methods, SSRF Guard, Webhooks, Lifecycle & NEON/ARGON."""

from __future__ import annotations

import hashlib
import hmac

import httpx
from fastapi.testclient import TestClient


def test_universal_connections_api_key_lifecycle_and_neon_argon_gates(
    client: TestClient,
    auth_headers: dict,
) -> None:
    from types import SimpleNamespace

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.db.session import get_engine
    from app.services import universal_connections_service

    # 1. Catalogue lists 14 categories and 11 lifecycle states
    cat = client.get("/api/v1/integrations/universal/catalogue", headers=auth_headers["owner"])
    assert cat.status_code == 200
    assert len(cat.json()["categories"]) == 14
    assert len(cat.json()["lifecycle_states"]) == 11

    # 2. Register custom API_KEY connector (secret never echoed back; never marked LIVE_VERIFIED yet)
    reg = client.post(
        "/api/v1/integrations/universal/connectors",
        headers=auth_headers["owner"],
        json={
            "name": "Linear",
            "category": "Productivity",
            "connection_method": "API_KEY",
            "website_url": "https://linear.app",
            "docs_url": "https://developers.linear.app",
            "api_base_url": "https://api.linear.app/graphql",
            "capabilities": ["read_issues", "create_issue"],
            "required_scopes": ["read", "write"],
            "credentials": {"api_key": "lin_api_test_secret_value"},
        },
    )
    assert reg.status_code == 201, reg.text
    conn = reg.json()
    cid = conn["connector_id"]
    assert conn["lifecycle_state"] == "AUTHENTICATED"
    assert "lin_api_test_secret_value" not in str(conn)

    # 3. ARGON action-level gate requires explicit user approval first
    unapproved = client.post(
        f"/api/v1/integrations/universal/connectors/{cid}/authorize-action",
        headers=auth_headers["owner"],
        json={"capability": "read_issues"},
    )
    assert unapproved.status_code == 200
    assert unapproved.json()["authorized"] is False
    assert unapproved.json()["status"] == "APPROVAL_REQUIRED"

    disc_before = client.get("/api/v1/integrations/universal/discover-authorized", headers=auth_headers["owner"])
    assert disc_before.status_code == 200
    assert all(s["connector_id"] != cid for s in disc_before.json()["services"])

    # Approve connector permissions
    app_res = client.post(
        f"/api/v1/integrations/universal/connectors/{cid}/approve",
        headers=auth_headers["owner"],
        json={"scopes": ["read", "write"]},
    )
    assert app_res.status_code == 200
    assert app_res.json()["approved_by"] is not None

    disc_after = client.get("/api/v1/integrations/universal/discover-authorized", headers=auth_headers["owner"])
    assert any(s["connector_id"] == cid for s in disc_after.json()["services"])

    ok_act = client.post(
        f"/api/v1/integrations/universal/connectors/{cid}/authorize-action",
        headers=auth_headers["owner"],
        json={"capability": "read_issues"},
    )
    assert ok_act.status_code == 200
    assert ok_act.json()["authorized"] is True

    bad_cap = client.post(
        f"/api/v1/integrations/universal/connectors/{cid}/authorize-action",
        headers=auth_headers["owner"],
        json={"capability": "delete_workspace"},
    )
    assert bad_cap.status_code == 200
    assert bad_cap.json()["authorized"] is False
    assert bad_cap.json()["status"] == "CAPABILITY_NOT_PERMITTED"

    # 4. Test Connection transitions (200 -> LIVE_VERIFIED, 401 -> FAILED, timeout -> DEGRADED)
    settings = get_settings()
    db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
    try:
        tid = db.execute(text("SELECT tenant_id FROM tenants LIMIT 1")).scalar_one()
        principal = SimpleNamespace(user_id="owner-1", username="owner", tenant_id=tid, role="OWNER")

        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))) as c200:
            t200 = universal_connections_service.test_universal_connector(db, principal=principal, connector_id=cid, settings=settings, http_client=c200)
            assert t200["lifecycle_state"] == "LIVE_VERIFIED"

        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401))) as c401:
            t401 = universal_connections_service.test_universal_connector(db, principal=principal, connector_id=cid, settings=settings, http_client=c401)
            assert t401["lifecycle_state"] == "FAILED"

        def _timeout(_req):
            raise httpx.ReadTimeout("timeout")

        with httpx.Client(transport=httpx.MockTransport(_timeout)) as c_to:
            tto = universal_connections_service.test_universal_connector(db, principal=principal, connector_id=cid, settings=settings, http_client=c_to)
            assert tto["lifecycle_state"] == "DEGRADED"
    finally:
        db.close()

    # 5. Rotate & Revoke
    rot = client.post(
        f"/api/v1/integrations/universal/connectors/{cid}/rotate",
        headers=auth_headers["owner"],
        json={"credentials": {"api_key": "lin_api_rotated_secret"}},
    )
    assert rot.status_code == 200
    assert rot.json()["lifecycle_state"] == "AUTHENTICATED"
    assert "lin_api_rotated_secret" not in str(rot.json())

    rev = client.post(f"/api/v1/integrations/universal/connectors/{cid}/revoke", headers=auth_headers["owner"])
    assert rev.status_code == 200
    assert rev.json()["lifecycle_state"] == "REVOKED"


def test_universal_connections_ssrf_website_and_webhooks(client: TestClient, auth_headers: dict) -> None:
    from types import SimpleNamespace

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.db.session import get_engine
    from app.services import universal_connections_service

    # 1. SSRF protection blocks loopback, metadata IPs, private CIDRs, and file://
    for ssrf_url in [
        "http://127.0.0.1:8000/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:3000",
        "http://10.0.0.1/internal",
        "file:///etc/passwd",
    ]:
        bad_web = client.post(
            "/api/v1/integrations/universal/website-inspect",
            headers=auth_headers["owner"],
            json={"website_url": ssrf_url},
        )
        assert bad_web.status_code in (400, 403, 422), f"SSRF not blocked for {ssrf_url}: {bad_web.text}"

    # 2. Website inspection detects OAuth/API key/Webhook without marking authenticated
    settings = get_settings()
    db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
    try:
        tid = db.execute(text("SELECT tenant_id FROM tenants LIMIT 1")).scalar_one()
        principal = SimpleNamespace(user_id="owner-1", username="owner", tenant_id=tid, role="OWNER")
        html = '<html><a href="https://developers.example.com/docs">API Docs</a> OAuth 2.0 and API key and Webhook signing secret</html>'
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html))) as mock_http:
            insp = universal_connections_service.inspect_website_integration(
                db,
                principal=principal,
                website_url="https://example.com",
                http_client=mock_http,
            )
            assert insp["lifecycle_state"] == "DISCOVERED"
            assert insp["authenticated"] is False
            assert "OAUTH2" in insp["detected_auth_methods"]
            assert "API_KEY" in insp["detected_auth_methods"]
            assert "WEBHOOK" in insp["detected_auth_methods"]
    finally:
        db.close()

    # 3. Webhook connector: HMAC-SHA256 signature verification + replay protection + delivery logs
    wh_secret = "ultron-universal-wh-secret-test"
    wh_reg = client.post(
        "/api/v1/integrations/universal/connectors",
        headers=auth_headers["owner"],
        json={
            "name": "Shopify Webhook",
            "category": "Business operations",
            "connection_method": "WEBHOOK",
            "webhook_secret": wh_secret,
            "subscribed_events": ["order.created"],
        },
    )
    assert wh_reg.status_code == 201
    wh_cid = wh_reg.json()["connector_id"]
    assert wh_reg.json()["has_webhook_secret"] is True
    assert wh_secret not in str(wh_reg.json())

    payload = b'{"event":"order.created","order_id":"ord_123"}'
    sig = hmac.new(wh_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # Invalid signature rejected (401)
    bad_sig = client.post(
        f"/api/v1/integrations/universal/webhooks/{wh_cid}",
        headers={"X-Ultron-Signature": "sha256=deadbeef", "X-Idempotency-Key": "evt_1"},
        content=payload,
    )
    assert bad_sig.status_code == 401

    # Valid signature accepted (200)
    good_sig = client.post(
        f"/api/v1/integrations/universal/webhooks/{wh_cid}",
        headers={"X-Ultron-Signature": f"sha256={sig}", "X-Idempotency-Key": "evt_1", "X-Event-Type": "order.created"},
        content=payload,
    )
    assert good_sig.status_code == 200
    assert good_sig.json()["status"] == "ACCEPTED"

    # Replay with same idempotency key detected
    replay = client.post(
        f"/api/v1/integrations/universal/webhooks/{wh_cid}",
        headers={"X-Ultron-Signature": f"sha256={sig}", "X-Idempotency-Key": "evt_1"},
        content=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "DUPLICATE_REPLAY"

    # Delivery logs recorded
    delivs = client.get(f"/api/v1/integrations/universal/connectors/{wh_cid}/deliveries", headers=auth_headers["owner"])
    assert delivs.status_code == 200
    assert delivs.json()["total"] == 2
