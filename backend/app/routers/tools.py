"""Governed Tool Registry & Execution Harness routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import ExecuteToolRequest
from app.services.tool_service import execute_tool, list_tool_executions, list_tools

router = APIRouter(prefix="/api/v1/tools", tags=["Tools & Execution Harness"])


@router.get("")
def api_list_tools(_principal: Principal = Depends(require_perm("tools:read"))) -> dict:
    tools = list_tools()
    return {"total": len(tools), "tools": tools}


@router.post("/{tool_name}/execute")
def api_execute_tool(
    tool_name: str,
    body: ExecuteToolRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return execute_tool(
        db,
        principal=principal,
        tool_name=tool_name,
        arguments=body.arguments,
        settings=settings,
        agent_id=body.agent_id,
    )


@router.get("/executions/history")
def api_tool_history(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("tools:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_tool_executions(db, tenant_id=principal.tenant_id, limit=limit)
    return {"total": len(items), "executions": items}
