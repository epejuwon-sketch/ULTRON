"""PULSE — Live Data-Backed Generated Web Pages API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.platform_modules_service import (
    VALID_PULSE_TYPES,
    create_pulse_page,
    list_pulse_pages,
    render_pulse_page_live,
)

router = APIRouter(prefix="/api/v1/pulse", tags=["PULSE Live Pages"])


class CreatePulsePageRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    page_type: str = Field(min_length=3, max_length=48)
    slug: str | None = None


@router.get("/pages")
def api_list_pulse_pages(
    principal: Principal = Depends(require_perm("pulse:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_pulse_pages(db, tenant_id=principal.tenant_id)
    return {
        "total": len(items),
        "supported_types": sorted(VALID_PULSE_TYPES),
        "pages": items,
    }


@router.post("/pages", status_code=status.HTTP_201_CREATED)
def api_create_pulse_page(
    body: CreatePulsePageRequest,
    principal: Principal = Depends(require_perm("pulse:write")),
    db: Session = Depends(get_db),
) -> dict:
    return create_pulse_page(
        db,
        principal=principal,
        title=body.title,
        page_type=body.page_type,
        slug=body.slug,
    )


@router.get("/pages/{page_id}/live")
def api_render_pulse_page_live(
    page_id: str,
    principal: Principal = Depends(require_perm("pulse:read")),
    db: Session = Depends(get_db),
) -> dict:
    return render_pulse_page_live(db, tenant_id=principal.tenant_id, page_id=page_id)
