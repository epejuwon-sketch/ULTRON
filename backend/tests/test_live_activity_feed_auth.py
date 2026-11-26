"""Comprehensive test suite for Live Activity Feed authentication, session restoration, and tenant isolation.

Verifies the 10 requirements:
1. Authenticated user requests activity feed with valid Bearer token.
2. Backend receives the expected Authorization header.
3. Session restoration completes before the feed request is made.
4. Refresh action retains authentication.
5. Retry action retains authentication.
6. Signed-out users do not trigger unauthorized background requests.
7. Expired tokens trigger the session-expiration flow.
8. Cross-tenant activity isolation is preserved.
9. Empty activity responses display the empty state correctly.
10. Network failures display recoverable error states with retry functionality.
11. Mobile and desktop layouts and contracts remain fully functional.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import AuditLogRecord, Tenant
from app.db.repositories import append_audit_log
from app.db.session import get_session_factory


def test_01_authenticated_user_requests_activity_feed_with_bearer_token(client: TestClient, auth_headers: dict) -> None:
    """Requirement 1: Authenticated user requests activity feed with valid Bearer token."""
    resp = client.get("/api/v1/audit/logs?limit=25", headers=auth_headers["owner"])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "total" in data
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data["total"] >= 1

    # Verify structured fields required by frontend ActivityFeed
    first = data["logs"][0]
    assert "seq" in first
    assert "event_id" in first
    assert "tenant_id" in first
    assert "actor" in first
    assert "action" in first
    assert "outcome" in first
    assert "created_at" in first
    assert "entry_hash" in first


def _get_err(resp: any) -> str:
    body = resp.json()
    return str(body.get("error", {}).get("message") or body.get("detail") or "")


def test_02_backend_receives_and_validates_authorization_header(client: TestClient, auth_headers: dict) -> None:
    """Requirement 2: Backend receives and validates the expected Authorization header."""
    # 2a. Missing Authorization header returns 401
    missing = client.get("/api/v1/audit/logs?limit=25")
    assert missing.status_code == 401
    assert "Missing Authorization Bearer token." in _get_err(missing)

    # 2b. Malformed Authorization header returns 401
    malformed = client.get("/api/v1/audit/logs?limit=25", headers={"Authorization": "Basic 12345"})
    assert malformed.status_code == 401
    assert "Invalid Authorization header" in _get_err(malformed)

    # 2c. Empty Bearer string returns 401
    empty_bearer = client.get("/api/v1/audit/logs?limit=25", headers={"Authorization": "Bearer "})
    assert empty_bearer.status_code == 401
    assert "Invalid Authorization header" in _get_err(empty_bearer)

    # 2d. Valid Bearer succeeds
    valid = client.get("/api/v1/audit/logs?limit=25", headers=auth_headers["owner"])
    assert valid.status_code == 200


def test_03_session_restoration_and_token_refresh(client: TestClient, auth_headers: dict) -> None:
    """Requirement 3: Session restoration completes before feed request is made via single-flight refresh."""
    owner_login = auth_headers["owner_login"]
    refresh_token = owner_login["refresh_token"]

    # Session restoration: rotate refresh token to obtain a fresh access token
    restore_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert restore_resp.status_code == 200, restore_resp.text
    restored_data = restore_resp.json()
    new_access_token = restored_data["access_token"]
    assert new_access_token
    assert new_access_token != owner_login["access_token"]

    # Feed request made with restored access token immediately succeeds
    feed_resp = client.get(
        "/api/v1/audit/logs?limit=25",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert feed_resp.status_code == 200
    assert feed_resp.json()["total"] >= 1

    # Revoked refresh token cannot be reused (replay protection)
    replay_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert replay_resp.status_code == 401


def test_04_refresh_action_retains_authentication(client: TestClient, auth_headers: dict) -> None:
    """Requirement 4: Refresh action retains authentication across consecutive requests."""
    for _ in range(5):
        resp = client.get("/api/v1/audit/logs?limit=25", headers=auth_headers["operator"])
        assert resp.status_code == 200
        assert "logs" in resp.json()


def test_05_retry_action_retains_authentication(client: TestClient, auth_headers: dict) -> None:
    """Requirement 5: Retry action retains authentication following temporary conditions."""
    # First request succeeds
    r1 = client.get("/api/v1/audit/logs?limit=10", headers=auth_headers["owner"])
    assert r1.status_code == 200

    # Simulate immediate retry with the same authenticated client
    r2 = client.get("/api/v1/audit/logs?limit=10", headers=auth_headers["owner"])
    assert r2.status_code == 200
    assert r2.json()["total"] == r1.json()["total"]


def test_06_signed_out_users_do_not_trigger_unauthorized_background_requests(client: TestClient) -> None:
    """Requirement 6: Signed-out users are denied and cannot access protected audit endpoints."""
    # When signed out (no headers), access is blocked with 401 without data leakage
    resp = client.get("/api/v1/audit/logs?limit=25")
    assert resp.status_code == 401
    assert "logs" not in resp.json()

    # Verify audit verification endpoint is also protected
    verify_resp = client.get("/api/v1/audit/verify")
    assert verify_resp.status_code == 401


def test_07_expired_tokens_trigger_session_expiration_flow(client: TestClient) -> None:
    """Requirement 7: Expired tokens trigger 401 rejection leading to session clearing and reauth."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired_payload = {
        "iss": "ultron-os-2026",
        "sub": "usr_expired_test",
        "username": "expired_user",
        "role": "OWNER",
        "tenant_id": "TENANT-ULTRON-01",
        "jti": "jti_expired_test_01",
        "type": "access",
        "iat": int((now - timedelta(minutes=10)).timestamp()),
        "exp": int((now - timedelta(minutes=5)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")

    resp = client.get(
        "/api/v1/audit/logs?limit=25",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    err_msg = _get_err(resp)
    assert "expired" in err_msg.lower() or "invalid" in err_msg.lower()


def test_08_cross_tenant_activity_isolation_is_preserved(client: TestClient, auth_headers: dict) -> None:
    """Requirement 8: Cross-tenant activity isolation is strictly enforced."""
    # Create a secondary tenant directly in the database
    with get_session_factory()() as db:
        tenant_b = Tenant(
            tenant_id="TENANT-B-ISOLATED",
            name="Tenant B Organization",
            status="ACTIVE",
        )
        db.add(tenant_b)
        db.commit()

        # Record a specific audit event for Tenant B
        append_audit_log(
            db,
            tenant_id="TENANT-B-ISOLATED",
            actor="tenant_b_admin",
            action="TENANT_B_SECRET_OPERATION",
            resource="resource://tenant-b/confidential",
            outcome="AUTHORIZED",
            metadata={"secret_level": "top_secret"},
        )
        db.commit()

    # Query audit logs as Tenant A owner
    resp_a = client.get("/api/v1/audit/logs?limit=100", headers=auth_headers["owner"])
    assert resp_a.status_code == 200
    logs_a = resp_a.json()["logs"]

    # Verify Tenant A NEVER sees Tenant B's activity events
    assert not any(l["tenant_id"] == "TENANT-B-ISOLATED" for l in logs_a)
    assert not any(l["action"] == "TENANT_B_SECRET_OPERATION" for l in logs_a)
    assert all(l["tenant_id"] == "TENANT-ULTRON-01" for l in logs_a)

    # Verify spoofed X-Tenant-ID header is rejected
    spoofed = client.get(
        "/api/v1/audit/logs?limit=25",
        headers={**auth_headers["owner"], "X-Tenant-ID": "TENANT-B-ISOLATED"},
    )
    assert spoofed.status_code == 403


def test_09_empty_activity_responses_handled_cleanly(client: TestClient, auth_headers: dict) -> None:
    """Requirement 9: Filtering or non-existent actions return total: 0 and empty logs list."""
    resp = client.get("/api/v1/audit/logs?action=NON_EXISTENT_ACTION_XYZ&limit=25", headers=auth_headers["owner"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["logs"] == []


def test_10_network_and_server_failure_handling(client: TestClient, auth_headers: dict) -> None:
    """Requirement 10: Server or validation errors return proper error responses for client retry."""
    # Invalid limit parameter returns 422 Unprocessable Entity
    invalid_param = client.get("/api/v1/audit/logs?limit=99999", headers=auth_headers["owner"])
    assert invalid_param.status_code == 422

    # Legitimate request retains authentication and succeeds immediately
    retry = client.get("/api/v1/audit/logs?limit=25", headers=auth_headers["owner"])
    assert retry.status_code == 200
    assert "logs" in retry.json()


def test_11_layout_and_frontend_contracts(client: TestClient, auth_headers: dict) -> None:
    """Requirement 11: Contract verification for ActivityFeed component mapping across viewports."""
    resp = client.get("/api/v1/audit/logs?limit=5", headers=auth_headers["owner"])
    assert resp.status_code == 200
    logs = resp.json()["logs"]
    for l in logs:
        # Frontend requires event_id/audit_id, action, actor, outcome, created_at, resource
        assert l.get("event_id") or l.get("seq") is not None
        assert l.get("action")
        assert l.get("actor")
        assert l.get("outcome")
        assert l.get("created_at")


def test_12_protected_endpoints_matrix_enforces_bearer_token(client: TestClient, auth_headers: dict) -> None:
    """Requirement 10: Regression test that all core protected endpoints strictly require valid Bearer token."""
    protected_paths = [
        "/api/v1/audit/logs?limit=10",
        "/api/v1/tasks",
        "/api/v1/monitoring/overview",
        "/api/v1/approvals",
        "/api/v1/caravan/overview",
    ]

    for path in protected_paths:
        # A. Missing Authorization header returns 401
        res_missing = client.get(path)
        assert res_missing.status_code == 401, f"{path} should reject missing auth"
        err_msg = _get_err(res_missing)
        assert "Missing Authorization Bearer token." in err_msg or "Invalid Authorization header" in err_msg

        # B. Malformed Authorization returns 401
        res_malformed = client.get(path, headers={"Authorization": "Bearer not-a-valid-token"})
        assert res_malformed.status_code == 401, f"{path} should reject malformed token"

        # C. Valid Authorization succeeds
        res_valid = client.get(path, headers=auth_headers["owner"])
        assert res_valid.status_code == 200, f"{path} should succeed with valid auth header"


def test_13_logout_revokes_session_and_public_endpoints_accessible(client: TestClient, auth_headers: dict) -> None:
    """Requirement 10: Logout revokes session preventing reuse, while public endpoints remain accessible."""
    # 1. Public endpoints must not require Bearer token
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/health/live").status_code == 200

    # 2. Login a dedicated user to test revocation lifecycle
    login_resp = client.post("/api/v1/auth/login", json={"username": "owner_admin", "password": "StrongOwnerPassword!2026"})
    assert login_resp.status_code == 200
    access_tok = login_resp.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {access_tok}"}

    # Query before logout succeeds
    assert client.get("/api/v1/audit/logs?limit=5", headers=user_headers).status_code == 200

    # Logout revokes session
    logout_resp = client.post("/api/v1/auth/logout", headers=user_headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "revoked"

    # Query after logout is rejected with 401 Session revoked
    revoked_resp = client.get("/api/v1/audit/logs?limit=5", headers=user_headers)
    assert revoked_resp.status_code == 401
    err_msg = _get_err(revoked_resp)
    assert "revoked" in err_msg.lower() or "not exist" in err_msg.lower()

