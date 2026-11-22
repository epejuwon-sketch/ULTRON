"""Health, readiness, and honest external integration verification routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import check_database_health_detailed
from app.integrations.registry import IntegrationRegistry
from app.routers.deps import require_perm

router = APIRouter(tags=["Health & Integrations"])


@router.get("/health/live")
def health_live(settings: Settings = Depends(get_settings)) -> dict:
    """Liveness probe (no external network dependencies)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "env": settings.ultron_env,
    }


@router.get("/health/ready")
def health_ready(settings: Settings = Depends(get_settings)) -> dict:
    """Readiness probe verifying active database connectivity and safe config summary."""
    db_report = check_database_health_detailed(settings)
    return {
        "status": "ready" if db_report["healthy"] else "degraded",
        "database": db_report,
        "config": settings.safe_summary(),
    }


@router.get("/health")
def health_root(settings: Settings = Depends(get_settings)) -> dict:
    """Combined health overview with honest static integration configuration state."""
    db_report = check_database_health_detailed(settings)
    integrations = IntegrationRegistry(settings).get_static_status()
    return {
        "status": "ok" if db_report["healthy"] else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": db_report,
        "integrations": integrations,
    }


@router.get("/api/v1/integrations/status")
def integrations_status(
    _principal: Principal = Depends(require_perm("integrations:verify")),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return honest configuration status for Supabase, Gemini, Vercel, and Cloudflare."""
    return IntegrationRegistry(settings).get_static_status()


@router.post("/api/v1/integrations/verify")
def integrations_verify_live(
    timeout_seconds: float = Query(default=8.0, ge=1.0, le=20.0),
    _principal: Principal = Depends(require_perm("integrations:verify")),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Run live outbound connectivity checks against all configured providers honestly."""
    return IntegrationRegistry(settings).verify_all_live(timeout_seconds=timeout_seconds)
