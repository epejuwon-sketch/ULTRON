"""Operational monitoring, metrics (JSON + Prometheus), queue depth, and migration status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.models import AgentRecord, ApprovalRecord, BackgroundJobRecord, TaskRecord
from app.db.session import check_database_health, get_applied_migrations, get_db
from app.routers.deps import require_perm
from app.services.neon_router import get_usage_summary
from app.services.realtime_hub import metrics_tracker, realtime_hub

router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring & Observability"])


@router.get("/overview")
def api_monitoring_overview(
    principal: Principal = Depends(require_perm("monitoring:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    db_ok, db_detail = check_database_health(settings)
    pending_approvals = int(
        db.execute(
            select(func.count())
            .select_from(ApprovalRecord)
            .where(ApprovalRecord.tenant_id == principal.tenant_id, ApprovalRecord.status == "PENDING")
        ).scalar_one()
    )
    active_tasks = int(
        db.execute(
            select(func.count())
            .select_from(TaskRecord)
            .where(
                TaskRecord.tenant_id == principal.tenant_id,
                TaskRecord.lifecycle_state.in_(["READY", "RUNNING", "WAITING_FOR_APPROVAL", "RETRYING"]),
            )
        ).scalar_one()
    )
    queued_jobs = int(
        db.execute(
            select(func.count())
            .select_from(BackgroundJobRecord)
            .where(
                BackgroundJobRecord.tenant_id == principal.tenant_id,
                BackgroundJobRecord.status.in_(["QUEUED", "RETRYING", "RUNNING"]),
            )
        ).scalar_one()
    )
    agent_totals = db.execute(
        select(
            func.count(AgentRecord.agent_id),
            func.coalesce(func.sum(AgentRecord.tasks_completed), 0),
            func.coalesce(func.sum(AgentRecord.tasks_failed), 0),
        )
    ).one()

    return {
        "database": {"healthy": db_ok, "backend": settings.database_backend, "detail": db_detail},
        "http_metrics": metrics_tracker.snapshot(),
        "websocket_connections": realtime_hub.connection_count(),
        "governance": {"pending_approvals": pending_approvals},
        "orchestration": {"active_tasks": active_tasks, "queued_jobs": queued_jobs},
        "agents": {
            "total_registered": int(agent_totals[0]),
            "tasks_completed": int(agent_totals[1]),
            "tasks_failed": int(agent_totals[2]),
        },
        "neon_usage": get_usage_summary(db, tenant_id=principal.tenant_id),
        "applied_migrations": get_applied_migrations(settings),
    }


@router.get("/metrics", response_class=PlainTextResponse)
def api_prometheus_metrics(_principal: Principal = Depends(require_perm("monitoring:read"))) -> str:
    """Prometheus text exposition format for external scrapers."""
    return metrics_tracker.prometheus_text(active_ws=realtime_hub.connection_count())
