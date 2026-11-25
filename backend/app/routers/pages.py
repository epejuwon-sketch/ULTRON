"""112-Page Integration Registry router for ULTRON OS 2026.

Provides direct access to the 112-page integration matrix, integrity checks,
and page-to-agent mapping specifications.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.routers.deps import require_perm
from app.services.page_agent_registry import (
    PAGE_INTEGRATION_MATRIX,
    get_page_spec,
    validate_registry_integrity,
)

router = APIRouter(prefix="/api/v1/pages", tags=["Page-Agent Registry"])


@router.get("")
def list_pages(
    subsystem: str | None = Query(default=None),
    primary_agent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    pages = PAGE_INTEGRATION_MATRIX
    if subsystem:
        pages = [p for p in pages if subsystem.lower() in p["subsystem"].lower()]
    if primary_agent:
        pages = [p for p in pages if (p["primary_agent"] or "").upper() == primary_agent.upper()]
    if status:
        pages = [p for p in pages if (p["integration_status"] or "").upper() == status.upper()]

    validation = validate_registry_integrity()
    return {
        "total": len(pages),
        "total_registry_pages": len(PAGE_INTEGRATION_MATRIX),
        "valid": validation["valid"],
        "pages": pages,
    }


@router.get("/integrity")
def check_registry_integrity(
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    return validate_registry_integrity()


@router.get("/{page_id}")
def get_page(
    page_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    spec = get_page_spec(page_id)
    if not spec:
        raise NotFoundError(f"Page '{page_id}' not found in 112-page registry.")
    return spec


@router.get("/{page_id}/agents")
def get_page_agents(
    page_id: str,
    _principal: Principal = Depends(require_perm("agents:read")),
) -> dict:
    spec = get_page_spec(page_id)
    if not spec:
        raise NotFoundError(f"Page '{page_id}' not found in 112-page registry.")
    return {
        "page_id": spec["page_id"],
        "number": spec["number"],
        "name": spec["name"],
        "subsystem": spec["subsystem"],
        "primary_agent": spec["primary_agent"],
        "supporting_agents": spec["supporting_agents"],
        "backend_service": spec["backend_service"],
        "available_tools": spec["available_tools"],
        "required_permissions": spec["required_permissions"],
        "operational_status": spec["operational_status"],
        "integration_status": spec["integration_status"],
    }
