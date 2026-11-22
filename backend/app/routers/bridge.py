"""BRIDGE — iPhone PWA Share-to-JARVIS Intake API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.platform_modules_service import ingest_shared_item, list_shared_items

router = APIRouter(prefix="/api/v1/bridge", tags=["BRIDGE Share-to-JARVIS"])


class ShareIntakeRequest(BaseModel):
    title: str = Field(default="", max_length=240)
    url: str = Field(default="", max_length=1000)
    shared_text: str = Field(default="", max_length=16000)
    source_app: str = Field(default="ios_share_sheet", max_length=80)
    file_id: str | None = None


@router.post("/share", status_code=status.HTTP_201_CREATED)
def api_bridge_share(
    body: ShareIntakeRequest,
    principal: Principal = Depends(require_perm("bridge:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return ingest_shared_item(
        db,
        principal=principal,
        settings=settings,
        title=body.title,
        url=body.url,
        shared_text=body.shared_text,
        source_app=body.source_app,
        file_id=body.file_id,
    )


@router.get("/shares")
def api_list_bridge_shares(
    principal: Principal = Depends(require_perm("agents:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_shared_items(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "shares": items}
