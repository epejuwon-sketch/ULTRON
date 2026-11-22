"""Database engine management supporting Supabase PostgreSQL (pooled/serverless) and local SQLite WAL."""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseConfigurationError, DatabaseUnavailableError
from app.core.logging import redact_secrets
from app.db.models import Base, SchemaMigration, Tenant

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_ENGINE_URL: str | None = None
_INITIALIZED_ENGINE_URLS: set[str] = set()

MIGRATION_REGISTRY: list[tuple[str, str]] = [
    ("001", "001_initial_schema.sql"),
    ("002", "002_full_backend_schema.sql"),
    ("003", "003_ecosystem_and_devices.sql"),
    ("004", "004_full_platform_features.sql"),
]


def _is_supabase_pooler_url(url: str, raw_url: str = "") -> bool:
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    raw_lower = raw_url.lower()
    return (
        parsed.port == 6543
        or "pooler.supabase" in host
        or "pgbouncer=" in raw_lower
        or "supa=" in raw_lower
    )


def classify_database_error(exc: Exception, settings: Settings) -> tuple[str, str]:
    """Return a non-secret `(error_code, redacted_diagnostic_detail)` tuple for runtime DB failures."""
    if isinstance(exc, DatabaseConfigurationError):
        return exc.code, exc.message

    raw_msg = redact_secrets(str(exc))
    lower = raw_msg.lower()
    diag = settings.database_diagnostics()

    if "invalid uri query parameter" in lower:
        return (
            "DB_INVALID_URI_PARAM",
            f"Unsupported query parameter in ULTRON_DATABASE_URL ({raw_msg[:220]}).",
        )
    if (
        "network is unreachable" in lower
        or "cannot assign requested address" in lower
        or "could not translate host name" in lower
        or "name or service not known" in lower
    ):
        if diag.get("port") == 5432 and not diag.get("uses_pooler"):
            return (
                "DB_IPV6_DIRECT_PORT_5432",
                "Cannot reach Supabase direct database host on port 5432 from IPv4 serverless runtime. "
                "Update ULTRON_DATABASE_URL to the Supabase Transaction Pooler URI (port 6543, *.pooler.supabase.com).",
            )
        return (
            "DB_HOST_UNREACHABLE",
            "PostgreSQL host is unreachable from this runtime. Verify ULTRON_DATABASE_URL uses the Supabase "
            "Transaction Pooler host (*.pooler.supabase.com:6543) and that the Supabase project is active.",
        )
    if "tenant or user not found" in lower:
        return (
            "DB_POOLER_TENANT_USER_NOT_FOUND",
            "Supabase Transaction Pooler rejected the username. Ensure ULTRON_DATABASE_URL uses the pooled "
            "username format `postgres.<project-ref>` copied from Supabase -> Connect -> Transaction Pooler.",
        )
    if "password authentication failed" in lower or "authentication failed" in lower:
        return (
            "DB_AUTH_FAILED",
            "PostgreSQL authentication failed. Verify the database password in ULTRON_DATABASE_URL "
            "(URL-encode special characters like @, #, %, / if present).",
        )
    if "timeout" in lower or "timed out" in lower or "connection refused" in lower:
        return (
            "DB_CONNECTION_TIMEOUT",
            "PostgreSQL connection timed out or was refused. Confirm the Supabase project is not paused "
            "and ULTRON_DATABASE_URL uses the Transaction Pooler (port 6543) with SSL.",
        )
    if "ssl" in lower and ("required" in lower or "certificate" in lower or "handshake" in lower):
        return (
            "DB_SSL_ERROR",
            f"PostgreSQL SSL/TLS negotiation failed ({raw_msg[:220]}). Ensure sslmode=require is enabled.",
        )
    return (
        "DB_CONNECTION_FAILED",
        f"Database connection failed ({type(exc).__name__}): {raw_msg[:240]}",
    )


def _build_engine(settings: Settings) -> Engine:
    url = settings.effective_database_url
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}

    if url.startswith("sqlite"):
        if settings.is_deployed_environment:
            raise DatabaseConfigurationError(
                "Refusing to initialize SQLite in a deployed environment. "
                "Configure ULTRON_DATABASE_URL with a Supabase PostgreSQL connection string.",
                details={
                    "env": settings.ultron_env,
                    "vercel": settings.is_vercel,
                    "required_env_var": "ULTRON_DATABASE_URL",
                },
            )
        if url.startswith("sqlite:///"):
            db_file = url.removeprefix("sqlite:///")
            if db_file and db_file != ":memory:":
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
    else:
        parsed = make_url(url)
        connect_args: dict[str, Any] = {"connect_timeout": 10}
        if "psycopg" in (parsed.drivername or "").lower() and (
            settings.is_vercel or _is_supabase_pooler_url(url, settings.database_url)
        ):
            # Disable psycopg v3 automatic server-side prepared statements for
            # PgBouncer / Supabase Supavisor transaction pooler compatibility.
            connect_args["prepare_threshold"] = None
        kwargs["connect_args"] = connect_args

        if settings.is_vercel:
            # Delegate connection pooling to Supabase's pooler in ephemeral serverless functions.
            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_size"] = settings.db_pool_size
            kwargs["max_overflow"] = settings.db_max_overflow
            kwargs["pool_recycle"] = 1800

    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.close()

    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    global _ENGINE, _SESSION_FACTORY, _ENGINE_URL
    cfg = settings or get_settings()
    url = cfg.effective_database_url
    if _ENGINE is None or _ENGINE_URL != url:
        if _ENGINE is not None:
            _ENGINE.dispose()
        _ENGINE = _build_engine(cfg)
        _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False, expire_on_commit=False)
        _ENGINE_URL = url
    return _ENGINE


def reset_engine() -> None:
    """Dispose cached engine/sessionmaker (used in test isolation)."""
    global _ENGINE, _SESSION_FACTORY, _ENGINE_URL
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
    _ENGINE_URL = None
    _INITIALIZED_ENGINE_URLS.clear()


def _record_schema_migrations(db: Session) -> None:
    mig_dir = Path(__file__).resolve().parents[2] / "migrations" / "supabase"
    for ver, filename in MIGRATION_REGISTRY:
        if db.get(SchemaMigration, ver) is not None:
            continue
        file_path = mig_dir / filename
        content = file_path.read_bytes() if file_path.exists() else filename.encode("utf-8")
        checksum = hashlib.sha256(content).hexdigest()
        db.add(SchemaMigration(version=ver, name=filename, checksum=checksum))
    db.flush()


def init_database(settings: Settings | None = None) -> None:
    """Non-destructively ensure schema tables exist, record migration versions, and seed default tenant + 60 agents."""
    cfg = settings or get_settings()
    url = cfg.effective_database_url
    engine = get_engine(cfg)

    if cfg.auto_init_schema:
        # Strictly non-destructive (CREATE TABLE IF NOT EXISTS); never drops or alters existing tables.
        Base.metadata.create_all(bind=engine, checkfirst=True)

    from app.services.agent_catalog import seed_agent_catalog

    with get_session_factory(cfg)() as db:
        try:
            _record_schema_migrations(db)
            tenant = db.get(Tenant, cfg.default_tenant_id)
            if tenant is None:
                db.add(Tenant(tenant_id=cfg.default_tenant_id, name="ULTRON OS Primary Organization"))
                db.flush()
            seed_agent_catalog(db)
            db.commit()
        except IntegrityError:
            # Tolerate concurrent cold-start seeding races in serverless environments.
            db.rollback()

    _INITIALIZED_ENGINE_URLS.add(url)


def ensure_database_initialized(settings: Settings | None = None) -> None:
    """Ensure the active database engine has been initialized at least once in this process."""
    cfg = settings or get_settings()
    url = cfg.effective_database_url
    if url not in _INITIALIZED_ENGINE_URLS:
        init_database(cfg)


def get_applied_migrations(settings: Settings | None = None) -> list[dict]:
    cfg = settings or get_settings()
    with get_session_factory(cfg)() as db:
        rows = db.execute(select(SchemaMigration).order_by(SchemaMigration.version.asc())).scalars().all()
        return [
            {
                "version": r.version,
                "name": r.name,
                "checksum": r.checksum,
                "applied_at": r.applied_at.isoformat(),
            }
            for r in rows
        ]


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_engine(settings)
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""
    cfg = get_settings()
    try:
        ensure_database_initialized(cfg)
        factory = get_session_factory(cfg)
    except DatabaseConfigurationError:
        raise
    except SQLAlchemyError as exc:
        err_code, detail = classify_database_error(exc, cfg)
        raise DatabaseUnavailableError(
            detail,
            details={
                "error_code": err_code,
                **cfg.database_diagnostics(),
            },
        ) from exc
    db = factory()
    try:
        yield db
    finally:
        db.close()


def check_database_health_detailed(settings: Settings | None = None) -> dict[str, Any]:
    """Execute a lightweight connectivity probe and return structured non-secret diagnostics."""
    cfg = settings or get_settings()
    diag = cfg.database_diagnostics()
    try:
        engine = get_engine(cfg)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "healthy": True,
            "backend": cfg.database_backend,
            "error_code": None,
            "detail": "ok",
            **diag,
        }
    except Exception as exc:
        err_code, detail = classify_database_error(exc, cfg)
        return {
            "healthy": False,
            "backend": cfg.database_backend,
            "error_code": err_code,
            "detail": detail,
            **diag,
        }


def check_database_health(settings: Settings | None = None) -> tuple[bool, str]:
    """Execute a lightweight connectivity probe against the configured database."""
    report = check_database_health_detailed(settings)
    return bool(report["healthy"]), str(report["detail"])
