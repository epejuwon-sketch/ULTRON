"""Persistent background job queue and recurring job scheduler for dedicated worker deployment.

Production guarantees:
- Idempotent job enqueueing (prevents duplicate execution of identical active jobs).
- Bounded exponential backoff retries (`min(600, 15 * 2^(attempts-1))`).
- Dead-Letter Queue (`DEAD_LETTER`) after exhausting `max_attempts`, with operator requeue & cancel.
- Strict non-bypassable ApprovalGate enforcement: worker retries NEVER bypass PENDING/REJECTED approvals.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal, Role
from app.db.models import ApprovalRecord, BackgroundJobRecord, ScheduledJobRecord, TaskRecord
from app.db.repositories import append_audit_log
from app.services.argon_orchestrator import execute_task
from app.services.memory_service import prune_expired_memories

MAX_BACKOFF_SECONDS = 600


def compute_backoff_seconds(attempt: int, base_seconds: int = 15) -> int:
    """Bounded exponential backoff: 15s, 30s, 60s, 120s, 240s, capped at 600s."""
    return min(MAX_BACKOFF_SECONDS, base_seconds * (2 ** max(0, attempt - 1)))


def enqueue_background_job(
    db: Session,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 0,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    clean_type = job_type.strip().upper()
    enriched_payload = dict(payload)
    if idempotency_key:
        enriched_payload["_idempotency_key"] = idempotency_key.strip()
        # Idempotency deduplication across active/completed jobs in the same tenant
        existing = db.execute(
            select(BackgroundJobRecord)
            .where(
                BackgroundJobRecord.tenant_id == tenant_id,
                BackgroundJobRecord.job_type == clean_type,
                BackgroundJobRecord.status.in_(["QUEUED", "RETRYING", "RUNNING", "COMPLETED"]),
            )
            .order_by(BackgroundJobRecord.created_at.desc())
            .limit(50)
        ).scalars().all()
        for row in existing:
            try:
                p = json.loads(row.payload_json or "{}")
                if p.get("_idempotency_key") == idempotency_key.strip():
                    out = _serialize_job(row)
                    out["idempotent_replay"] = True
                    return out
            except Exception:
                continue

    run_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))
    job = BackgroundJobRecord(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        job_type=clean_type,
        payload_json=json.dumps(enriched_payload, default=str),
        status="QUEUED",
        attempts=0,
        max_attempts=max(1, min(10, int(max_attempts))),
        scheduled_for=run_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def cancel_background_job(db: Session, *, principal: Principal, job_id: str) -> dict[str, Any]:
    job = db.execute(
        select(BackgroundJobRecord).where(
            BackgroundJobRecord.job_id == job_id,
            BackgroundJobRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError(f"Background job '{job_id}' not found.")
    if job.status in {"COMPLETED", "CANCELLED"}:
        raise ConflictError(f"Background job '{job_id}' is already {job.status}.")
    job.status = "CANCELLED"
    job.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ARGON_JOB_CANCELLED",
        resource=job.job_id,
        outcome="CANCELLED",
    )
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def requeue_dead_letter_job(db: Session, *, principal: Principal, job_id: str) -> dict[str, Any]:
    """Requeue a DEAD_LETTER or FAILED job for clean retry after operator remediation."""
    job = db.execute(
        select(BackgroundJobRecord).where(
            BackgroundJobRecord.job_id == job_id,
            BackgroundJobRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError(f"Background job '{job_id}' not found.")
    if job.status not in {"DEAD_LETTER", "FAILED", "CANCELLED"}:
        raise ConflictError(f"Only DEAD_LETTER, FAILED, or CANCELLED jobs can be requeued (current={job.status}).")
    job.status = "QUEUED"
    job.attempts = 0
    job.error_detail = None
    job.scheduled_for = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ARGON_JOB_REQUEUED",
        resource=job.job_id,
        outcome="QUEUED",
    )
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


def _assert_task_approval_not_bypassed(db: Session, tenant_id: str, task_id: str) -> None:
    """Hard governance guard inside the worker: unapproved or rejected tasks MUST NEVER execute."""
    task = db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' not found.")
    if task.lifecycle_state in {"WAITING_FOR_APPROVAL", "REJECTED", "CANCELLED"}:
        raise PermissionError(
            f"ApprovalGate non-bypass violation: task '{task_id}' is in state '{task.lifecycle_state}' and cannot execute in worker."
        )
    approvals = db.execute(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.task_id == task_id,
        )
    ).scalars().all()
    for approval in approvals:
        if approval.status != "APPROVED":
            raise PermissionError(
                f"ApprovalGate non-bypass violation: approval '{approval.approval_id}' is '{approval.status}', not APPROVED."
            )


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

    # 2. Process queued/retrying background jobs
    jobs = db.execute(
        select(BackgroundJobRecord)
        .where(BackgroundJobRecord.status.in_(["QUEUED", "RETRYING"]))
        .order_by(BackgroundJobRecord.scheduled_for.asc())
        .limit(max_jobs)
    ).scalars().all()

    processed = 0
    succeeded = 0
    failed = 0
    dead_lettered = 0
    approval_blocked = 0

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
                task_id = str(payload["task_id"])
                _assert_task_approval_not_bypassed(db, job.tenant_id, task_id)
                result = execute_task(
                    db,
                    principal=worker_principal,
                    task_id=task_id,
                    settings=settings,
                )
            elif job.job_type == "PRUNE_MEMORY":
                removed = prune_expired_memories(db, principal=worker_principal)
                result = {"pruned_count": removed}
            elif job.job_type == "CARAVAN_DISCOVERY_SWEEP":
                from app.services.caravan_discovery_service import run_caravan_discovery_sweep

                result = run_caravan_discovery_sweep(db, principal=worker_principal)
            elif job.job_type == "CARAVAN_DEADLINE_SWEEP":
                from app.services.caravan_product_service import (
                    send_approaching_deadline_reminders,
                    sweep_expired_opportunities,
                )

                exp = sweep_expired_opportunities(db, principal=worker_principal)
                rem = send_approaching_deadline_reminders(db, principal=worker_principal)
                result = {"expired_sweep": exp, "deadline_reminders": rem}
            elif job.job_type == "CARAVAN_NOTIFICATION_DISPATCH":
                from app.services.caravan_phase7_service import dispatch_pending_notifications

                result = dispatch_pending_notifications(db, tenant_id=job.tenant_id)
            elif job.job_type == "CARAVAN_SUBSCRIPTION_LIFECYCLE":
                from app.services.caravan_phase7_service import run_subscription_lifecycle_sweep

                result = run_subscription_lifecycle_sweep(db, tenant_id=job.tenant_id)
            elif job.job_type == "FAIL_TEST_JOB":
                raise RuntimeError(str(payload.get("reason", "Simulated worker failure for DLQ testing")))
            else:
                result = {"handled": True, "job_type": job.job_type, "payload": payload}

            job.status = "COMPLETED"
            job.result_json = json.dumps(result, default=str)
            job.error_detail = None
            job.updated_at = datetime.now(timezone.utc)
            succeeded += 1
        except PermissionError as exc:
            # Non-bypassable ApprovalGate block -> move directly to DEAD_LETTER without retry bypass
            job.status = "DEAD_LETTER"
            job.error_detail = str(exc)
            job.updated_at = datetime.now(timezone.utc)
            approval_blocked += 1
            dead_lettered += 1
            failed += 1
            append_audit_log(
                db,
                tenant_id=job.tenant_id,
                actor="ultron-worker",
                action="ARGON_WORKER_APPROVAL_BLOCKED",
                resource=job.job_id,
                outcome=str(exc)[:200],
            )
        except Exception as exc:
            job.error_detail = str(exc)
            if job.attempts < job.max_attempts:
                backoff = compute_backoff_seconds(job.attempts)
                job.status = "RETRYING"
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            else:
                job.status = "DEAD_LETTER"
                dead_lettered += 1
                append_audit_log(
                    db,
                    tenant_id=job.tenant_id,
                    actor="ultron-worker",
                    action="ARGON_JOB_DEAD_LETTERED",
                    resource=job.job_id,
                    outcome=f"attempts={job.attempts}|err={str(exc)[:140]}",
                )
            job.updated_at = datetime.now(timezone.utc)
            failed += 1
        db.commit()

    try:
        from app.db.models import WorkerHeartbeatRecord

        hb = db.get(WorkerHeartbeatRecord, "ultron-primary-worker")
        if hb is None:
            hb = WorkerHeartbeatRecord(
                worker_id="ultron-primary-worker",
                status="ALIVE",
                last_poll_at=datetime.now(timezone.utc),
                jobs_processed=processed,
                jobs_failed=failed,
                detail=f"succeeded={succeeded},dead_lettered={dead_lettered}",
            )
            db.add(hb)
        else:
            hb.status = "ALIVE"
            hb.last_poll_at = datetime.now(timezone.utc)
            hb.jobs_processed += processed
            hb.jobs_failed += failed
            hb.detail = f"last_poll_succeeded={succeeded},dead_lettered={dead_lettered}"
        db.commit()
    except Exception:
        db.rollback()

    return {
        "enqueued_from_schedules": enqueued_from_schedules,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "dead_lettered": dead_lettered,
        "approval_blocked": approval_blocked,
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


# Backwards-compatible alias for persistent worker polling
run_worker_poll_once = process_due_jobs

