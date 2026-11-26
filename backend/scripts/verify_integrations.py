#!/usr/bin/env python3
"""Honest live integration verifier CLI for ULTRON OS 2026.

Inspects configured environment variables, runs real live probes against configured
cloud/API providers, and audits official connected Antigravity plugin CLIs.
Never fabricates passing results when credentials are missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.session import check_database_health, init_database  # noqa: E402
from app.integrations.antigravity import inspect_antigravity_environment  # noqa: E402
from app.integrations.registry import IntegrationRegistry  # noqa: E402


def main() -> int:
    settings = get_settings()
    init_database(settings)
    db_ok, db_detail = check_database_health(settings)
    report = {
        "environment": settings.ultron_env,
        "gemini_models_configured": {
            "fast": settings.gemini_model_fast,
            "standard": settings.gemini_model_standard,
            "reasoning": settings.gemini_model_reasoning,
            "embedding": settings.gemini_model_embedding,
            "image": settings.gemini_model_image,
        },
        "database": {
            "backend": settings.database_backend,
            "healthy": db_ok,
            "detail": db_detail,
        },
        "integrations": IntegrationRegistry(settings).verify_all_live(),
        "antigravity_plugins": inspect_antigravity_environment(run_live_auth_checks=True),
    }
    print(json.dumps(report, indent=2))
    return 0 if db_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
