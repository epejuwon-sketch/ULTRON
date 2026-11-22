"""Database engine management supporting Supabase PostgreSQL (pooled/serverless) and local SQLite WAL."""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseConfigurationError
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


def _is_supabase_pooler_url(url: str) -> bool:
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    return parsed.port == 6543 or "pooler.supabase" in host


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
            settings.is_vercel or _is_supabase_pooler_url(url)
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
    ensure_database_initialized(cfg)
    factory = get_session_factory(cfg)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def check_database_health(settings: Settings | None = None) -> tuple[bool, str]:
    """Execute a lightweight connectivity probe against the configured database."""
    try:
        engine = get_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except DatabaseConfigurationError as exc:
        return False, exc.message
    except Exception as exc:
        return False, redact_secrets(str(exc))
