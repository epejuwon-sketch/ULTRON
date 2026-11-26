"""TURBO Performance Profiling, Cache Management & Real Benchmarks API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.turbo_service import run_real_benchmarks, turbo_cache

router = APIRouter(prefix="/api/v1/turbo", tags=["TURBO Performance Engine"])


@router.get("/stats")
def api_turbo_stats(
    _principal: Principal = Depends(require_perm("turbo:read")),
) -> dict:
    return {"cache": turbo_cache.stats()}


@router.post("/cache/flush")
def api_turbo_flush(
    _principal: Principal = Depends(require_perm("turbo:manage")),
) -> dict:
    cleared = turbo_cache.clear()
    return {"cleared_entries": cleared, "cache": turbo_cache.stats()}


@router.post("/benchmarks")
def api_turbo_benchmarks(
    iterations: int = Query(default=25, ge=5, le=100),
    _principal: Principal = Depends(require_perm("turbo:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return run_real_benchmarks(db, settings=settings, iterations=iterations)
