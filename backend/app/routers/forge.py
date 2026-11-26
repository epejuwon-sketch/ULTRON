"""FORGE & LIVE PREVIEW API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.forge_service import (
    VALID_TEMPLATES,
    generate_forge_project,
    get_forge_project,
    list_forge_projects,
    update_forge_project,
)

router = APIRouter(prefix="/api/v1/forge", tags=["FORGE & Live Preview"])


class GenerateForgeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    template: str = Field(default="web_app")
    prompt: str = Field(min_length=5, max_length=8000)
    custom_files: dict[str, str] | None = None


class UpdateForgeRequest(BaseModel):
    files: dict[str, str]


@router.get("/projects")
def api_list_forge_projects(
    principal: Principal = Depends(require_perm("forge:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_forge_projects(db, tenant_id=principal.tenant_id)
    return {
        "total": len(items),
        "supported_templates": sorted(VALID_TEMPLATES),
        "projects": items,
        "empty_state": None if items else "No FORGE projects generated yet.",
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def api_generate_forge_project(
    body: GenerateForgeRequest,
    principal: Principal = Depends(require_perm("forge:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return generate_forge_project(
        db,
        principal=principal,
        settings=settings,
        name=body.name,
        template=body.template,
        prompt=body.prompt,
        custom_files=body.custom_files,
    )


@router.get("/projects/{forge_id}")
def api_get_forge_project(
    forge_id: str,
    principal: Principal = Depends(require_perm("forge:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_forge_project(db, tenant_id=principal.tenant_id, forge_id=forge_id)


@router.patch("/projects/{forge_id}")
def api_update_forge_project(
    forge_id: str,
    body: UpdateForgeRequest,
    principal: Principal = Depends(require_perm("forge:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return update_forge_project(
        db,
        principal=principal,
        settings=settings,
        forge_id=forge_id,
        files=body.files,
    )


@router.get("/projects/{forge_id}/preview", response_class=HTMLResponse)
def api_forge_live_preview(
    forge_id: str,
    principal: Principal = Depends(require_perm("forge:read")),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    proj = get_forge_project(db, tenant_id=principal.tenant_id, forge_id=forge_id)
    html_doc = proj.get("preview_html") or ""
    if not html_doc:
        raise NotFoundError("Live preview unavailable (project failed AEGIS verification or has no preview HTML).")
    return HTMLResponse(
        content=html_doc,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:;",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )
