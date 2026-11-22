"""Database engine management supporting Supabase PostgreSQL and SQLite WAL."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import Base, Tenant

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_ENGINE_URL: str | None = None


def _build_engine(settings: Settings) -> Engine:
    url = settings.effective_database_url
    connect_args: dict = {}
    if url.startswith("sqlite:///"):
        db_file = url.removeprefix("sqlite:///")
        if db_file != ":memory:":
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False, "timeout": 30.0}

    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)

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


def init_database(settings: Settings | None = None) -> None:
    """Create schema tables and seed default tenant + 60-agent catalog idempotently."""
    cfg = settings or get_settings()
    engine = get_engine(cfg)
    Base.metadata.create_all(bind=engine)

    # Seed default tenant and 60 specialist agents idempotently
    from app.services.agent_catalog import seed_agent_catalog

    with get_session_factory(cfg)() as db:
        tenant = db.get(Tenant, cfg.default_tenant_id)
        if tenant is None:
            db.add(Tenant(tenant_id=cfg.default_tenant_id, name="ULTRON OS Primary Organization"))
            db.flush()
        seed_agent_catalog(db)
        db.commit()


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_engine(settings)
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""
    factory = get_session_factory()
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
    except Exception as exc:
        return False, str(exc)
