"""ARGON Autonomous Orchestration Engine: parallel DAG waves, pause/resume/retry, verification, and resource limits."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import AgentRecord, TaskRecord, TaskStepRecord
from app.db.repositories import append_audit_log
from app.db.session import get_session_factory
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.memory_service import store_memory
from app.services.neon_router import invoke_agent_reasoning, route_objective
from app.services.notification_service import create_notification
from app.services.realtime_hub import realtime_hub
from app.services.settings_service import is_autonomous_execution_enabled

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

    color = {k: 0 for k in adj}

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


def compute_execution_waves(steps: list[TaskStepRecord]) -> list[list[TaskStepRecord]]:
    """Group DAG steps into parallelizable execution waves respecting all dependencies."""
    by_num = {s.step_number: s for s in steps}
    in_degree = {s.step_number: 0 for s in steps}
    children: dict[int, list[int]] = {s.step_number: [] for s in steps}

    for s in steps:
        deps = json.loads(s.depends_on_json or "[]")
        for d in deps:
            if d in by_num:
                children[d].append(s.step_number)
                in_degree[s.step_number] += 1

    waves: list[list[TaskStepRecord]] = []
    frontier = sorted(num for num, deg in in_degree.items() if deg == 0)
    while frontier:
        waves.append([by_num[n] for n in frontier])
        next_frontier: list[int] = []
        for num in frontier:
            for child in children[num]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_frontier.append(child)
        frontier = sorted(next_frontier)
    return waves


def verify_task_results(steps: list[TaskStepRecord]) -> dict[str, Any]:
    """Independently verify DAG steps and classify COMPLETED, PARTIALLY_COMPLETED, FAILED, or UNVERIFIED work."""
    checks: list[dict[str, Any]] = []
    passed_count = 0
    failed_count = 0
    unverified_count = 0
    fallback_count = 0

    for step in steps:
        output = json.loads(step.output_json or "{}")
        has_output = bool(output.get("output")) and bool(output.get("agent_id"))
        mode = str(output.get("execution_mode") or "unknown")
        if "fallback" in mode.lower():
            fallback_count += 1
        step_ok = step.status == "COMPLETED" and has_output and not step.error_detail
        if step_ok:
            passed_count += 1
        elif step.status == "FAILED" or step.error_detail:
            failed_count += 1
        else:
            unverified_count += 1
        checks.append(
            {
                "step_number": step.step_number,
                "agent_id": step.agent_id,
                "status": step.status,
                "has_valid_output": has_output,
                "execution_mode": mode,
                "passed": step_ok,
            }
        )

    total = len(steps)
    all_passed = total > 0 and passed_count == total
    if all_passed:
        outcome = "COMPLETED"
    elif passed_count > 0 and (failed_count > 0 or unverified_count > 0):
        outcome = "PARTIALLY_COMPLETED"
    elif failed_count > 0:
        outcome = "FAILED"
    else:
        outcome = "UNVERIFIED"

    return {
        "verified": all_passed,
        "outcome_classification": outcome,
        "checked_steps": total,
        "completed_steps": passed_count,
        "failed_steps": failed_count,
        "unverified_steps": unverified_count,
        "fallback_steps": fallback_count,
        "checks": checks,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_default_dag(objective: str, primary_agent_id: str) -> list[dict[str, Any]]:
    lowered = objective.lower()
    is_market_collab = (
        ("market research" in lowered)
        or (("research" in lowered or "competitor" in lowered) and any(k in lowered for k in ("marketing", "go-to-market", "gtm", "campaign", "positioning")))
    )
    if is_market_collab:
        return [
            {
                "step_number": 1,
                "agent_id": "AGT-01",
                "description": f"Decompose scope and constraints for market intelligence objective: {objective}",
                "depends_on": [],
            },
            {
                "step_number": 2,
                "agent_id": "AGT-02",
                "description": f"Conduct market research, competitive evidence gathering, and audience analysis: {objective}",
                "depends_on": [1],
            },
            {
                "step_number": 3,
                "agent_id": "AGT-06",
                "description": f"Collaborate with Research Agent output to build positioning, messaging, and go-to-market marketing strategy: {objective}",
                "depends_on": [2],
            },
            {
                "step_number": 4,
                "agent_id": "AGT-25",
                "description": "Verify output integrity, policy adherence, and factual honesty across Research and Marketing deliverables.",
                "depends_on": [3],
            },
        ]

    return [
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


def create_and_plan_task(
    db: Session,
    *,
    principal: Principal,
    title: str,
    objective: str,
    financial_amount_usd: float = 0.0,
    preferred_agent_id: str | None = None,
    project_id: str | None = None,
    custom_dag: list[dict[str, Any]] | None = None,
    max_retries: int = 2,
    max_concurrency: int = 4,
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

    agent_rec = db.get(AgentRecord, primary_agent)
    if agent_rec is None or not agent_rec.approved:
        raise NotFoundError(f"Assigned agent '{primary_agent}' does not exist or is not approved.")

    dag_steps = custom_dag if custom_dag else _build_default_dag(sanitized_obj, primary_agent)
    step_numbers = [int(s["step_number"]) for s in dag_steps]
    if len(step_numbers) != len(set(step_numbers)):
        raise ValidationError("DAG contains duplicate step numbers.")
    for s in dag_steps:
        ag = db.get(AgentRecord, s["agent_id"])
        if ag is None or not ag.approved:
            raise ValidationError(f"DAG step {s['step_number']} references unknown or unapproved agent '{s['agent_id']}'.")
        for dep in s.get("depends_on", []):
            if int(dep) not in step_numbers:
                raise ValidationError(f"DAG step {s['step_number']} depends on missing step {dep}.")
    if has_circular_dependency(dag_steps):
        raise ValidationError("Circular dependency detected in task DAG.")

    task_id = f"tsk_{uuid.uuid4().hex[:16]}"
    initial_state = "WAITING_FOR_APPROVAL" if routing["requires_approval_gate"] else "READY"
    bounded_concurrency = max(1, min(int(max_concurrency), settings.argon_max_parallel_steps))

    task = TaskRecord(
        task_id=task_id,
        tenant_id=principal.tenant_id,
        project_id=project_id,
        created_by=principal.username,
        title=title.strip() or sanitized_obj[:80],
        objective=sanitized_obj,
        lifecycle_state=initial_state,
        risk_level=routing["risk_level"],
        financial_amount_usd=float(financial_amount_usd),
        assigned_agent_id=primary_agent,
        reasoning_tier=routing["reasoning_tier"],
        progress_percent=0,
        max_retries=max(0, min(5, int(max_retries))),
        max_concurrency=bounded_concurrency,
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
    realtime_hub.publish_sync(principal.tenant_id, "task.planned", {"task_id": task_id, "state": initial_state})
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


def pause_task(db: Session, *, principal: Principal, task_id: str) -> dict[str, Any]:
    return transition_task_state(db, principal=principal, task_id=task_id, next_state="PAUSED")


def resume_task(db: Session, *, principal: Principal, task_id: str) -> dict[str, Any]:
    return transition_task_state(db, principal=principal, task_id=task_id, next_state="READY")


def retry_task(db: Session, *, principal: Principal, task_id: str, settings: Settings) -> dict[str, Any]:
    """Retry a FAILED task up to its max_retries budget and re-execute incomplete steps."""
    task = db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' not found.")
    if task.lifecycle_state != "FAILED":
        raise ConflictError(f"Only FAILED tasks can be retried (current state: '{task.lifecycle_state}').")
    if task.retry_count >= task.max_retries:
        raise ConflictError(f"Task '{task_id}' exhausted its retry limit ({task.max_retries}).")

    task.retry_count += 1
    task.lifecycle_state = "RETRYING"
    task.error_detail = None
    steps = db.execute(select(TaskStepRecord).where(TaskStepRecord.task_id == task_id)).scalars().all()
    for s in steps:
        if s.status != "COMPLETED":
            s.status = "PENDING"
            s.error_detail = None
    db.commit()
    return execute_task(db, principal=principal, task_id=task_id, settings=settings)


def _execute_single_step_isolated(
    *,
    step_id: str,
    task_id: str,
    agent_id: str,
    description: str,
    prior_context: dict[str, Any],
    reasoning_tier: int,
    tenant_id: str,
    actor: str,
    settings: Settings,
) -> tuple[str, dict[str, Any]]:
    """Run one DAG step in an isolated DB session (thread-safe for parallel waves)."""
    with get_session_factory(settings)() as step_db:
        output = invoke_agent_reasoning(
            step_db,
            agent_id=agent_id,
            prompt=description,
            settings=settings,
            context={"task_id": task_id, "prior_steps": prior_context},
            reasoning_tier=reasoning_tier,
            tenant_id=tenant_id,
            actor=actor,
        )
        step_db.commit()
        return step_id, output


def execute_task(
    db: Session,
    *,
    principal: Principal,
    task_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Execute a READY/RETRYING task in parallel DAG waves with independent verification."""
    if not is_autonomous_execution_enabled(db, tenant_id=principal.tenant_id):
        raise ConflictError("Autonomous execution is currently paused by OWNER kill-switch setting.")

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

    steps = list(
        db.execute(
            select(TaskStepRecord)
            .where(TaskStepRecord.task_id == task_id)
            .order_by(TaskStepRecord.step_number.asc())
        ).scalars().all()
    )
    waves = compute_execution_waves(steps)
    total_steps = max(1, len(steps))
    completed_count = sum(1 for s in steps if s.status == "COMPLETED")
    step_outputs: dict[int, Any] = {
        s.step_number: json.loads(s.output_json or "{}") for s in steps if s.status == "COMPLETED"
    }

    try:
        for wave in waves:
            pending_in_wave = [s for s in wave if s.status != "COMPLETED"]
            if not pending_in_wave:
                continue

            now = datetime.now(timezone.utc)
            for s in pending_in_wave:
                s.status = "RUNNING"
                s.attempt_count += 1
                s.started_at = now
            db.commit()

            if len(pending_in_wave) == 1 or task.max_concurrency <= 1:
                wave_results: dict[str, dict[str, Any]] = {}
                for s in pending_in_wave:
                    deps = json.loads(s.depends_on_json or "[]")
                    prior_ctx = {f"step_{d}": step_outputs.get(d, {}) for d in deps}
                    out = invoke_agent_reasoning(
                        db,
                        agent_id=s.agent_id,
                        prompt=s.description,
                        settings=settings,
                        context={"task_id": task_id, "prior_steps": prior_ctx},
                        reasoning_tier=task.reasoning_tier,
                        tenant_id=principal.tenant_id,
                        actor=principal.username,
                    )
                    wave_results[s.step_id] = out
            else:
                workers = min(len(pending_in_wave), task.max_concurrency)
                wave_results = {}
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = []
                    for s in pending_in_wave:
                        deps = json.loads(s.depends_on_json or "[]")
                        prior_ctx = {f"step_{d}": step_outputs.get(d, {}) for d in deps}
                        futures.append(
                            pool.submit(
                                _execute_single_step_isolated,
                                step_id=s.step_id,
                                task_id=task_id,
                                agent_id=s.agent_id,
                                description=s.description,
                                prior_context=prior_ctx,
                                reasoning_tier=task.reasoning_tier,
                                tenant_id=principal.tenant_id,
                                actor=principal.username,
                                settings=settings,
                            )
                        )
                    for fut in futures:
                        sid, out = fut.result(timeout=settings.argon_step_timeout_seconds)
                        wave_results[sid] = out

            done_now = datetime.now(timezone.utc)
            for s in pending_in_wave:
                out = wave_results[s.step_id]
                s.output_json = json.dumps(out, default=str)
                s.status = "COMPLETED"
                s.completed_at = done_now
                step_outputs[s.step_number] = out
                completed_count += 1

                agent = db.get(AgentRecord, s.agent_id)
                if agent is not None:
                    agent.tasks_completed += 1
                    agent.last_active = done_now

            task.progress_percent = min(99, int((completed_count / total_steps) * 100))
            db.flush()
            realtime_hub.publish_sync(
                principal.tenant_id,
                "task.progress",
                {"task_id": task_id, "progress_percent": task.progress_percent, "completed_steps": completed_count},
            )

        # Independent result verification BEFORE marking COMPLETED
        verification = verify_task_results(steps)
        task.verification_json = json.dumps(verification, default=str)
        if not verification["verified"]:
            raise RuntimeError("ARGON independent result verification failed.")

        last_step_num = max(step_outputs.keys()) if step_outputs else None
        final_summary = {
            "steps_executed": len(steps),
            "parallel_waves": len(waves),
            "verified": True,
            "execution_modes": sorted({o.get("execution_mode", "unknown") for o in step_outputs.values()}),
            "final_output": step_outputs[last_step_num]["output"] if last_step_num is not None else "",
        }
        task.result_json = json.dumps(final_summary, default=str)
        task.progress_percent = 100
        task.lifecycle_state = "COMPLETED"
        task.updated_at = datetime.now(timezone.utc)

        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="ARGON_TASK_COMPLETED",
            resource=task_id,
            outcome=f"STEPS={len(steps)}|WAVES={len(waves)}|VERIFIED=TRUE",
        )
        create_notification(
            db,
            tenant_id=principal.tenant_id,
            severity="INFO",
            category="ARGON_TASK",
            title=f"Task Completed: {task.title}",
            message=f"Executed {len(steps)} steps across {len(waves)} DAG wave(s) and passed verification.",
            metadata={"task_id": task_id},
            commit=False,
        )
        db.commit()

        store_memory(
            db,
            principal=principal,
            content=f"Completed task '{task.title}': {task.objective}. Result: {final_summary['final_output'][:400]}",
            memory_type="EPISODIC",
            namespace="task_executions",
            agent_id=task.assigned_agent_id,
            project_id=task.project_id,
            metadata={"task_id": task_id, "risk_level": task.risk_level, "verified": True},
            importance_score=0.7,
            settings=settings,
        )
        realtime_hub.publish_sync(principal.tenant_id, "task.completed", {"task_id": task_id, "verified": True})
    except Exception as exc:
        task.lifecycle_state = "FAILED"
        task.error_detail = str(exc)
        task.updated_at = datetime.now(timezone.utc)
        agent = db.get(AgentRecord, task.assigned_agent_id)
        if agent is not None:
            agent.tasks_failed += 1
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
    project_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(TaskRecord).where(TaskRecord.tenant_id == tenant_id)
    if state:
        stmt = stmt.where(TaskRecord.lifecycle_state == state.upper())
    if project_id:
        stmt = stmt.where(TaskRecord.project_id == project_id)
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
        "project_id": task.project_id,
        "created_by": task.created_by,
        "title": task.title,
        "objective": task.objective,
        "lifecycle_state": task.lifecycle_state,
        "risk_level": task.risk_level,
        "financial_amount_usd": task.financial_amount_usd,
        "assigned_agent_id": task.assigned_agent_id,
        "reasoning_tier": task.reasoning_tier,
        "progress_percent": task.progress_percent,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "max_concurrency": task.max_concurrency,
        "steps": [
            {
                "step_id": s.step_id,
                "step_number": s.step_number,
                "agent_id": s.agent_id,
                "description": s.description,
                "depends_on": json.loads(s.depends_on_json or "[]"),
                "status": s.status,
                "attempt_count": s.attempt_count,
                "output": json.loads(s.output_json or "{}"),
                "error_detail": s.error_detail,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in steps
        ],
        "result": json.loads(task.result_json or "{}"),
        "verification": json.loads(task.verification_json or "{}"),
        "error_detail": task.error_detail,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }
