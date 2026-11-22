"""FILE HUB — Two-Way Secure File Intake, XXE-Safe Extraction, Secret Redaction & Persistent Cloud/Local Storage."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.db.models import FileRecord
from app.db.repositories import append_audit_log
from app.services.storage_adapter import (
    BaseStorageAdapter,
    get_storage_adapter,
    verify_local_download_token,
)

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per upload

TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".tsx", ".jsx",
        ".html", ".css", ".sql", ".yaml", ".yml", ".toml", ".xml", ".env", ".sh", ".log",
    }
)

BLOCKED_EXTENSIONS = frozenset({".exe", ".dll", ".bat", ".cmd", ".msi", ".com", ".scr", ".vbs"})


def _safe_filename(name: str) -> str:
    base = Path(name or "untitled.txt").name
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip()
    return cleaned[:200] or "untitled.txt"


def _extract_content(filename: str, raw_bytes: bytes) -> tuple[str, dict[str, Any]]:
    ext = Path(filename).suffix.lower()
    meta: dict[str, Any] = {"extension": ext, "extractor": "binary_metadata_only"}

    if ext in TEXT_EXTENSIONS:
        text = raw_bytes.decode("utf-8", errors="replace")
        meta["extractor"] = "utf8_text"
        meta["line_count"] = text.count("\n") + 1
        if ext == ".csv":
            reader = list(csv.reader(io.StringIO(text)))
            meta["csv_rows"] = len(reader)
            meta["csv_columns"] = reader[0] if reader else []
        elif ext == ".json":
            try:
                parsed = json.loads(text)
                meta["json_type"] = type(parsed).__name__
            except json.JSONDecodeError:
                meta["json_valid"] = False
        return text[:100_000], meta

    if ext in {".docx", ".xlsx", ".pptx", ".zip"}:
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                names = zf.namelist()
                meta["archive_entries"] = len(names)
                meta["entries_preview"] = names[:30]
                if ext == ".docx" and "word/document.xml" in names:
                    root = SafeET.fromstring(zf.read("word/document.xml"))
                    extracted = " ".join(elem.text for elem in root.iter() if elem.text)
                    meta["extractor"] = "docx_defusedxml"
                    return extracted[:100_000], meta
                if ext == ".pptx":
                    slides = [n for n in sorted(names) if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
                    parts = []
                    for s in slides:
                        root = SafeET.fromstring(zf.read(s))
                        parts.append(" ".join(e.text for e in root.iter() if e.text))
                    meta["extractor"] = "pptx_defusedxml"
                    meta["slide_count"] = len(slides)
                    return "\n".join(parts)[:100_000], meta
                if ext == ".xlsx":
                    shared = []
                    if "xl/sharedStrings.xml" in names:
                        root = SafeET.fromstring(zf.read("xl/sharedStrings.xml"))
                        shared = [e.text for e in root.iter() if e.text]
                    meta["extractor"] = "xlsx_defusedxml"
                    return "\n".join(shared)[:100_000], meta
                meta["extractor"] = "zip_manifest"
                return "\n".join(names[:200]), meta
        except zipfile.BadZipFile:
            meta["extractor"] = "invalid_zip"
            return "", meta

    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            pages_text = [(page.extract_text() or "").strip() for page in reader.pages]
            extracted = "\n\n".join(p for p in pages_text if p)
            meta["extractor"] = "pypdf"
            meta["page_count"] = len(reader.pages)
            return extracted[:100_000], meta
        except Exception:
            ascii_chunks = re.findall(rb"\(([^()]{3,200})\)", raw_bytes)
            extracted = " ".join(c.decode("latin-1", errors="ignore") for c in ascii_chunks[:500])
            meta["extractor"] = "pdf_basic_text_scan"
            return extracted[:100_000], meta

    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(raw_bytes)) as img:
                meta["extractor"] = "pillow_image_metadata"
                meta["width"] = img.width
                meta["height"] = img.height
                meta["format"] = img.format
                meta["mode"] = img.mode
        except Exception:
            meta["extractor"] = "image_raw_bytes"
        return "", meta

    return "", meta


def _safe_folder(folder: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\- /]+", "_", (folder or "General").strip()).strip("/")
    return cleaned[:80] or "General"


def ingest_uploaded_file(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    filename: str,
    raw_bytes: bytes,
    mime_type: str = "application/octet-stream",
    project_id: str | None = None,
    folder: str | None = None,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    """Validate, hash, scan, redact secrets, extract text, tag as untrusted, and persist via StorageAdapter."""
    safe_name = _safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"Executable file extension '{ext}' is blocked by AEGIS file intake policy.")
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ValidationError(f"File exceeds maximum allowed size of {MAX_FILE_BYTES // (1024 * 1024)} MB.")

    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    file_id = f"fil_{uuid.uuid4().hex[:14]}"
    adapter = storage or get_storage_adapter(settings)
    storage_ref = adapter.upload_bytes(
        tenant_id=principal.tenant_id,
        object_key=f"{file_id}_{safe_name}",
        data=raw_bytes,
        mime_type=mime_type or "application/octet-stream",
    )

    raw_extracted, meta = _extract_content(safe_name, raw_bytes)
    interception = intercept_and_redact_secrets(
        raw_extracted,
        db=db,
        principal=principal,
        settings=settings,
        source_context=f"file_hub:{safe_name}",
        auto_vault=True,
    )
    scan_status = "REDACTED" if interception.redaction_count > 0 else "CLEAN"
    if interception.warnings:
        meta["security_warnings"] = interception.warnings
    if interception.secrets_vaulted:
        meta["secrets_vaulted"] = interception.secrets_vaulted
    meta["prompt_injection_guard"] = "TAGGED_AS_UNTRUSTED_DATA"
    meta["storage_backend"] = adapter.backend_name
    meta["private_bucket"] = True
    meta["deleted"] = False
    meta["folder"] = _safe_folder(folder)

    rec = FileRecord(
        file_id=file_id,
        tenant_id=principal.tenant_id,
        filename=safe_name,
        mime_type=(mime_type or "application/octet-stream")[:120],
        size_bytes=len(raw_bytes),
        sha256_hash=sha256_hex,
        direction="UPLOAD",
        storage_path=storage_ref,
        scan_status=scan_status,
        secrets_redacted=interception.redaction_count,
        untrusted_content_tagged=True,
        extracted_text=interception.sanitized_text,
        metadata_json=json.dumps(meta, default=str),
        project_id=project_id,
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FILE_HUB_UPLOAD",
        resource=file_id,
        outcome=f"{safe_name}|bytes={len(raw_bytes)}|scan={scan_status}|backend={adapter.backend_name}|folder={meta['folder']}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_file(rec, include_text=True)


def generate_and_store_file(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    filename: str,
    content_bytes: bytes,
    mime_type: str = "text/plain",
    project_id: str | None = None,
    folder: str | None = None,
    metadata: dict[str, Any] | None = None,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    """Persist an ULTRON-generated artifact via StorageAdapter (Supabase Storage in prod, Local in dev)."""
    safe_name = _safe_filename(filename)
    sha256_hex = hashlib.sha256(content_bytes).hexdigest()
    file_id = f"fil_{uuid.uuid4().hex[:14]}"
    adapter = storage or get_storage_adapter(settings)
    storage_ref = adapter.upload_bytes(
        tenant_id=principal.tenant_id,
        object_key=f"{file_id}_{safe_name}",
        data=content_bytes,
        mime_type=mime_type,
    )

    extracted = ""
    if Path(safe_name).suffix.lower() in TEXT_EXTENSIONS:
        extracted = content_bytes.decode("utf-8", errors="replace")[:50_000]

    meta = dict(metadata or {})
    meta["storage_backend"] = adapter.backend_name
    meta["private_bucket"] = True
    meta["deleted"] = False
    meta["folder"] = _safe_folder(folder or meta.get("folder") or "Generated")

    rec = FileRecord(
        file_id=file_id,
        tenant_id=principal.tenant_id,
        filename=safe_name,
        mime_type=mime_type[:120],
        size_bytes=len(content_bytes),
        sha256_hash=sha256_hex,
        direction="GENERATED",
        storage_path=storage_ref,
        scan_status="CLEAN",
        secrets_redacted=0,
        untrusted_content_tagged=False,
        extracted_text=extracted,
        metadata_json=json.dumps(meta, default=str),
        project_id=project_id,
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FILE_HUB_GENERATED",
        resource=file_id,
        outcome=f"{safe_name}|bytes={len(content_bytes)}|backend={adapter.backend_name}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_file(rec, include_text=False)


def create_zip_bundle_file(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    archive_name: str,
    files_map: dict[str, str],
    project_id: str | None = None,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in sorted(files_map.items()):
            clean_rel = rel_path.lstrip("/").replace("..", "")
            zf.writestr(clean_rel, content.encode("utf-8"))
    zip_name = archive_name if archive_name.endswith(".zip") else f"{archive_name}.zip"
    return generate_and_store_file(
        db,
        principal=principal,
        settings=settings,
        filename=zip_name,
        content_bytes=buf.getvalue(),
        mime_type="application/zip",
        project_id=project_id,
        metadata={"archived_files": sorted(files_map.keys())},
        storage=storage,
    )


def download_file_bytes(
    db: Session,
    *,
    tenant_id: str,
    file_id: str,
    settings: Settings,
    storage: BaseStorageAdapter | None = None,
) -> tuple[FileRecord, bytes]:
    rec = get_file_record(db, tenant_id=tenant_id, file_id=file_id)
    meta = json.loads(rec.metadata_json or "{}")
    if meta.get("deleted"):
        raise NotFoundError(f"File '{file_id}' has been soft-deleted. Restore it before downloading.")
    adapter = storage or get_storage_adapter(settings)
    raw = adapter.download_bytes(tenant_id=tenant_id, storage_ref=rec.storage_path)
    return rec, raw


def create_signed_file_url(
    db: Session,
    *,
    principal: Principal,
    file_id: str,
    settings: Settings,
    expires_in_seconds: int = 300,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    meta = json.loads(rec.metadata_json or "{}")
    if meta.get("deleted"):
        raise NotFoundError(f"File '{file_id}' is soft-deleted.")
    adapter = storage or get_storage_adapter(settings)
    signed = adapter.create_signed_url(
        tenant_id=principal.tenant_id,
        file_id=rec.file_id,
        storage_ref=rec.storage_path,
        expires_in_seconds=expires_in_seconds,
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FILE_HUB_SIGNED_URL_ISSUED",
        resource=rec.file_id,
        outcome=f"ttl={signed['expires_in_seconds']}s|backend={signed['storage_backend']}",
    )
    db.commit()
    return {"file_id": rec.file_id, "filename": rec.filename, **signed}


def download_via_signed_token(
    db: Session,
    *,
    token: str,
    settings: Settings,
    storage: BaseStorageAdapter | None = None,
) -> tuple[FileRecord, bytes]:
    claims = verify_local_download_token(token, secret_key=settings.jwt_secret.get_secret_value())
    return download_file_bytes(
        db,
        tenant_id=str(claims["tid"]),
        file_id=str(claims["fid"]),
        settings=settings,
        storage=storage,
    )


def soft_delete_file(
    db: Session,
    *,
    principal: Principal,
    file_id: str,
    settings: Settings,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    meta = json.loads(rec.metadata_json or "{}")
    if meta.get("deleted"):
        raise ConflictError(f"File '{file_id}' is already deleted.")
    adapter = storage or get_storage_adapter(settings)
    original_ref = rec.storage_path
    trash_ref = adapter.soft_delete(tenant_id=principal.tenant_id, storage_ref=original_ref)
    meta["deleted"] = True
    meta["original_storage_path"] = original_ref
    rec.storage_path = trash_ref
    rec.metadata_json = json.dumps(meta, default=str)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FILE_HUB_SOFT_DELETED",
        resource=rec.file_id,
        outcome=rec.filename,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_file(rec, include_text=False)


def restore_file(
    db: Session,
    *,
    principal: Principal,
    file_id: str,
    settings: Settings,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    meta = json.loads(rec.metadata_json or "{}")
    if not meta.get("deleted"):
        raise ConflictError(f"File '{file_id}' is not deleted.")
    original_ref = meta.get("original_storage_path")
    if not original_ref:
        raise NotFoundError("Original storage path missing; file cannot be restored.")
    adapter = storage or get_storage_adapter(settings)
    restored_ref = adapter.restore(
        tenant_id=principal.tenant_id,
        trash_ref=rec.storage_path,
        original_ref=original_ref,
    )
    meta["deleted"] = False
    rec.storage_path = restored_ref
    rec.metadata_json = json.dumps(meta, default=str)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FILE_HUB_RESTORED",
        resource=rec.file_id,
        outcome=rec.filename,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_file(rec, include_text=False)


def update_file_metadata(
    db: Session,
    *,
    principal: Principal,
    file_id: str,
    filename: str | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    """Rename a stored file and/or move it to another folder with tenant isolation and audit logging."""
    rec = get_file_record(db, tenant_id=principal.tenant_id, file_id=file_id)
    meta = json.loads(rec.metadata_json or "{}")
    if meta.get("deleted"):
        raise ConflictError(f"File '{file_id}' is soft-deleted; restore it before editing.")

    changes: list[str] = []
    if filename is not None and filename.strip():
        new_name = _safe_filename(filename)
        ext = Path(new_name).suffix.lower()
        if ext in BLOCKED_EXTENSIONS:
            raise ValidationError(f"Executable file extension '{ext}' is blocked by AEGIS file intake policy.")
        if new_name != rec.filename:
            changes.append(f"rename:{rec.filename}->{new_name}")
            rec.filename = new_name
    if folder is not None:
        new_folder = _safe_folder(folder)
        prev_folder = meta.get("folder", "General")
        if new_folder != prev_folder:
            changes.append(f"folder:{prev_folder}->{new_folder}")
            meta["folder"] = new_folder

    rec.metadata_json = json.dumps(meta, default=str)
    if changes:
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="FILE_HUB_UPDATED",
            resource=rec.file_id,
            outcome=";".join(changes),
        )
    db.commit()
    db.refresh(rec)
    return _serialize_file(rec, include_text=True)


def load_files_for_neon(
    db: Session,
    *,
    tenant_id: str,
    file_ids: list[str],
    settings: Settings,
    storage: BaseStorageAdapter | None = None,
) -> dict[str, Any]:
    """Load tenant-isolated uploaded files into Gemini multimodal inlineData parts + extracted document excerpts."""
    import base64

    multimodal_parts: list[dict[str, Any]] = []
    document_excerpts: list[dict[str, Any]] = []
    attached_files: list[dict[str, Any]] = []

    seen: set[str] = set()
    for fid in file_ids[:8]:
        clean_id = (fid or "").strip()
        if not clean_id or clean_id in seen:
            continue
        seen.add(clean_id)
        rec, raw = download_file_bytes(
            db,
            tenant_id=tenant_id,
            file_id=clean_id,
            settings=settings,
            storage=storage,
        )
        ext = Path(rec.filename).suffix.lower()
        is_image = rec.mime_type.lower().startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        if is_image:
            effective_mime = rec.mime_type if rec.mime_type.lower().startswith("image/") else (
                "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/gif" if ext == ".gif" else "image/jpeg"
            )
            multimodal_parts.append(
                {
                    "inlineData": {
                        "mimeType": effective_mime,
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                }
            )
            attached_files.append(
                {
                    "file_id": rec.file_id,
                    "filename": rec.filename,
                    "mime_type": effective_mime,
                    "size_bytes": rec.size_bytes,
                    "analysis_mode": "multimodal_inline_image",
                }
            )
        else:
            excerpt = (rec.extracted_text or "").strip()[:12000]
            document_excerpts.append(
                {
                    "file_id": rec.file_id,
                    "filename": rec.filename,
                    "mime_type": rec.mime_type,
                    "scan_status": rec.scan_status,
                    "content": excerpt or "(Binary file without extractable text)",
                }
            )
            attached_files.append(
                {
                    "file_id": rec.file_id,
                    "filename": rec.filename,
                    "mime_type": rec.mime_type,
                    "size_bytes": rec.size_bytes,
                    "analysis_mode": "extracted_document_text",
                    "chars_provided": len(excerpt),
                }
            )

    return {
        "multimodal_parts": multimodal_parts,
        "document_excerpts": document_excerpts,
        "attached_files": attached_files,
    }


def list_files(
    db: Session,
    *,
    tenant_id: str,
    direction: str | None = None,
    project_id: str | None = None,
    folder: str | None = None,
    search: str | None = None,
    include_deleted: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(FileRecord).where(FileRecord.tenant_id == tenant_id)
    if direction:
        stmt = stmt.where(FileRecord.direction == direction.upper())
    if project_id:
        stmt = stmt.where(FileRecord.project_id == project_id)
    rows = db.execute(stmt.order_by(FileRecord.created_at.desc()).limit(limit)).scalars().all()
    items = []
    folder_clean = folder.strip().lower() if folder else ""
    search_clean = search.strip().lower() if search else ""
    for r in rows:
        meta = json.loads(r.metadata_json or "{}")
        if not include_deleted and meta.get("deleted"):
            continue
        item_folder = str(meta.get("folder") or "General")
        if folder_clean and folder_clean != "all" and item_folder.lower() != folder_clean:
            continue
        if search_clean and search_clean not in r.filename.lower() and search_clean not in item_folder.lower():
            continue
        items.append(_serialize_file(r, include_text=False))
    return items


def get_file_record(db: Session, *, tenant_id: str, file_id: str) -> FileRecord:
    rec = db.execute(
        select(FileRecord).where(FileRecord.file_id == file_id, FileRecord.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"File '{file_id}' not found.")
    return rec


def _serialize_file(f: FileRecord, *, include_text: bool = False) -> dict[str, Any]:
    meta = json.loads(f.metadata_json or "{}")
    ext = Path(f.filename).suffix.lower()
    is_image = f.mime_type.lower().startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    data: dict[str, Any] = {
        "file_id": f.file_id,
        "filename": f.filename,
        "folder": str(meta.get("folder") or "General"),
        "mime_type": f.mime_type,
        "is_image": is_image,
        "size_bytes": f.size_bytes,
        "sha256_hash": f.sha256_hash,
        "direction": f.direction,
        "scan_status": f.scan_status,
        "secrets_redacted": f.secrets_redacted,
        "untrusted_content_tagged": f.untrusted_content_tagged,
        "deleted": bool(meta.get("deleted", False)),
        "is_deleted": bool(meta.get("deleted", False)),
        "storage_backend": meta.get("storage_backend", "local_disk"),
        "metadata": meta,
        "project_id": f.project_id,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat(),
        "download_url": f"/api/v1/files/{f.file_id}/download",
        "preview_url": f"/api/v1/files/{f.file_id}/preview",
    }
    if include_text:
        data["extracted_text"] = f.extracted_text
    return data
