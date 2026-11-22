"""ARGON Task Lifecycle State Machine & Multi-Agent DAG Orchestrator."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import AgentRecord, TaskRecord, TaskStepRecord
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.memory_service import store_memory
from app.services.neon_router import invoke_agent_reasoning, route_objective

VALID_LIFECYCLE_STATES = frozenset(
    {
        "CREATED",
        "PLANNED",
        "WAITING_FOR_APPROVAL",
        "READY",
        "RUNNING",
        "PAUSED",
        "RETRYING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"PLANNED", "CANCELLED", "FAILED"}),
    "PLANNED": frozenset({"READY", "WAITING_FOR_APPROVAL", "PAUSED", "CANCELLED", "FAILED"}),
    "WAITING_FOR_APPROVAL": frozenset({"READY", "CANCELLED", "FAILED"}),
    "READY": frozenset({"RUNNING", "PAUSED", "CANCELLED", "FAILED"}),
    "RUNNING": frozenset({"COMPLETED", "FAILED", "RETRYING", "PAUSED", "CANCELLED"}),
    "PAUSED": frozenset({"READY", "RUNNING", "CANCELLED"}),
    "RETRYING": frozenset({"RUNNING", "FAILED", "CANCELLED"}),
    "COMPLETED": frozenset(),
    "FAILED": frozenset({"RETRYING", "CANCELLED"}),
    "CANCELLED": frozenset(),
}


def has_circular_dependency(steps: list[dict[str, Any]]) -> bool:
    """Detect cycles in a DAG using 3-color depth-first search."""
    adj: dict[int, list[int]] = {int(s["step_number"]): [] for s in steps}
    for s in steps:
        sn = int(s["step_number"])
        for dep in s.get("depends_on", []):
            dep_i = int(dep)
            if dep_i == sn:
                return True
            if dep_i in adj:
                adj[dep_i].append(sn)

    color = {k: 0 for k in adj}  # 0=unvisited, 1=visiting, 2=visited

    def dfs(node: int) -> bool:
        color[node] = 1
        for nxt in adj[node]:
            if color[nxt] == 1:
                return True
            if color[nxt] == 0 and dfs(nxt):
                return True
        color[node] = 2
        return False

    return any(color[k] == 0 and dfs(k) for k in adj)


def topological_order(steps: list[TaskStepRecord]) -> list[TaskStepRecord]:
    """Return TaskStepRecords in deterministic dependency-respecting topological order."""
    by_num = {s.step_number: s for s in steps}
    in_degree = {s.step_number: 0 for s in steps}
    children: dict[int, list[int]] = {s.step_number: [] for s in steps}

    for s in steps:
        deps = json.loads(s.depends_on_json or "[]")
        for d in deps:
            if d in by_num:
                children[d].append(s.step_number)
                in_degree[s.step_number] += 1

    ready = sorted([num for num, deg in in_degree.items() if deg == 0])
    ordered: list[TaskStepRecord] = []
    while ready:
        current = ready.pop(0)
        ordered.append(by_num[current])
        for child in sorted(children[current]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                ready.append(child)
                ready.sort()
    return ordered


def _build_default_dag(objective: str, primary_agent_id: str) -> list[dict[str, Any]]:
    steps = [
        {
            "step_number": 1,
            "agent_id": "AGT-01",
            "description": f"Decompose and validate constraints for objective: {objective}",
            "depends_on": [],
        },
        {
            "step_number": 2,
            "agent_id": primary_agent_id,
            "description": f"Execute primary specialist analysis and synthesis: {objective}",
            "depends_on": [1],
        },
        {
            "step_number": 3,
            "agent_id": "AGT-25",
            "description": "Verify output integrity, policy adherence, and factual honesty.",
            "depends_on": [2],
        },
    ]
    return steps


def create_and_plan_task(
    db: Session,
    *,
    principal: Principal,
    title: str,
    objective: str,
    financial_amount_usd: float = 0.0,
    preferred_agent_id: str | None = None,
    custom_dag: list[dict[str, Any]] | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Create a task, plan its multi-agent DAG, and enforce ApprovalGate for high-risk or >$50 actions."""
    routing = route_objective(
        objective,
        financial_amount_usd=financial_amount_usd,
        settings=settings,
        preferred_agent_id=preferred_agent_id,
    )
    sanitized_obj = routing["sanitized_objective"]
    primary_agent = routing["selected_agent_id"]

    if db.get(AgentRecord, primary_agent) is None:
        raise NotFoundError(f"Assigned agent '{primary_agent}' does not exist.")

    dag_steps = custom_dag if custom_dag else _build_default_dag(sanitized_obj, primary_agent)
    step_numbers = [int(s["step_number"]) for s in dag_steps]
    if len(step_numbers) != len(set(step_numbers)):
        raise ValidationError("DAG contains duplicate step numbers.")
    for s in dag_steps:
        if db.get(AgentRecord, s["agent_id"]) is None:
            raise ValidationError(f"DAG step {s['step_number']} references unknown agent '{s['agent_id']}'.")
        for dep in s.get("depends_on", []):
            if int(dep) not in step_numbers:
                raise ValidationError(f"DAG step {s['step_number']} depends on missing step {dep}.")
    if has_circular_dependency(dag_steps):
        raise ValidationError("Circular dependency detected in task DAG.")

    task_id = f"tsk_{uuid.uuid4().hex[:16]}"
    initial_state = "WAITING_FOR_APPROVAL" if routing["requires_approval_gate"] else "READY"

    task = TaskRecord(
        task_id=task_id,
        tenant_id=principal.tenant_id,
        created_by=principal.username,
        title=title.strip() or sanitized_obj[:80],
        objective=sanitized_obj,
        lifecycle_state=initial_state,
        risk_level=routing["risk_level"],
        financial_amount_usd=float(financial_amount_usd),
        assigned_agent_id=primary_agent,
        reasoning_tier=routing["reasoning_tier"],
        dag_json=json.dumps(dag_steps),
    )
    db.add(task)
    db.flush()

    for step in dag_steps:
        db.add(
            TaskStepRecord(
                step_id=f"stp_{uuid.uuid4().hex[:16]}",
                task_id=task_id,
                step_number=int(step["step_number"]),
                agent_id=step["agent_id"],
                description=step["description"],
                depends_on_json=json.dumps([int(d) for d in step.get("depends_on", [])]),
                status="PENDING",
            )
        )

    approval_payload: dict[str, Any] | None = None
    if routing["requires_approval_gate"]:
        reason = (
            f"Financial amount ${financial_amount_usd:.2f} exceeds soft limit ${settings.approval_soft_limit_usd:.2f}"
            if financial_amount_usd > settings.approval_soft_limit_usd
            else f"High-risk operation detected ({routing['risk_level']})"
        )
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type="TASK_EXECUTION",
            reason=reason,
            risk_level=routing["risk_level"],
            financial_amount_usd=financial_amount_usd,
            task_id=task_id,
            payload={"title": task.title, "objective": sanitized_obj, "agent_id": primary_agent},
            commit=False,
        )
        approval_payload = serialize_approval(approval)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ARGON_TASK_PLANNED",
        resource=task_id,
        outcome=f"STATE={initial_state}|RISK={routing['risk_level']}|STEPS={len(dag_steps)}",
    )
    db.commit()
    db.refresh(task)
    result = serialize_task(db, task)
    result["approval"] = approval_payload
    return result


def transition_task_state(
    db: Session,
    *,
    principal: Principal,
    task_id: str,
    next_state: str,
    error_detail: str | None = None,
) -> dict[str, Any]:
    """Validate and apply an ARGON task lifecycle state transition."""
    target = next_state.strip().upper()
    if target not in VALID_LIFECYCLE_STATES:
        raise ValidationError(f"Invalid lifecycle state '{target}'.")

    task = db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' not found.")

    current = task.lifecycle_state
    if current == "WAITING_FOR_APPROVAL" and target == "READY":
        raise ConflictError("Tasks in WAITING_FOR_APPROVAL can only become READY through ApprovalGate approval.")
    if target != current and target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ConflictError(f"Illegal state transition from '{current}' to '{target}'.")

    task.lifecycle_state = target
    if error_detail is not None:
        task.error_detail = error_detail
    task.updated_at = datetime.now(timezone.utc)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=f"ARGON_TASK_{target}",
        resource=task_id,
        outcome=f"{current}->{target}",
    )
    db.commit()
    db.refresh(task)
    return serialize_task(db, task)


def execute_task(
    db: Session,
    *,
    principal: Principal,
    task_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Execute a READY task's DAG steps in topological order through NEON and store episodic memory."""
    task = db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' not found.")

    if task.lifecycle_state == "WAITING_FOR_APPROVAL":
        raise ConflictError("Task is blocked at ApprovalGate and requires approval before execution.")
    if task.lifecycle_state not in {"READY", "RETRYING"}:
        raise ConflictError(f"Task in state '{task.lifecycle_state}' cannot be executed.")

    task.lifecycle_state = "RUNNING"
    task.updated_at = datetime.now(timezone.utc)
    db.flush()

    steps = db.execute(
        select(TaskStepRecord).where(TaskStepRecord.task_id == task_id).order_by(TaskStepRecord.step_number.asc())
    ).scalars().all()
    ordered = topological_order(list(steps))

    step_outputs: dict[int, Any] = {}
    try:
        for step in ordered:
            step.status = "RUNNING"
            step.started_at = datetime.now(timezone.utc)
            db.flush()

            deps = json.loads(step.depends_on_json or "[]")
            prior_context = {f"step_{d}": step_outputs.get(d, {}) for d in deps}

            output = invoke_agent_reasoning(
                db,
                agent_id=step.agent_id,
                prompt=step.description,
                settings=settings,
                context={"task_id": task_id, "prior_steps": prior_context},
                reasoning_tier=task.reasoning_tier,
            )
            step.output_json = json.dumps(output, default=str)
            step.status = "COMPLETED"
            step.completed_at = datetime.now(timezone.utc)
            step_outputs[step.step_number] = output

            agent = db.get(AgentRecord, step.agent_id)
            if agent is not None:
                agent.tasks_completed += 1
                agent.last_active = datetime.now(timezone.utc)

        final_summary = {
            "steps_executed": len(ordered),
            "execution_modes": sorted({o.get("execution_mode", "unknown") for o in step_outputs.values()}),
            "final_output": step_outputs[ordered[-1].step_number]["output"] if ordered else "",
        }
        task.result_json = json.dumps(final_summary, default=str)
        task.lifecycle_state = "COMPLETED"
        task.updated_at = datetime.now(timezone.utc)

        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="ARGON_TASK_COMPLETED",
            resource=task_id,
            outcome=f"STEPS={len(ordered)}",
        )
        db.commit()

        # Persist episodic memory trace for downstream semantic recall
        store_memory(
            db,
            principal=principal,
            content=f"Completed task '{task.title}': {task.objective}. Result: {final_summary['final_output'][:400]}",
            memory_type="EPISODIC",
            namespace="task_executions",
            agent_id=task.assigned_agent_id,
            metadata={"task_id": task_id, "risk_level": task.risk_level},
            importance_score=0.7,
            settings=settings,
        )
    except Exception as exc:
        task.lifecycle_state = "FAILED"
        task.error_detail = str(exc)
        task.updated_at = datetime.now(timezone.utc)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="ARGON_TASK_FAILED",
            resource=task_id,
            outcome=str(exc)[:100],
        )
        db.commit()
        raise

    db.refresh(task)
    return serialize_task(db, task)


def list_tasks(
    db: Session,
    *,
    tenant_id: str,
    state: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(TaskRecord).where(TaskRecord.tenant_id == tenant_id)
    if state:
        stmt = stmt.where(TaskRecord.lifecycle_state == state.upper())
    rows = db.execute(stmt.order_by(TaskRecord.created_at.desc()).limit(limit)).scalars().all()
    return [serialize_task(db, r) for r in rows]


def get_task(db: Session, *, tenant_id: str, task_id: str) -> dict[str, Any]:
    task = db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' not found.")
    return serialize_task(db, task)


def serialize_task(db: Session, task: TaskRecord) -> dict[str, Any]:
    steps = db.execute(
        select(TaskStepRecord).where(TaskStepRecord.task_id == task.task_id).order_by(TaskStepRecord.step_number.asc())
    ).scalars().all()
    return {
        "task_id": task.task_id,
        "tenant_id": task.tenant_id,
        "created_by": task.created_by,
        "title": task.title,
        "objective": task.objective,
        "lifecycle_state": task.lifecycle_state,
        "risk_level": task.risk_level,
        "financial_amount_usd": task.financial_amount_usd,
        "assigned_agent_id": task.assigned_agent_id,
        "reasoning_tier": task.reasoning_tier,
        "steps": [
            {
                "step_id": s.step_id,
                "step_number": s.step_number,
                "agent_id": s.agent_id,
                "description": s.description,
                "depends_on": json.loads(s.depends_on_json or "[]"),
                "status": s.status,
                "output": json.loads(s.output_json or "{}"),
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in steps
        ],
        "result": json.loads(task.result_json or "{}"),
        "error_detail": task.error_detail,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }
