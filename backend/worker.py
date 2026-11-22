#!/usr/bin/env python3
"""ULTRON OS 2026 — Dedicated Persistent Background Worker.

Runs long-lived ARGON DAG orchestrations and recurring scheduled jobs outside
Vercel's serverless execution timeout window. Deploy as a container (Fly.io,
Railway, Render, Cloud Run, or self-hosted Docker) connected to the same
Supabase PostgreSQL database (`ULTRON_DATABASE_URL`).
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.permissions import Principal, Role  # noqa: E402
from app.db.session import get_session_factory, init_database  # noqa: E402
from app.services.aegis_service import run_security_scan  # noqa: E402
from app.services.job_scheduler import process_due_jobs  # noqa: E402

_RUNNING = True


def _handle_stop(_signum: int, _frame) -> None:
    global _RUNNING
    _RUNNING = False


def run_worker(*, poll_interval_seconds: float = 5.0, aegis_interval_seconds: float = 60.0, once: bool = False) -> int:
    settings = get_settings()
    logger = configure_logging(settings.log_level)
    init_database(settings)

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info(
        "ULTRON OS 2026 persistent worker started (db=%s, poll=%.1fs, aegis=%.1fs, once=%s)",
        settings.database_backend,
        poll_interval_seconds,
        aegis_interval_seconds,
        once,
    )

    last_aegis_at = 0.0
    system_principal = Principal(
        user_id="system-worker",
        username="AEGIS_DAEMON",
        role=Role.OWNER,
        tenant_id=settings.default_tenant_id,
        jti="worker-daemon",
    )

    while _RUNNING:
        now_mono = time.monotonic()
        with get_session_factory(settings)() as db:
            summary = process_due_jobs(db, settings=settings, max_jobs=10)
            if summary["processed"] or summary["enqueued_from_schedules"]:
                logger.info("Worker cycle summary: %s", summary)
            if once or (now_mono - last_aegis_at >= aegis_interval_seconds):
                aegis_res = run_security_scan(db, principal=system_principal, settings=settings, scan_type="FAST")
                last_aegis_at = now_mono
                logger.info(
                    "AEGIS scan completed (scan_id=%s, risk_score=%s, findings=%s)",
                    aegis_res["scan"]["scan_id"],
                    aegis_res["scan"]["risk_score"],
                    aegis_res["scan"]["findings_count"],
                )
        if once:
            break
        time.sleep(poll_interval_seconds)

    logger.info("ULTRON OS 2026 persistent worker stopped cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ULTRON OS 2026 Persistent Background Worker")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between queue polls")
    parser.add_argument("--aegis-interval", type=float, default=60.0, help="Seconds between AEGIS scans")
    parser.add_argument("--once", action="store_true", help="Run a single poll & AEGIS scan cycle and exit")
    args = parser.parse_args()
    return run_worker(
        poll_interval_seconds=args.poll_interval,
        aegis_interval_seconds=args.aegis_interval,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
