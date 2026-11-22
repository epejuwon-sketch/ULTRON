"""Persistent background job queue and recurring job scheduler (designed for dedicated worker deployment outside Vercel serverless limits)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.db.models import BackgroundJobRecord, ScheduledJobRecord
from app.db.repositories import append_audit_log
from app.services.argon_orchestrator import execute_task
from app.services.memory_service import prune_expired_memories


def enqueue_background_job(
    db: Session,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 0,
) -> dict[str, Any]:
    run_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))
    job = BackgroundJobRecord(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        job_type=job_type.strip().upper(),
        payload_json=json.dumps(payload, default=str),
        status="QUEUED",
        attempts=0,
        max_attempts=max(1, min(10, int(max_attempts))),
        scheduled_for=run_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def list_background_jobs(
    db: Session,
    *,
    tenant_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(BackgroundJobRecord).where(BackgroundJobRecord.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(BackgroundJobRecord.status == status.upper())
    rows = db.execute(stmt.order_by(BackgroundJobRecord.created_at.desc()).limit(limit)).scalars().all()
    return [_serialize_job(r) for r in rows]


def create_scheduled_job(
    db: Session,
    *,
    principal: Principal,
    name: str,
    job_type: str,
    interval_seconds: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    sched = ScheduledJobRecord(
        schedule_id=f"sch_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        name=name.strip(),
        job_type=job_type.strip().upper(),
        interval_seconds=max(60, int(interval_seconds)),
        payload_json=json.dumps(payload or {}, default=str),
        enabled=True,
        next_run_at=now + timedelta(seconds=max(60, int(interval_seconds))),
        created_by=principal.username,
    )
    db.add(sched)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SCHEDULE_CREATED",
        resource=sched.schedule_id,
        outcome=f"{sched.job_type}|INTERVAL={sched.interval_seconds}s",
    )
    db.commit()
    db.refresh(sched)
    return _serialize_schedule(sched)


def list_scheduled_jobs(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ScheduledJobRecord)
        .where(ScheduledJobRecord.tenant_id == tenant_id)
        .order_by(ScheduledJobRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_schedule(r) for r in rows]


def process_due_jobs(db: Session, *, settings: Settings, max_jobs: int = 10) -> dict[str, Any]:
    """Poll due scheduled jobs, enqueue them, and execute up to `max_jobs` queued background jobs."""
    now = datetime.now(timezone.utc)

    # 1. Enqueue due recurring schedules
    schedules = db.execute(
        select(ScheduledJobRecord).where(ScheduledJobRecord.enabled.is_(True))
    ).scalars().all()
    enqueued_from_schedules = 0
    for sched in schedules:
        nxt = sched.next_run_at if sched.next_run_at.tzinfo else sched.next_run_at.replace(tzinfo=timezone.utc)
        if now >= nxt:
            enqueue_background_job(
                db,
                tenant_id=sched.tenant_id,
                job_type=sched.job_type,
                payload=json.loads(sched.payload_json or "{}"),
            )
            sched.last_run_at = now
            sched.next_run_at = now + timedelta(seconds=sched.interval_seconds)
            enqueued_from_schedules += 1
    db.commit()

    # 2. Process queued background jobs
    jobs = db.execute(
        select(BackgroundJobRecord)
        .where(BackgroundJobRecord.status.in_(["QUEUED", "RETRYING"]))
        .order_by(BackgroundJobRecord.scheduled_for.asc())
        .limit(max_jobs)
    ).scalars().all()

    processed = 0
    succeeded = 0
    failed = 0

    for job in jobs:
        due = job.scheduled_for if job.scheduled_for.tzinfo else job.scheduled_for.replace(tzinfo=timezone.utc)
        if now < due:
            continue
        processed += 1
        job.status = "RUNNING"
        job.attempts += 1
        job.updated_at = now
        db.commit()

        payload = json.loads(job.payload_json or "{}")
        worker_principal = Principal(
            user_id="worker_system",
            username="ultron-worker",
            role=Role.ADMIN,
            tenant_id=job.tenant_id,
            jti="worker-session",
        )
        try:
            if job.job_type == "EXECUTE_TASK":
                result = execute_task(
                    db,
                    principal=worker_principal,
                    task_id=str(payload["task_id"]),
                    settings=settings,
                )
            elif job.job_type == "PRUNE_MEMORY":
                removed = prune_expired_memories(db, principal=worker_principal)
                result = {"pruned_count": removed}
            else:
                result = {"handled": True, "job_type": job.job_type, "payload": payload}

            job.status = "COMPLETED"
            job.result_json = json.dumps(result, default=str)
            job.error_detail = None
            job.updated_at = datetime.now(timezone.utc)
            succeeded += 1
        except Exception as exc:
            job.error_detail = str(exc)
            if job.attempts < job.max_attempts:
                job.status = "RETRYING"
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=30 * job.attempts)
            else:
                job.status = "FAILED"
            job.updated_at = datetime.now(timezone.utc)
            failed += 1
        db.commit()

    return {
        "enqueued_from_schedules": enqueued_from_schedules,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
    }


def _serialize_job(j: BackgroundJobRecord) -> dict[str, Any]:
    return {
        "job_id": j.job_id,
        "tenant_id": j.tenant_id,
        "job_type": j.job_type,
        "status": j.status,
        "attempts": j.attempts,
        "max_attempts": j.max_attempts,
        "payload": json.loads(j.payload_json or "{}"),
        "result": json.loads(j.result_json or "{}"),
        "error_detail": j.error_detail,
        "scheduled_for": j.scheduled_for.isoformat(),
        "created_at": j.created_at.isoformat(),
    }


def _serialize_schedule(s: ScheduledJobRecord) -> dict[str, Any]:
    return {
        "schedule_id": s.schedule_id,
        "name": s.name,
        "job_type": s.job_type,
        "interval_seconds": s.interval_seconds,
        "enabled": s.enabled,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "next_run_at": s.next_run_at.isoformat(),
        "created_by": s.created_by,
    }
