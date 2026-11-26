"""Creative Studio, Voice Interaction & Visual Multimodal API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.platform_modules_service import (
    MEDIA_AGENT_MAP,
    analyze_visual_frame,
    create_media_job,
    list_media_jobs,
    process_voice_turn,
)

router = APIRouter(prefix="/api/v1/creative", tags=["Creative Studio, Voice & Visual"])


class VoiceTurnRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    mode: str = Field(default="push_to_talk", pattern="^(push_to_talk|continuous)$")


class VisualAnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    image_base64: str = Field(min_length=8)
    mime_type: str = Field(default="image/png", max_length=64)
    source: str = Field(default="camera", pattern="^(camera|screenshot|upload|screen_share)$")


class CreateMediaJobRequest(BaseModel):
    media_type: str = Field(min_length=2, max_length=32)
    prompt: str = Field(min_length=3, max_length=4000)


@router.post("/voice/turn")
def api_voice_turn(
    body: VoiceTurnRequest,
    principal: Principal = Depends(require_perm("creative:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return process_voice_turn(
        db,
        principal=principal,
        settings=settings,
        transcript=body.transcript,
        conversation_id=body.conversation_id,
        mode=body.mode,
    )


@router.post("/visual/analyze")
def api_visual_analyze(
    body: VisualAnalyzeRequest,
    principal: Principal = Depends(require_perm("creative:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return analyze_visual_frame(
        db,
        principal=principal,
        settings=settings,
        prompt=body.prompt,
        image_base64=body.image_base64,
        mime_type=body.mime_type,
        source=body.source,
    )


@router.get("/jobs")
def api_list_media_jobs(
    principal: Principal = Depends(require_perm("creative:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_media_jobs(db, tenant_id=principal.tenant_id)
    return {
        "total": len(items),
        "supported_media_types": sorted(MEDIA_AGENT_MAP.keys()),
        "jobs": items,
        "empty_state": None if items else "No Creative Studio jobs created yet.",
    }


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def api_create_media_job(
    body: CreateMediaJobRequest,
    principal: Principal = Depends(require_perm("creative:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return create_media_job(
        db,
        principal=principal,
        settings=settings,
        media_type=body.media_type,
        prompt=body.prompt,
    )
