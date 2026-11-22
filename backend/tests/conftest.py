"""Pytest fixtures providing isolated databases, settings, and multi-role authenticated clients."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import init_database, reset_engine
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_file = tmp_path / "ultron_test.db"
    monkeypatch.setenv("ULTRON_ENV", "test")
    monkeypatch.setenv("ULTRON_SQLITE_PATH", str(db_file))
    monkeypatch.setenv("ULTRON_DATABASE_URL", "")
    monkeypatch.setenv("ULTRON_JWT_SECRET", "test-jwt-secret-key-with-at-least-40-characters-0001")
    monkeypatch.setenv("ULTRON_VAULT_MASTER_KEY", "test-vault-master-key-with-at-least-40-characters-0001")
    monkeypatch.setenv("ULTRON_APPROVAL_SOFT_LIMIT_USD", "50.0")
    monkeypatch.setenv("ULTRON_MAX_FAILED_LOGINS", "3")
    # Ensure external keys are cleared so offline tests are strictly deterministic
    for var in (
        "VERCEL",
        "VERCEL_ENV",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "GEMINI_API_KEY",
        "VERCEL_TOKEN",
        "VERCEL_PROJECT_ID",
        "VERCEL_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_KV_NAMESPACE_ID",
    ):
        monkeypatch.delenv(var, raising=False)

    get_settings.cache_clear()
    reset_engine()
    settings = get_settings()
    init_database(settings)
    app = create_app(settings)

    with TestClient(app) as test_client:
        yield test_client

    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, dict[str, str]]:
    """Bootstrap OWNER + provision OPERATOR and VIEWER accounts, returning Bearer header maps."""
    resp = client.post(
        "/api/v1/auth/bootstrap-owner",
        json={
            "username": "owner_admin",
            "email": "owner@ultron.local",
            "password": "StrongOwnerPassword!2026",
            "tenant_id": "TENANT-ULTRON-01",
            "organization_name": "ULTRON Test Org",
        },
    )
    assert resp.status_code == 201, resp.text

    owner_login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner_admin", "password": "StrongOwnerPassword!2026"},
    )
    assert owner_login.status_code == 200, owner_login.text
    owner_token = owner_login.json()["access_token"]
    owner_hdr = {"Authorization": f"Bearer {owner_token}"}

    # Create OPERATOR and VIEWER
    for uname, role in (("ops_user", "OPERATOR"), ("view_user", "VIEWER")):
        r = client.post(
            "/api/v1/auth/users",
            headers=owner_hdr,
            json={
                "username": uname,
                "email": f"{uname}@ultron.local",
                "password": "StrongRolePassword!2026",
                "role": role,
            },
        )
        assert r.status_code == 201, r.text

    ops_token = client.post(
        "/api/v1/auth/login",
        json={"username": "ops_user", "password": "StrongRolePassword!2026"},
    ).json()["access_token"]
    view_token = client.post(
        "/api/v1/auth/login",
        json={"username": "view_user", "password": "StrongRolePassword!2026"},
    ).json()["access_token"]

    return {
        "owner": owner_hdr,
        "operator": {"Authorization": f"Bearer {ops_token}"},
        "viewer": {"Authorization": f"Bearer {view_token}"},
        "owner_login": owner_login.json(),
    }
