"""FILE HUB API routes: secure upload, inspection, generation, ZIP export, and download."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.file_hub_service import (
    _serialize_file,
    create_zip_bundle_file,
    generate_and_store_file,
    get_file_record,
    ingest_uploaded_file,
    list_files,
)

router = APIRouter(prefix="/api/v1/files", tags=["FILE HUB"])


class GenerateFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(default="")
    content_base64: str | None = None
    mime_type: str = Field(default="text/markdown", max_length=120)
    project_id: str | None = None


class GenerateZipRequest(BaseModel):
    archive_name: str = Field(min_length=2, max_length=160)
    files: dict[str, str]
    project_id: str | None = None


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def api_upload_file(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw_bytes = await file.read()
    return ingest_uploaded_file(
        db,
        principal=principal,
        settings=settings,
        filename=file.filename or "upload.bin",
        raw_bytes=raw_bytes,
        mime_type=file.content_type or "application/octet-stream",
        project_id=project_id,
    )


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def api_generate_file(
    body: GenerateFileRequest,
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw = base64.b64decode(body.content_base64) if body.content_base64 else body.content.encode("utf-8")
    return generate_and_store_file(
        db,
        principal=principal,
        settings=settings,
        filename=body.filename,
        content_bytes=raw,
        mime_type=body.mime_type,
        project_id=body.project_id,
    )


@router.post("/generate-zip", status_code=status.HTTP_201_CREATED)
def api_generate_zip(
    body: GenerateZipRequest,
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return create_zip_bundle_file(
        db,
        principal=principal,
        settings=settings,
        archive_name=body.archive_name,
        files_map=body.files,
        project_id=body.project_id,
    )


@router.get("")
def api_list_files(
    direction: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_files(db, tenant_id=principal.tenant_id, direction=direction, project_id=project_id)
    return {
        "total": len(items),
        "files": items,
        "empty_state": None if items else "No files uploaded or generated yet.",
    }


@router.get("/{file_id}")
def api_get_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
) -> dict:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    return _serialize_file(rec, include_text=True)


@router.get("/{file_id}/download")
def api_download_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
) -> Response:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    path = Path(rec.storage_path)
    if not path.exists():
        raise NotFoundError("Stored file payload not found on disk.")
    return Response(
        content=path.read_bytes(),
        media_type=rec.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{rec.filename}"'},
    )
