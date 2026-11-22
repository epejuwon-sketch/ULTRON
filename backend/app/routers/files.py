"""FILE HUB API routes: secure upload, inspection, generation, ZIP export, signed URLs, delete, restore, and download."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.file_hub_service import (
    _serialize_file,
    create_signed_file_url,
    create_zip_bundle_file,
    download_file_bytes,
    download_via_signed_token,
    generate_and_store_file,
    get_file_record,
    ingest_uploaded_file,
    list_files,
    restore_file,
    soft_delete_file,
    update_file_metadata,
)
from app.services.storage_adapter import get_storage_adapter

router = APIRouter(prefix="/api/v1/files", tags=["FILE HUB"])


class GenerateFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(default="")
    content_base64: str | None = None
    mime_type: str = Field(default="text/markdown", max_length=120)
    project_id: str | None = None
    folder: str | None = Field(default=None, max_length=80)


class GenerateZipRequest(BaseModel):
    archive_name: str = Field(min_length=2, max_length=160)
    files: dict[str, str]
    project_id: str | None = None


class UpdateFileRequest(BaseModel):
    filename: str | None = Field(default=None, min_length=1, max_length=200)
    folder: str | None = Field(default=None, max_length=80)


class SignedUrlRequest(BaseModel):
    expires_in_seconds: int = Field(default=300, ge=30, le=3600)


@router.get("/storage/status")
def api_storage_status(
    _principal: Principal = Depends(require_perm("files:read")),
    settings: Settings = Depends(get_settings),
) -> dict:
    adapter = get_storage_adapter(settings)
    return {
        "active_backend": adapter.backend_name,
        "private_bucket_default": settings.supabase_storage_bucket,
        "supabase_storage_configured": adapter.backend_name == "supabase_storage",
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def api_upload_file(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    folder: str | None = Form(default=None),
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
        folder=folder,
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
        folder=body.folder,
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
    folder: str | None = Query(default=None),
    search: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_files(
        db,
        tenant_id=principal.tenant_id,
        direction=direction,
        project_id=project_id,
        folder=folder,
        search=search,
        include_deleted=include_deleted,
    )
    folders = sorted({str(i.get("folder") or "General") for i in items})
    return {
        "total": len(items),
        "folders": folders,
        "files": items,
        "empty_state": None if items else "No files uploaded or generated yet.",
    }


@router.get("/signed/{token}")
def api_download_signed_file(
    token: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Serve a file via short-lived HMAC-signed URL token (local adapter; Supabase returns direct cloud signed URLs)."""
    rec, raw = download_via_signed_token(db, token=token, settings=settings)
    return Response(
        content=raw,
        media_type=rec.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{rec.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{file_id}")
def api_get_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
) -> dict:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    return _serialize_file(rec, include_text=True)


@router.patch("/{file_id}")
def api_update_file(
    file_id: str,
    body: UpdateFileRequest,
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
) -> dict:
    """Rename a stored file or organize it into another folder."""
    return update_file_metadata(
        db,
        principal=principal,
        file_id=file_id,
        filename=body.filename,
        folder=body.folder,
    )


@router.get("/{file_id}/preview")
def api_preview_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Serve an authenticated inline preview for uploaded images and documents."""
    rec, raw = download_file_bytes(db, tenant_id=principal.tenant_id, file_id=file_id, settings=settings)
    return Response(
        content=raw,
        media_type=rec.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{rec.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{file_id}/download")
def api_download_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    rec, raw = download_file_bytes(db, tenant_id=principal.tenant_id, file_id=file_id, settings=settings)
    return Response(
        content=raw,
        media_type=rec.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{rec.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{file_id}/signed-url")
def api_create_signed_url(
    file_id: str,
    body: SignedUrlRequest,
    principal: Principal = Depends(require_perm("files:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return create_signed_file_url(
        db,
        principal=principal,
        file_id=file_id,
        settings=settings,
        expires_in_seconds=body.expires_in_seconds,
    )


@router.delete("/{file_id}")
def api_soft_delete_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return soft_delete_file(db, principal=principal, file_id=file_id, settings=settings)


@router.post("/{file_id}/restore")
def api_restore_file(
    file_id: str,
    principal: Principal = Depends(require_perm("files:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return restore_file(db, principal=principal, file_id=file_id, settings=settings)
