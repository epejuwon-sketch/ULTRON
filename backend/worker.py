"""Persistent background worker runner for ULTRON OS & CARAVAN scheduled operations.

Run from backend/:
    python -m worker
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend directory is in sys.path when executed directly
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory, init_database
from app.services.job_scheduler import process_due_jobs, run_worker_poll_once

_STOP = False


def _handle_signal(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def run_once() -> dict[str, Any]:
    """Execute a single polling and processing cycle (used for CI and smoke checks)."""
    settings = get_settings()
    logger = configure_logging(settings.log_level)
    init_database(settings)
    session_factory = get_session_factory(settings)
    with session_factory() as db:
        summary = run_worker_poll_once(db, settings=settings, max_jobs=25)
        logger.info("Worker single cycle completed: %s", summary)
        return summary


def run_forever(poll_interval_seconds: float = 5.0) -> None:
    settings = get_settings()
    logger = configure_logging(settings.log_level)
    init_database(settings)
    session_factory = get_session_factory(settings)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("ULTRON/CARAVAN persistent worker started (poll_interval=%.1fs)", poll_interval_seconds)
    while not _STOP:
        db = session_factory()
        try:
            summary = run_worker_poll_once(db, settings=settings, max_jobs=25)
            if summary["processed"] > 0 or summary["enqueued_from_schedules"] > 0:
                logger.info("Worker poll summary: %s", summary)
        except Exception as exc:
            logger.error("Worker poll error: %s", exc)
        finally:
            db.close()

        slept = 0.0
        while not _STOP and slept < poll_interval_seconds:
            time.sleep(min(0.5, poll_interval_seconds - slept))
            slept += 0.5
    logger.info("ULTRON/CARAVAN persistent worker stopped cleanly.")


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
        sys.exit(0)
    interval = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "--once" else 5.0
    run_forever(interval)

