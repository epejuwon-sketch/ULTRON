"""Unified NEON + ARGON + Specialist Agent Natural-Language Orchestration Bridge."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Principal
from app.services.argon_orchestrator import create_and_plan_task, execute_task
from app.services.device_service import list_devices
from app.services.integration_manager import list_connections
from app.services.memory_service import search_memories
from app.services.neon_router import route_objective


def orchestrate_natural_language_objective(
    db: Session,
    *,
    principal: Principal,
    objective: str,
    financial_amount_usd: float = 0.0,
    project_id: str | None = None,
    auto_execute: bool = True,
    settings: Settings,
) -> dict[str, Any]:
    """End-to-end natural-language orchestration uniting NEON, ARGON, 60 Agents, Memory, Integrations, and Devices.

    The caller supplies a plain-language objective without manually selecting agents.
    1. Recalls relevant tenant memories.
    2. Discovers authorized integrations & paired online devices.
    3. Routes via NEON to select reasoning tier, primary specialist agent, and risk class.
    4. Plans multi-agent DAG in ARGON with ApprovalGate checkpoints.
    5. Executes & independently verifies results when auto_execute=True and not gated.
    """
    memory_recall = search_memories(
        db,
        tenant_id=principal.tenant_id,
        query=objective,
        viewer_user_id=principal.user_id,
        limit=5,
        settings=settings,
    )
    integrations = list_connections(db, tenant_id=principal.tenant_id, settings=settings)
    available_integrations = [
        c["provider"] for c in integrations["connections"] if c["status"] == "AVAILABLE"
    ]
    online_devices = [
        {"device_id": d["device_id"], "name": d["name"], "platform": d["platform"]}
        for d in list_devices(db, tenant_id=principal.tenant_id)
        if d["status"] == "ONLINE"
    ]

    routing = route_objective(
        objective,
        financial_amount_usd=financial_amount_usd,
        settings=settings,
    )

    planned_task = create_and_plan_task(
        db,
        principal=principal,
        title=objective.strip()[:80],
        objective=objective,
        financial_amount_usd=financial_amount_usd,
        preferred_agent_id=routing["selected_agent_id"],
        project_id=project_id,
        settings=settings,
    )

    final_task = planned_task
    executed = False
    if auto_execute and planned_task["lifecycle_state"] == "READY":
        final_task = execute_task(
            db,
            principal=principal,
            task_id=planned_task["task_id"],
            settings=settings,
        )
        executed = True

    return {
        "orchestration_status": final_task["lifecycle_state"],
        "executed": executed,
        "requires_approval": final_task["lifecycle_state"] == "WAITING_FOR_APPROVAL",
        "approval": planned_task.get("approval"),
        "neon_routing": routing,
        "context_used": {
            "recalled_memories": memory_recall["total_matches"],
            "available_integrations": available_integrations,
            "online_devices": online_devices,
        },
        "task": final_task,
    }
