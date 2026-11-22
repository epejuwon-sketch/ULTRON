"""Tests for Argon2id auth, JWT lifecycle, rotation, revocation, lockout, RBAC, and tenant isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_bootstrap_owner_idempotency_and_login_flow(client: TestClient, auth_headers: dict) -> None:
    # Second bootstrap for same tenant must be rejected with 409 Conflict
    dup = client.post(
        "/api/v1/auth/bootstrap-owner",
        json={
            "username": "second_owner",
            "email": "second@ultron.local",
            "password": "AnotherStrongPassword!2026",
            "tenant_id": "TENANT-ULTRON-01",
        },
    )
    assert dup.status_code == 409

    me = client.get("/api/v1/auth/me", headers=auth_headers["owner"])
    assert me.status_code == 200
    assert me.json()["role"] == "OWNER"
    assert me.json()["tenant_id"] == "TENANT-ULTRON-01"
    assert "vault:write" in me.json()["permissions"]


def test_refresh_token_rotation_and_logout_revocation(client: TestClient, auth_headers: dict) -> None:
    refresh_token = auth_headers["owner_login"]["refresh_token"]
    old_access = auth_headers["owner_login"]["access_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert rotated.status_code == 200
    new_access = rotated.json()["access_token"]
    assert new_access != old_access

    # Old refresh token cannot be reused
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401

    # Old access token was revoked on rotation
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code == 401

    # New access token works, then logout revokes it immediately
    new_hdr = {"Authorization": f"Bearer {new_access}"}
    assert client.get("/api/v1/auth/me", headers=new_hdr).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=new_hdr).status_code == 200
    assert client.get("/api/v1/auth/me", headers=new_hdr).status_code == 401


def test_brute_force_account_lockout(client: TestClient, auth_headers: dict) -> None:
    for _ in range(3):
        r = client.post("/api/v1/auth/login", json={"username": "ops_user", "password": "wrong-password"})
        assert r.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={"username": "ops_user", "password": "StrongRolePassword!2026"},
    )
    assert locked.status_code == 423


def test_rbac_permissions_and_tenant_isolation(client: TestClient, auth_headers: dict) -> None:
    # Unauthenticated access is rejected
    assert client.get("/api/v1/agents").status_code == 401

    # VIEWER can read agents but cannot create tasks or manage users
    assert client.get("/api/v1/agents", headers=auth_headers["viewer"]).status_code == 200
    assert (
        client.post(
            "/api/v1/tasks",
            headers=auth_headers["viewer"],
            json={"title": "Test", "objective": "Summarize status"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/users",
            headers=auth_headers["operator"],
            json={"username": "u3", "email": "u3@ultron.local", "password": "Password123!", "role": "VIEWER"},
        ).status_code
        == 403
    )

    # Cross-tenant X-Tenant-ID header spoofing is rejected with 403
    spoof_hdr = dict(auth_headers["owner"])
    spoof_hdr["X-Tenant-ID"] = "TENANT-OTHER-99"
    assert client.get("/api/v1/tasks", headers=spoof_hdr).status_code == 403
