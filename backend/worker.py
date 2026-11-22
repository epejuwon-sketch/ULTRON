#!/usr/bin/env python3
"""ULTRON OS 2026 — Dedicated Persistent Background Worker.

Designed for dedicated container deployment (Fly.io, Railway, Render, Cloud Run, Docker)
connected to Supabase PostgreSQL (`ULTRON_DATABASE_URL`) — cleanly separated from Vercel
serverless HTTP API functions.

Features:
- Reliable persistent ARGON job queue processing with bounded exponential backoff & DLQ.
- Concurrency control (`--max-jobs`, `--concurrency`).
- Continuous 60-second AEGIS autonomous security scans.
- Built-in HTTP health probe server (`--health-port 8081` -> `/health/live`, `/health/ready`).
- Graceful SIGINT/SIGTERM shutdown draining the active cycle cleanly.
"""

from __future__ import annotations

import argparse
import http.server
import json
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.permissions import Principal, Role  # noqa: E402
from app.db.session import check_database_health, get_session_factory, init_database  # noqa: E402
from app.services.aegis_service import run_security_scan  # noqa: E402
from app.services.job_scheduler import process_due_jobs  # noqa: E402

_RUNNING = True
_WORKER_STATE: dict = {
    "status": "STARTING",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "last_cycle_at": None,
    "cycles_completed": 0,
    "jobs_processed": 0,
    "last_aegis_risk_score": None,
}


def _handle_stop(_signum: int, _frame) -> None:
    global _RUNNING
    _RUNNING = False
    _WORKER_STATE["status"] = "SHUTTING_DOWN"


def _start_health_server(port: int, settings) -> http.server.ThreadingHTTPServer:
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/health/live":
                body = json.dumps({"status": "alive", "worker": _WORKER_STATE}).encode("utf-8")
                self.send_response(200)
            elif self.path in {"/health/ready", "/health"}:
                ok, detail = check_database_health(settings)
                code = 200 if ok and _RUNNING else 503
                body = json.dumps({"ready": ok and _RUNNING, "db": detail, "worker": _WORKER_STATE}).encode("utf-8")
                self.send_response(code)
            else:
                self.send_response(404)
                body = b'{"error":"not_found"}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def run_worker(
    *,
    poll_interval_seconds: float = 5.0,
    aegis_interval_seconds: float = 60.0,
    max_jobs_per_cycle: int = 10,
    health_port: int = 0,
    once: bool = False,
) -> int:
    global _RUNNING
    _RUNNING = True
    settings = get_settings()
    logger = configure_logging(settings.log_level)
    init_database(settings)

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    health_server = _start_health_server(health_port, settings) if health_port > 0 else None
    _WORKER_STATE["status"] = "RUNNING"

    logger.info(
        "ULTRON OS 2026 persistent worker started (db=%s, poll=%.1fs, aegis=%.1fs, max_jobs=%d, health_port=%d, once=%s)",
        settings.database_backend,
        poll_interval_seconds,
        aegis_interval_seconds,
        max_jobs_per_cycle,
        health_port,
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

    try:
        while _RUNNING:
            now_mono = time.monotonic()
            with get_session_factory(settings)() as db:
                summary = process_due_jobs(db, settings=settings, max_jobs=max_jobs_per_cycle)
                _WORKER_STATE["cycles_completed"] += 1
                _WORKER_STATE["jobs_processed"] += summary["processed"]
                _WORKER_STATE["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
                if summary["processed"] or summary["enqueued_from_schedules"]:
                    logger.info("Worker cycle summary: %s", summary)
                if once or (now_mono - last_aegis_at >= aegis_interval_seconds):
                    aegis_res = run_security_scan(db, principal=system_principal, settings=settings, scan_type="FAST")
                    last_aegis_at = now_mono
                    _WORKER_STATE["last_aegis_risk_score"] = aegis_res["scan"]["risk_score"]
                    logger.info(
                        "AEGIS scan completed (scan_id=%s, risk_score=%s, findings=%s)",
                        aegis_res["scan"]["scan_id"],
                        aegis_res["scan"]["risk_score"],
                        aegis_res["scan"]["findings_count"],
                    )
            if once:
                break
            time.sleep(poll_interval_seconds)
    finally:
        _WORKER_STATE["status"] = "STOPPED"
        if health_server is not None:
            health_server.shutdown()
            health_server.server_close()

    logger.info("ULTRON OS 2026 persistent worker stopped cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ULTRON OS 2026 Persistent Background Worker")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between queue polls")
    parser.add_argument("--aegis-interval", type=float, default=60.0, help="Seconds between AEGIS scans")
    parser.add_argument("--max-jobs", type=int, default=10, help="Maximum queued jobs drained per cycle")
    parser.add_argument("--health-port", type=int, default=0, help="Optional HTTP health probe port (e.g. 8081)")
    parser.add_argument("--once", action="store_true", help="Run a single poll & AEGIS scan cycle and exit")
    args = parser.parse_args()
    return run_worker(
        poll_interval_seconds=args.poll_interval,
        aegis_interval_seconds=args.aegis_interval,
        max_jobs_per_cycle=args.max_jobs,
        health_port=args.health_port,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
