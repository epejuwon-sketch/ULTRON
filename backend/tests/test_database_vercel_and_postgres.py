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


def test_supabase_pooler_query_params_and_quoted_urls_normalize_for_psycopg() -> None:
    import psycopg.conninfo

    quoted_with_prisma_params = (
        '"postgresql://postgres.projref:MyPass99@aws-0-us-east-1.pooler.supabase.com:6543/postgres'
        '?pgbouncer=true&connection_limit=1&supa=base-pooler.x&schema=public"'
    )
    normalized = normalize_database_url(
        quoted_with_prisma_params,
        allow_sqlite=False,
        env_label="production",
        is_vercel=True,
    )
    assert normalized.startswith("postgresql+psycopg://")
    assert "pgbouncer" not in normalized
    assert "supa=" not in normalized
    assert "connection_limit" not in normalized
    assert "sslmode=require" in normalized

    # Confirm psycopg v3 libpq parser accepts the resulting URL cleanly
    libpq_uri = normalized.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed_info = psycopg.conninfo.conninfo_to_dict(libpq_uri)
    assert parsed_info["host"] == "aws-0-us-east-1.pooler.supabase.com"
    assert parsed_info["port"] == "6543"
    assert parsed_info["sslmode"] == "require"


def test_postgresql_runtime_failure_degrades_cleanly_without_crashing_lifespan_or_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    attempted_mkdirs = _forbid_mkdir(monkeypatch)
    monkeypatch.setenv("ULTRON_ENV", "development")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("VERCEL_URL", "ultron-abc123.vercel.app")
    monkeypatch.setenv("VERCEL_BRANCH_URL", "ultron-git-feat-ultron-os-2026-backend-juwon2.vercel.app")
    monkeypatch.setenv(
        "ULTRON_DATABASE_URL",
        "postgresql://postgres:VerySecretPassword!@db.projref.supabase.co:5432/postgres",
    )

    get_settings.cache_clear()
    reset_engine()

    def _failing_creator():
        raise psycopg.OperationalError(
            "connection failed: postgresql://postgres:VerySecretPassword!@db.projref.supabase.co:5432/postgres: Network is unreachable"
        )

    real_failing_engine = create_engine(
        "postgresql+psycopg://",
        creator=_failing_creator,
        poolclass=NullPool,
        future=True,
    )
    monkeypatch.setattr(db_session, "_build_engine", lambda _cfg: real_failing_engine)

    try:
        cfg = get_settings()
        assert "https://ultron-abc123.vercel.app" in cfg.cors_origin_list
        assert "https://ultron-git-feat-ultron-os-2026-backend-juwon2.vercel.app" in cfg.cors_origin_list

        app = create_app(cfg)
        with TestClient(app) as tc:
            live = tc.get("/health/live")
            assert live.status_code == 200
            assert live.json()["status"] == "ok"

            ready = tc.get("/health/ready")
            assert ready.status_code == 200
            body = ready.json()
            assert body["status"] == "degraded"
            assert body["database"]["healthy"] is False
            assert body["database"]["backend"] == "postgresql"
            assert body["database"]["error_code"] == "DB_IPV6_DIRECT_PORT_5432"
            assert "6543" in body["database"]["detail"]
            assert "VerySecretPassword!" not in str(body)

            boot = tc.post(
                "/api/v1/auth/bootstrap-owner",
                json={
                    "username": "owner_fail",
                    "email": "owner@ultron.dev",
                    "password": "StrongOwnerPassword!2026",
                },
            )
            assert boot.status_code == 503, boot.text
            err = boot.json()["error"]
            assert err["code"] == "DATABASE_UNAVAILABLE"
            assert err["details"]["error_code"] == "DB_IPV6_DIRECT_PORT_5432"
            assert "VerySecretPassword!" not in boot.text

        assert attempted_mkdirs == []
    finally:
        reset_engine()
        get_settings.cache_clear()


def test_classify_database_error_diagnoses_supabase_auth_and_pooler_errors() -> None:
    cfg = Settings(
        ULTRON_ENV="production",
        VERCEL="1",
        VERCEL_ENV="preview",
        ULTRON_JWT_SECRET=_PROD_JWT,
        ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
        ULTRON_DATABASE_URL="postgresql://postgres.projref:Secret123@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    )
    code1, msg1 = db_session.classify_database_error(
        Exception("FATAL: Tenant or user not found"), cfg
    )
    assert code1 == "DB_POOLER_TENANT_USER_NOT_FOUND"
    assert "postgres.<project-ref>" in msg1

    code2, msg2 = db_session.classify_database_error(
        Exception("FATAL: password authentication failed for user postgres"), cfg
    )
    assert code2 == "DB_AUTH_FAILED"
    assert "ULTRON_DATABASE_URL" in msg2

    bracket_cfg = Settings(
        ULTRON_ENV="production",
        VERCEL="1",
        VERCEL_ENV="preview",
        ULTRON_JWT_SECRET=_PROD_JWT,
        ULTRON_VAULT_MASTER_KEY=_PROD_VAULT,
        ULTRON_DATABASE_URL="postgresql://postgres.projref:[ActualPass123]@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    )
    assert bracket_cfg.database_diagnostics()["password_wrapped_in_brackets"] is True
    code3, msg3 = db_session.classify_database_error(
        Exception("FATAL: password authentication failed for user postgres.projref"), bracket_cfg
    )
    assert code3 == "DB_AUTH_FAILED"
    assert "brackets" in msg3
    assert "ActualPass123" not in msg3

    code_cb, msg_cb = db_session.classify_database_error(
        Exception("FATAL: (ECIRCUITBREAKER) too many authentication failures, new connections are temporarily blocked"), cfg
    )
    assert code_cb == "DB_CIRCUIT_BREAKER"
    assert "circuit breaker tripped" in msg_cb.lower()

    # Verify circuit-breaker storm backoff
    db_session.clear_auth_failure()
    assert db_session.get_active_auth_backoff() is None
    db_session.record_auth_failure("DB_CIRCUIT_BREAKER", msg_cb)
    active = db_session.get_active_auth_backoff()
    assert active is not None
    assert active[0] == "DB_CIRCUIT_BREAKER"
    db_session.clear_auth_failure()
    assert db_session.get_active_auth_backoff() is None


def test_unencoded_pg_password_chars_and_placeholder_detection() -> None:
    import psycopg.conninfo

    # Unencoded @, #, /, ?, and bare % are safely percent-encoded without breaking host parsing
    raw_special = (
        "postgresql://postgres.projref:My@Pass#12/34?50%@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    )
    norm_special = normalize_database_url(raw_special, allow_sqlite=False, is_vercel=True)
    ci = psycopg.conninfo.conninfo_to_dict(norm_special.replace("postgresql+psycopg://", "postgresql://", 1))
    assert ci["host"] == "aws-0-us-east-1.pooler.supabase.com"
    assert ci["port"] == "6543"
    assert ci["password"] == "My@Pass#12/34?50%"

    # Already-encoded %40%23 is NOT double-encoded
    raw_encoded = (
        "postgresql://postgres.projref:Already%40Encoded%231@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    )
    norm_encoded = normalize_database_url(raw_encoded, allow_sqlite=False, is_vercel=True)
    ci_enc = psycopg.conninfo.conninfo_to_dict(norm_encoded.replace("postgresql+psycopg://", "postgresql://", 1))
    assert ci_enc["password"] == "Already@Encoded#1"

    # Literal Supabase placeholder rejected immediately
    for placeholder in ("[YOUR-PASSWORD]", "your-password", "[database-password]", "<password>"):
        with pytest.raises(DatabaseConfigurationError, match="YOUR-PASSWORD"):
            normalize_database_url(
                f"postgresql://postgres.projref:{placeholder}@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
                allow_sqlite=False,
                is_vercel=True,
            )


def test_pulse_page_data_binding_uses_concrete_page_id(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/pulse/pages",
        headers=auth_headers["operator"],
        json={"title": "Live Ops Telemetry", "page_type": "AGENTS"},
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()
    assert page["page_id"].startswith("pls_")
    assert page["data_bindings"] == [f"/api/v1/pulse/pages/{page['page_id']}/live"]
    assert "{page_id}" not in page["data_bindings"][0]




def test_database_url_aliases_and_supabase_derivation() -> None:
    """Verify DATABASE_URL and POSTGRES_URL are loaded seamlessly and Supabase project URL is auto-derived."""
    from app.core.config import Settings
    from app.integrations.supabase import SupabaseClient

    # 1. DATABASE_URL alias loads into database_url
    s1 = Settings(
        ULTRON_ENV="staging",
        ULTRON_JWT_SECRET="x" * 40,
        ULTRON_VAULT_MASTER_KEY="y" * 40,
        DATABASE_URL="postgresql://postgres.myprojectref:secret@aws-0-eu-central-1.pooler.supabase.com:6543/postgres",
    )
    assert s1.database_url.startswith("postgresql://")
    assert SupabaseClient(s1).base_url == "https://myprojectref.supabase.co"

    # 2. POSTGRES_URL alias loads into database_url
    s2 = Settings(
        ULTRON_ENV="staging",
        ULTRON_JWT_SECRET="x" * 40,
        ULTRON_VAULT_MASTER_KEY="y" * 40,
        POSTGRES_URL="postgresql://postgres:secret@db.directref.supabase.co:5432/postgres",
    )
    assert s2.database_url.startswith("postgresql://")
    assert SupabaseClient(s2).base_url == "https://directref.supabase.co"
