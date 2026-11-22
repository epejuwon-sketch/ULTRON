"""ARGON task orchestration, DAG planning, lifecycle transition, and execution routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import CreateTaskRequest, TransitionTaskRequest
from app.services.argon_orchestrator import (
    create_and_plan_task,
    execute_task,
    get_task,
    list_tasks,
    transition_task_state,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["ARGON Tasks & Orchestration"])


@router.post("", status_code=status.HTTP_201_CREATED)
def api_create_task(
    body: CreateTaskRequest,
    principal: Principal = Depends(require_perm("tasks:create")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Create and plan a multi-agent DAG task with automatic ApprovalGate policy evaluation."""
    custom_dag = [s.model_dump() for s in body.custom_dag] if body.custom_dag else None
    return create_and_plan_task(
        db,
        principal=principal,
        title=body.title,
        objective=body.objective,
        financial_amount_usd=body.financial_amount_usd,
        preferred_agent_id=body.preferred_agent_id,
        custom_dag=custom_dag,
        settings=settings,
    )


@router.get("")
def api_list_tasks(
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("tasks:read")),
    db: Session = Depends(get_db),
) -> dict:
    tasks = list_tasks(db, tenant_id=principal.tenant_id, state=state, limit=limit)
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
    """Execute a READY task's DAG steps in topological order."""
    return execute_task(db, principal=principal, task_id=task_id, settings=settings)


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
