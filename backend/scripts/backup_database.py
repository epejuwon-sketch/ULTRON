#!/usr/bin/env python3
"""Database backup utility for ULTRON OS 2026 (SQLite online backup & Postgres pg_dump guidance)."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a consistent database backup for ULTRON OS 2026.")
    parser.add_argument("--output-dir", default="./backups", help="Directory to store backup files")
    args = parser.parse_args()

    settings = get_settings()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if settings.database_backend == "sqlite":
        src = Path(settings.sqlite_path)
        if not src.exists():
            print(f"SQLite database not found at {src}", file=sys.stderr)
            return 1
        dest = out_dir / f"ultron_sqlite_{stamp}.db"
        with sqlite3.connect(str(src)) as src_conn, sqlite3.connect(str(dest)) as dst_conn:
            src_conn.backup(dst_conn)
        print(f"SQLite online backup created: {dest} ({dest.stat().st_size} bytes)")
        return 0

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("pg_dump binary not installed. Use Supabase Point-in-Time Recovery (PITR) or install postgresql-client.", file=sys.stderr)
        return 2
    dest = out_dir / f"ultron_postgres_{stamp}.sql"
    pg_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    subprocess.run([pg_dump, pg_url, "-f", str(dest)], check=True)
    print(f"PostgreSQL backup created: {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
