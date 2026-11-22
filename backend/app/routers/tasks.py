"""ARGON task orchestration, DAG planning, pause/resume/retry, idempotent creation, and execution routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.idempotency import compute_request_hash, lookup_idempotency, save_idempotency
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import CreateTaskRequest, TransitionTaskRequest
from app.services.argon_orchestrator import (
    create_and_plan_task,
    execute_task,
    get_task,
    list_tasks,
    pause_task,
    resume_task,
    retry_task,
    transition_task_state,
)
from app.services.job_scheduler import enqueue_background_job

router = APIRouter(prefix="/api/v1/tasks", tags=["ARGON Tasks & Orchestration"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def api_create_task(
    request: Request,
    body: CreateTaskRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_perm("tasks:create")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Create and plan a multi-agent DAG task with optional Idempotency-Key replay safety."""
    raw_body = await request.body()
    req_hash = compute_request_hash("POST", "/api/v1/tasks", raw_body)
    if idempotency_key and idempotency_key.strip():
        cached = lookup_idempotency(
            db,
            key=idempotency_key.strip(),
            tenant_id=principal.tenant_id,
            request_hash=req_hash,
        )
        if cached is not None:
            return JSONResponse(
                status_code=cached["status_code"],
                content=cached["body"],
                headers={"X-Idempotency-Replayed": "true"},
            )

    custom_dag = [s.model_dump() for s in body.custom_dag] if body.custom_dag else None
    result = create_and_plan_task(
        db,
        principal=principal,
        title=body.title,
        objective=body.objective,
        financial_amount_usd=body.financial_amount_usd,
        preferred_agent_id=body.preferred_agent_id,
        project_id=body.project_id,
        custom_dag=custom_dag,
        max_retries=body.max_retries,
        max_concurrency=body.max_concurrency,
        settings=settings,
    )
    if idempotency_key and idempotency_key.strip():
        save_idempotency(
            db,
            key=idempotency_key.strip(),
            tenant_id=principal.tenant_id,
            request_hash=req_hash,
            status_code=status.HTTP_201_CREATED,
            response_body=result,
        )
    return result


@router.get("")
def api_list_tasks(
    state: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("tasks:read")),
    db: Session = Depends(get_db),
) -> dict:
    tasks = list_tasks(db, tenant_id=principal.tenant_id, state=state, project_id=project_id, limit=limit)
    return {"total": len(tasks), "tasks": tasks}


@router.get("/{task_id}")
def api_get_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_task(db, tenant_id=principal.tenant_id, task_id=task_id)


@router.post("/{task_id}/transition")
def api_transition_task(
    task_id: str,
    body: TransitionTaskRequest,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
) -> dict:
    return transition_task_state(
        db,
        principal=principal,
        task_id=task_id,
        next_state=body.next_state,
        error_detail=body.error_detail,
    )


@router.post("/{task_id}/execute")
def api_execute_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return execute_task(db, principal=principal, task_id=task_id, settings=settings)


@router.post("/{task_id}/enqueue", status_code=status.HTTP_202_ACCEPTED)
def api_enqueue_task_execution(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
) -> dict:
    """Queue task execution for the persistent background worker (recommended for long DAGs outside Vercel limits)."""
    get_task(db, tenant_id=principal.tenant_id, task_id=task_id)
    job = enqueue_background_job(
        db,
        tenant_id=principal.tenant_id,
        job_type="EXECUTE_TASK",
        payload={"task_id": task_id},
    )
    return {"queued": True, "task_id": task_id, "job": job}


@router.post("/{task_id}/pause")
def api_pause_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
) -> dict:
    return pause_task(db, principal=principal, task_id=task_id)


@router.post("/{task_id}/resume")
def api_resume_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
) -> dict:
    return resume_task(db, principal=principal, task_id=task_id)


@router.post("/{task_id}/retry")
def api_retry_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return retry_task(db, principal=principal, task_id=task_id, settings=settings)


@router.post("/{task_id}/cancel")
def api_cancel_task(
    task_id: str,
    principal: Principal = Depends(require_perm("tasks:cancel")),
    db: Session = Depends(get_db),
) -> dict:
    return transition_task_state(
        db,
        principal=principal,
        task_id=task_id,
        next_state="CANCELLED",
        error_detail=f"Cancelled by {principal.username}",
    )
