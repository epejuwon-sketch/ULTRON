"""Regression tests for Vercel read-only filesystem safety, Supabase PostgreSQL configuration, and SQLite isolation."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from app.core.config import Settings, get_settings, normalize_database_url
from app.core.exceptions import ConfigurationError, DatabaseConfigurationError
from app.core.logging import redact_secrets
from app.db import session as db_session
from app.db.session import check_database_health, get_engine, init_database, reset_engine
from app.main import create_app
from app.services.storage_adapter import get_storage_adapter

_PROD_JWT = "prod-jwt-secret-key-0123456789abcdef0123456789"
_PROD_VAULT = "prod-vault-master-key-0123456789abcdef01234567"


def _forbid_mkdir(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch Path.mkdir to simulate Vercel's read-only deployment filesystem (/var/task)."""
    attempted: list[str] = []

    def _ro_mkdir(self: Path, *args, **kwargs) -> None:
        attempted.append(str(self))
        raise OSError(errno.EROFS, "Read-only file system", str(self))

    monkeypatch.setattr(Path, "mkdir", _ro_mkdir)
    return attempted


def test_production_staging_and_vercel_never_select_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ULTRON_ENV", "ULTRON_DATABASE_URL", "VERCEL", "VERCEL_ENV"):
        monkeypatch.delenv(var, raising=False)

    deployed_configs = [
        Settings(
            ULTRON_ENV="production",
            ULTRON_JWT_SECRET=_PROD_JWT,
            ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
            ULTRON_DATABASE_URL="",
        ),
        Settings(
            ULTRON_ENV="staging",
            ULTRON_DATABASE_URL="",
        ),
        Settings(
            ULTRON_ENV="development",
            VERCEL="1",
            VERCEL_ENV="preview",
            ULTRON_DATABASE_URL="",
        ),
        Settings(
            ULTRON_ENV="development",
            VERCEL="1",
            VERCEL_ENV="production",
            ULTRON_DATABASE_URL="",
        ),
        Settings(
            ULTRON_ENV="production",
            ULTRON_JWT_SECRET=_PROD_JWT,
            ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
            ULTRON_DATABASE_URL="sqlite:///./data/ultron_os_2026.db",
        ),
        Settings(
            ULTRON_ENV="development",
            VERCEL="1",
            VERCEL_ENV="preview",
            ULTRON_DATABASE_URL="sqlite:///./data/ultron_os_2026.db",
        ),
    ]

    for cfg in deployed_configs:
        assert cfg.is_deployed_environment is True
        assert cfg.database_backend != "sqlite"
        with pytest.raises(DatabaseConfigurationError) as exc_info:
            _ = cfg.effective_database_url
        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "DATABASE_CONFIGURATION_ERROR"
        assert "ULTRON_DATABASE_URL" in exc_info.value.message


def test_missing_deployed_database_url_returns_clear_503_on_bootstrap_owner_without_filesystem_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_mkdirs = _forbid_mkdir(monkeypatch)
    monkeypatch.setenv("ULTRON_ENV", "development")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("ULTRON_DATABASE_URL", "")
    monkeypatch.setenv("ULTRON_JWT_SECRET", _PROD_JWT)
    monkeypatch.setenv("ULTRON_VAULT_MASTER_KEY", _PROD_VAULT)

    get_settings.cache_clear()
    reset_engine()
    try:
        cfg = get_settings()
        assert cfg.is_vercel is True
        assert cfg.is_deployed_environment is True
        assert cfg.database_backend == "unconfigured"

        app = create_app(cfg)
        with TestClient(app) as tc:
            live = tc.get("/health/live")
            assert live.status_code == 200
            assert live.json()["status"] == "ok"

            ready = tc.get("/health/ready")
            assert ready.status_code == 200
            ready_body = ready.json()
            assert ready_body["status"] == "degraded"
            assert ready_body["database"]["healthy"] is False
            assert ready_body["database"]["backend"] == "unconfigured"
            assert "ULTRON_DATABASE_URL" in ready_body["database"]["detail"]

            resp = tc.post(
                "/api/v1/auth/bootstrap-owner",
                json={
                    "username": "vercel_owner",
                    "email": "owner@ultron.dev",
                    "password": "StrongOwnerPassword!2026",
                    "tenant_id": "TENANT-ULTRON-01",
                    "organization_name": "ULTRON Vercel Org",
                },
            )
            assert resp.status_code == 503, resp.text
            err = resp.json()["error"]
            assert err["code"] == "DATABASE_CONFIGURATION_ERROR"
            assert "ULTRON_DATABASE_URL" in err["message"]
            assert err["details"]["required_env_var"] == "ULTRON_DATABASE_URL"

        assert attempted_mkdirs == [], f"Unexpected filesystem mkdir calls: {attempted_mkdirs}"
    finally:
        reset_engine()
        get_settings.cache_clear()


def test_bootstrap_owner_does_not_attempt_filesystem_writes_and_preserves_safeguards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_mkdirs = _forbid_mkdir(monkeypatch)
    monkeypatch.setenv("ULTRON_ENV", "test")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("ULTRON_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ULTRON_JWT_SECRET", _PROD_JWT)
    monkeypatch.setenv("ULTRON_VAULT_MASTER_KEY", _PROD_VAULT)

    get_settings.cache_clear()
    reset_engine()

    # Use a single shared in-memory engine (StaticPool) so SQLAlchemy never touches disk
    mem_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    monkeypatch.setattr(db_session, "_build_engine", lambda _cfg: mem_engine)

    try:
        cfg = get_settings()
        app = create_app(cfg)
        with TestClient(app) as tc:
            first = tc.post(
                "/api/v1/auth/bootstrap-owner",
                json={
                    "username": "readonly_owner",
                    "email": "owner@ultron.dev",
                    "password": "StrongOwnerPassword!2026",
                    "tenant_id": "TENANT-ULTRON-01",
                    "organization_name": "ULTRON Serverless Org",
                },
            )
            assert first.status_code == 201, first.text
            assert first.json()["role"] == "OWNER"
            assert first.json()["tenant_id"] == "TENANT-ULTRON-01"

            # One-time owner bootstrap safeguard remains enforced
            duplicate = tc.post(
                "/api/v1/auth/bootstrap-owner",
                json={
                    "username": "second_owner",
                    "email": "second@ultron.dev",
                    "password": "StrongOwnerPassword!2026",
                    "tenant_id": "TENANT-ULTRON-01",
                },
            )
            assert duplicate.status_code == 409

            login = tc.post(
                "/api/v1/auth/login",
                json={"username": "readonly_owner", "password": "StrongOwnerPassword!2026"},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]
            me = tc.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["username"] == "readonly_owner"

        assert attempted_mkdirs == [], f"Unexpected filesystem mkdir calls: {attempted_mkdirs}"
    finally:
        reset_engine()
        get_settings.cache_clear()


def test_postgresql_connection_string_normalization_driver_and_serverless_pooling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_mkdirs = _forbid_mkdir(monkeypatch)
    for var in ("ULTRON_ENV", "ULTRON_DATABASE_URL", "VERCEL", "VERCEL_ENV"):
        monkeypatch.delenv(var, raising=False)

    # 1. postgres:// scheme -> postgresql+psycopg:// with sslmode=require for remote Supabase host
    url_pooler = normalize_database_url(
        "postgres://postgres.projref:MySecretPass123@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
        allow_sqlite=False,
        env_label="production",
        is_vercel=True,
    )
    assert url_pooler.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url_pooler

    # 2. postgresql:// scheme -> postgresql+psycopg://
    url_direct = normalize_database_url(
        "postgresql://postgres:MySecretPass123@db.projref.supabase.co:5432/postgres",
        allow_sqlite=False,
    )
    assert url_direct.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url_direct

    # 3. postgresql+psycopg2:// normalized to installed psycopg v3, preserving explicit sslmode
    url_explicit_ssl = normalize_database_url(
        "postgresql+psycopg2://postgres:MySecretPass123@db.projref.supabase.co:5432/postgres?sslmode=verify-full",
        allow_sqlite=False,
    )
    assert url_explicit_ssl.startswith("postgresql+psycopg://")
    assert "sslmode=verify-full" in url_explicit_ssl

    # 4. localhost PostgreSQL does not force sslmode=require
    url_local = normalize_database_url(
        "postgresql://postgres:devpass@localhost:5432/ultron",
        allow_sqlite=False,
    )
    assert url_local == "postgresql+psycopg://postgres:devpass@localhost:5432/ultron"

    # 5. Accidental Supabase HTTP URL rejected clearly without echoing secret or URL
    with pytest.raises(DatabaseConfigurationError, match="not an HTTP/HTTPS URL"):
        normalize_database_url("https://projref.supabase.co", allow_sqlite=False)

    # 6. Vercel serverless engine uses psycopg v3 + NullPool + zero filesystem writes
    reset_engine()
    try:
        vercel_pg_cfg = Settings(
            ULTRON_ENV="production",
            VERCEL="1",
            VERCEL_ENV="production",
            ULTRON_JWT_SECRET=_PROD_JWT,
            ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
            ULTRON_DATABASE_URL="postgresql://postgres.projref:MySecretPass123@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
        )
        assert vercel_pg_cfg.database_backend == "postgresql"
        assert vercel_pg_cfg.is_vercel is True
        engine = get_engine(vercel_pg_cfg)
        assert engine.dialect.name == "postgresql"
        assert engine.driver == "psycopg"
        assert isinstance(engine.pool, NullPool)

        # 7. Persistent non-Vercel production engine uses QueuePool + psycopg v3
        reset_engine()
        persistent_pg_cfg = Settings(
            ULTRON_ENV="production",
            VERCEL="",
            VERCEL_ENV="",
            ULTRON_JWT_SECRET=_PROD_JWT,
            ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
            ULTRON_DATABASE_URL="postgresql://postgres:MySecretPass123@db.projref.supabase.co:5432/postgres",
        )
        assert persistent_pg_cfg.is_vercel is False
        assert persistent_pg_cfg.is_deployed_environment is True
        engine_persistent = get_engine(persistent_pg_cfg)
        assert engine_persistent.dialect.name == "postgresql"
        assert engine_persistent.driver == "psycopg"
        assert isinstance(engine_persistent.pool, QueuePool)

        assert attempted_mkdirs == []
    finally:
        reset_engine()


def test_local_development_and_test_environments_keep_sqlite_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in ("VERCEL", "VERCEL_ENV", "ULTRON_DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)

    dev_db = tmp_path / "local_dev" / "ultron.db"
    dev_cfg = Settings(
        ULTRON_ENV="development",
        ULTRON_DATABASE_URL="",
        ULTRON_SQLITE_PATH=str(dev_db),
    )
    assert dev_cfg.is_deployed_environment is False
    assert dev_cfg.database_backend == "sqlite"
    assert dev_cfg.effective_database_url == f"sqlite:///{dev_db}"

    reset_engine()
    try:
        init_database(dev_cfg)
        healthy, detail = check_database_health(dev_cfg)
        assert healthy is True
        assert detail == "ok"
        assert dev_db.exists()
    finally:
        reset_engine()


def test_deployed_storage_adapter_rejects_local_disk_and_logs_redact_pg_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_mkdirs = _forbid_mkdir(monkeypatch)
    vercel_cfg = Settings(
        ULTRON_ENV="development",
        VERCEL="1",
        VERCEL_ENV="preview",
        SUPABASE_URL="",
        SUPABASE_SERVICE_ROLE_KEY=None,
    )
    with pytest.raises(ConfigurationError, match="Supabase Storage is required"):
        get_storage_adapter(vercel_cfg)
    assert attempted_mkdirs == []

    sample = "OperationalError: connection to postgresql+psycopg://postgres.abc:TopSecretPass!42@db.abc.supabase.co:5432/postgres failed"
    scrubbed = redact_secrets(sample)
    assert "TopSecretPass!42" not in scrubbed
    assert "postgres.abc:[REDACTED]@db.abc.supabase.co:5432/postgres" in scrubbed
