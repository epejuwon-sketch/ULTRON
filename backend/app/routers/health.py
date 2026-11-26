"""Health, readiness, and honest external integration verification routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import check_database_health_detailed, get_db
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
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return unified integration status combining static config and VAULT OAuth/API-key records."""
    from app.services.integration_manager import list_connections

    static = IntegrationRegistry(settings).get_static_status()
    managed = list_connections(db, tenant_id=principal.tenant_id, settings=settings)
    by_provider = {c["provider"]: c for c in managed.get("connections", [])}

    caps = static.get("capabilities", {})
    mapping = {
        "google_drive": "google_drive",
        "github": "github",
        "google_calendar": "calendar",
        "google_gmail": "email",
    }
    for provider_key, cap_key in mapping.items():
        rec = by_provider.get(provider_key)
        if rec and rec.get("connection_id") and not rec.get("disconnected_at"):
            caps[cap_key] = {
                **caps.get(cap_key, {}),
                "provider": provider_key,
                "configured": True,
                "live_verified": rec.get("status") == "AVAILABLE",
                "capability_state": rec.get("status", "IMPLEMENTED_NOT_LIVE"),
                "detail": (
                    f"Connected via {rec.get('auth_type', 'OAUTH2')}"
                    + (f" ({rec['account_label']})" if rec.get("account_label") else "")
                ),
                "missing_env_vars": [],
            }
    return static


@router.post("/api/v1/integrations/verify")
def integrations_verify_live(
    timeout_seconds: float = Query(default=8.0, ge=1.0, le=20.0),
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Run live outbound connectivity checks against configured providers and active VAULT OAuth connections."""
    from app.services.integration_manager import list_connections, verify_provider_live

    report = IntegrationRegistry(settings).verify_all_live(timeout_seconds=timeout_seconds)
    managed = list_connections(db, tenant_id=principal.tenant_id, settings=settings)
    for rec in managed.get("connections", []):
        if rec.get("connection_id") and not rec.get("disconnected_at"):
            try:
                v = verify_provider_live(db, principal=principal, provider=rec["provider"], settings=settings)
                if rec["provider"] in report.get("capabilities", {}):
                    report["capabilities"][rec["provider"]] = v
            except Exception:
                pass
    return report
