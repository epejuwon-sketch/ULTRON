#!/usr/bin/env python3
"""Verify SQLAlchemy schema completeness and Supabase SQL migration files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import inspect

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import MIGRATION_REGISTRY, get_applied_migrations, get_engine, init_database  # noqa: E402


def main() -> int:
    settings = get_settings()
    init_database(settings)
    engine = get_engine(settings)
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = sorted(expected_tables - existing_tables)

    mig_dir = _BACKEND_DIR / "migrations" / "supabase"
    sql_files = []
    for ver, filename in MIGRATION_REGISTRY:
        p = mig_dir / filename
        sql_files.append(
            {
                "version": ver,
                "file": filename,
                "exists": p.exists(),
                "bytes": p.stat().st_size if p.exists() else 0,
            }
        )

    report = {
        "database_backend": settings.database_backend,
        "expected_table_count": len(expected_tables),
        "existing_table_count": len(existing_tables),
        "missing_tables": missing_tables,
        "schema_valid": len(missing_tables) == 0 and all(f["exists"] for f in sql_files),
        "supabase_migrations": sql_files,
        "applied_migrations": get_applied_migrations(settings),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
