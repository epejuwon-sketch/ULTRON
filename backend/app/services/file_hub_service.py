"""FILE HUB — Two-Way Secure File Intake, Extraction, Secret Redaction & Artifact Generation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.db.models import FileRecord
from app.db.repositories import append_audit_log

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per upload

TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".tsx", ".jsx",
        ".html", ".css", ".sql", ".yaml", ".yml", ".toml", ".xml", ".env", ".sh", ".log",
    }
)

BLOCKED_EXTENSIONS = frozenset({".exe", ".dll", ".bat", ".cmd", ".msi", ".com", ".scr", ".vbs"})


def _storage_root(settings: Settings) -> Path:
    base = Path(__file__).resolve().parents[3] / "data" / "file_hub"
    base.mkdir(parents=True, exist_ok=True)
    return base


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
                    root = ET.fromstring(zf.read("word/document.xml"))
                    extracted = " ".join(elem.text for elem in root.iter() if elem.text)
                    meta["extractor"] = "docx_xml"
                    return extracted[:100_000], meta
                if ext == ".pptx":
                    slides = [n for n in sorted(names) if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
                    parts = []
                    for s in slides:
                        root = ET.fromstring(zf.read(s))
                        parts.append(" ".join(e.text for e in root.iter() if e.text))
                    meta["extractor"] = "pptx_xml"
                    meta["slide_count"] = len(slides)
                    return "\n".join(parts)[:100_000], meta
                if ext == ".xlsx":
                    shared = []
                    if "xl/sharedStrings.xml" in names:
                        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                        shared = [e.text for e in root.iter() if e.text]
                    meta["extractor"] = "xlsx_xml"
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


def ingest_uploaded_file(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    filename: str,
    raw_bytes: bytes,
    mime_type: str = "application/octet-stream",
    project_id: str | None = None,
) -> dict[str, Any]:
    """Validate, hash, scan, redact secrets, extract text, tag as untrusted, and persist uploaded file."""
    safe_name = _safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"Executable file extension '{ext}' is blocked by AEGIS file intake policy.")
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ValidationError(f"File exceeds maximum allowed size of {MAX_FILE_BYTES // (1024 * 1024)} MB.")

    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    file_id = f"fil_{uuid.uuid4().hex[:14]}"
    tenant_dir = _storage_root(settings) / principal.tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    disk_path = tenant_dir / f"{file_id}_{safe_name}"
    disk_path.write_bytes(raw_bytes)

    raw_extracted, meta = _extract_content(safe_name, raw_bytes)

    # Run VAULT secret interception on extracted text so secrets in uploaded files never leak to AI prompts!
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

    rec = FileRecord(
        file_id=file_id,
        tenant_id=principal.tenant_id,
        filename=safe_name,
        mime_type=(mime_type or "application/octet-stream")[:120],
        size_bytes=len(raw_bytes),
        sha256_hash=sha256_hex,
        direction="UPLOAD",
        storage_path=str(disk_path),
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
        outcome=f"{safe_name}|bytes={len(raw_bytes)}|scan={scan_status}",
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
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an ULTRON-generated artifact (report, CSV, JSON, code, ZIP archive) for download."""
    safe_name = _safe_filename(filename)
    sha256_hex = hashlib.sha256(content_bytes).hexdigest()
    file_id = f"fil_{uuid.uuid4().hex[:14]}"
    tenant_dir = _storage_root(settings) / principal.tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    disk_path = tenant_dir / f"{file_id}_{safe_name}"
    disk_path.write_bytes(content_bytes)

    extracted = ""
    if Path(safe_name).suffix.lower() in TEXT_EXTENSIONS:
        extracted = content_bytes.decode("utf-8", errors="replace")[:50_000]

    rec = FileRecord(
        file_id=file_id,
        tenant_id=principal.tenant_id,
        filename=safe_name,
        mime_type=mime_type[:120],
        size_bytes=len(content_bytes),
        sha256_hash=sha256_hex,
        direction="GENERATED",
        storage_path=str(disk_path),
        scan_status="CLEAN",
        secrets_redacted=0,
        untrusted_content_tagged=False,
        extracted_text=extracted,
        metadata_json=json.dumps(metadata or {}, default=str),
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
        outcome=f"{safe_name}|bytes={len(content_bytes)}",
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
) -> dict[str, Any]:
    """Package a multi-file dict into a real downloadable ZIP archive in File Hub."""
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
    )


def list_files(
    db: Session,
    *,
    tenant_id: str,
    direction: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(FileRecord).where(FileRecord.tenant_id == tenant_id)
    if direction:
        stmt = stmt.where(FileRecord.direction == direction.upper())
    if project_id:
        stmt = stmt.where(FileRecord.project_id == project_id)
    rows = db.execute(stmt.order_by(FileRecord.created_at.desc()).limit(limit)).scalars().all()
    return [_serialize_file(r, include_text=False) for r in rows]


def get_file_record(db: Session, *, tenant_id: str, file_id: str) -> FileRecord:
    rec = db.execute(
        select(FileRecord).where(FileRecord.file_id == file_id, FileRecord.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"File '{file_id}' not found.")
    return rec


def _serialize_file(f: FileRecord, *, include_text: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "file_id": f.file_id,
        "filename": f.filename,
        "mime_type": f.mime_type,
        "size_bytes": f.size_bytes,
        "sha256_hash": f.sha256_hash,
        "direction": f.direction,
        "scan_status": f.scan_status,
        "secrets_redacted": f.secrets_redacted,
        "untrusted_content_tagged": f.untrusted_content_tagged,
        "metadata": json.loads(f.metadata_json or "{}"),
        "project_id": f.project_id,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat(),
        "download_url": f"/api/v1/files/{f.file_id}/download",
    }
    if include_text:
        data["extracted_text"] = f.extracted_text
    return data
