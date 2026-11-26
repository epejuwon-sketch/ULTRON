"""ARGON background job queue, DLQ management, recurring schedules, and worker poll control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import CreateScheduleRequest, EnqueueJobRequest
from app.services.job_scheduler import (
    cancel_background_job,
    create_scheduled_job,
    enqueue_background_job,
    list_background_jobs,
    list_scheduled_jobs,
    process_due_jobs,
    requeue_dead_letter_job,
)

router = APIRouter(prefix="/api/v1/argon", tags=["ARGON Queue & Scheduler"])


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def api_enqueue_job(
    body: EnqueueJobRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
) -> dict:
    return enqueue_background_job(
        db,
        tenant_id=principal.tenant_id,
        job_type=body.job_type,
        payload=body.payload,
        max_attempts=body.max_attempts,
        delay_seconds=body.delay_seconds,
        idempotency_key=idempotency_key,
    )


@router.get("/jobs")
def api_list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    principal: Principal = Depends(require_perm("tasks:read")),
    db: Session = Depends(get_db),
) -> dict:
    jobs = list_background_jobs(db, tenant_id=principal.tenant_id, status=status_filter)
    return {"total": len(jobs), "jobs": jobs}


@router.post("/jobs/{job_id}/cancel")
def api_cancel_job(
    job_id: str,
    principal: Principal = Depends(require_perm("tasks:cancel")),
    db: Session = Depends(get_db),
) -> dict:
    return cancel_background_job(db, principal=principal, job_id=job_id)


@router.post("/jobs/{job_id}/requeue")
def api_requeue_job(
    job_id: str,
    principal: Principal = Depends(require_perm("jobs:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return requeue_dead_letter_job(db, principal=principal, job_id=job_id)


@router.post("/jobs/process")
def api_process_due_jobs(
    max_jobs: int = Query(default=10, ge=1, le=50),
    _principal: Principal = Depends(require_perm("jobs:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Trigger one worker poll cycle (for Cron triggers or manual drainage)."""
    return process_due_jobs(db, settings=settings, max_jobs=max_jobs)


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
def api_create_schedule(
    body: CreateScheduleRequest,
    principal: Principal = Depends(require_perm("jobs:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return create_scheduled_job(
        db,
        principal=principal,
        name=body.name,
        job_type=body.job_type,
        interval_seconds=body.interval_seconds,
        payload=body.payload,
    )


@router.get("/schedules")
def api_list_schedules(
    principal: Principal = Depends(require_perm("tasks:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_scheduled_jobs(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "schedules": items}
