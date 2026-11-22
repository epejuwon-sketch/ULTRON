"""Official Google Ecosystem API routes: Drive, Gmail, Calendar, Docs, Sheets, Slides, and Google Cloud."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.repositories import append_audit_log
from app.db.session import get_db
from app.integrations.google_workspace import (
    GoogleCalendarAPI,
    GoogleCloudAPI,
    GoogleDocsAPI,
    GoogleDriveAPI,
    GoogleGmailAPI,
    GoogleSheetsAPI,
    GoogleSlidesAPI,
)
from app.routers.deps import require_perm
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.integration_manager import resolve_provider_token

router = APIRouter(prefix="/api/v1/google", tags=["Google Ecosystem"])


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class UploadFileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str
    mime_type: str = "text/plain"


class GmailComposeRequest(BaseModel):
    to: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=32000)


class CalendarEventRequest(BaseModel):
    calendar_id: str = "primary"
    summary: str = Field(min_length=1, max_length=200)
    start_iso: str
    end_iso: str
    description: str = ""


class FreeBusyRequest(BaseModel):
    time_min_iso: str
    time_max_iso: str
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])


class CreateTitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AppendDocRequest(BaseModel):
    text: str = Field(min_length=1, max_length=32000)
    index: int = Field(default=1, ge=1)


class SheetWriteRequest(BaseModel):
    range_a1: str = Field(min_length=2, max_length=80)
    values: list[list[Any]]


# --- Google Drive ---
@router.get("/drive/files")
def api_drive_search(
    q: str = Query(default=""),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_drive", settings=settings)
    files = GoogleDriveAPI(tok).search_files(query=q, page_size=page_size)
    return {"total": len(files), "files": files}


@router.get("/drive/files/{file_id}/read")
def api_drive_read(
    file_id: str,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_drive", settings=settings)
    return GoogleDriveAPI(tok).read_document_text(file_id)


@router.post("/drive/folders")
def api_drive_create_folder(
    body: CreateFolderRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_drive", settings=settings)
    res = GoogleDriveAPI(tok).create_folder(body.name, parent_id=body.parent_id)
    append_audit_log(db, tenant_id=principal.tenant_id, actor=principal.username, action="GOOGLE_DRIVE_FOLDER_CREATED", resource=res.get("id", body.name), outcome="CREATED")
    db.commit()
    return res


@router.post("/drive/upload")
def api_drive_upload(
    body: UploadFileRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_drive", settings=settings)
    return GoogleDriveAPI(tok).upload_text_file(body.name, body.content, mime_type=body.mime_type)


# --- Google Gmail ---
@router.get("/gmail/messages")
def api_gmail_search(
    q: str = Query(default=""),
    max_results: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_gmail", settings=settings)
    msgs = GoogleGmailAPI(tok).search_messages(query=q, max_results=max_results)
    return {"total": len(msgs), "messages": msgs}


@router.get("/gmail/threads/{thread_id}")
def api_gmail_thread(
    thread_id: str,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_gmail", settings=settings)
    return GoogleGmailAPI(tok).read_thread(thread_id)


@router.post("/gmail/drafts")
def api_gmail_draft(
    body: GmailComposeRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_gmail", settings=settings)
    return GoogleGmailAPI(tok).create_draft(to=body.to, subject=body.subject, body=body.body)


@router.post("/gmail/send-request")
def api_gmail_send_request(
    body: GmailComposeRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
) -> dict:
    """Queue an outbound Gmail send behind mandatory ApprovalGate authorization."""
    approval = create_approval_request(
        db,
        tenant_id=principal.tenant_id,
        requested_by=principal.username,
        action_type="GOOGLE_GMAIL_SEND",
        reason=f"Outbound Gmail to '{body.to}' (subject: {body.subject[:80]}) requires explicit authorization.",
        risk_level="HIGH",
        payload=body.model_dump(),
    )
    return {"gated": True, "status": "WAITING_FOR_APPROVAL", "approval": serialize_approval(approval)}


# --- Google Calendar ---
@router.get("/calendar/calendars")
def api_cal_list(
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_calendar", settings=settings)
    cals = GoogleCalendarAPI(tok).list_calendars()
    return {"total": len(cals), "calendars": cals}


@router.get("/calendar/events")
def api_cal_events(
    calendar_id: str = Query(default="primary"),
    q: str = Query(default=""),
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_calendar", settings=settings)
    events = GoogleCalendarAPI(tok).search_events(calendar_id=calendar_id, query=q)
    return {"total": len(events), "events": events}


@router.post("/calendar/events")
def api_cal_create_event(
    body: CalendarEventRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_calendar", settings=settings)
    return GoogleCalendarAPI(tok).create_event(
        calendar_id=body.calendar_id,
        summary=body.summary,
        start_iso=body.start_iso,
        end_iso=body.end_iso,
        description=body.description,
    )


@router.post("/calendar/availability")
def api_cal_freebusy(
    body: FreeBusyRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_calendar", settings=settings)
    return GoogleCalendarAPI(tok).check_availability(
        time_min_iso=body.time_min_iso, time_max_iso=body.time_max_iso, calendar_ids=body.calendar_ids
    )


# --- Google Docs, Sheets, Slides ---
@router.post("/docs")
def api_docs_create(
    body: CreateTitleRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_docs", settings=settings)
    return GoogleDocsAPI(tok).create_document(body.title)


@router.get("/docs/{document_id}")
def api_docs_read(
    document_id: str,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_docs", settings=settings)
    return GoogleDocsAPI(tok).read_document(document_id)


@router.post("/docs/{document_id}/append")
def api_docs_append(
    document_id: str,
    body: AppendDocRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_docs", settings=settings)
    return GoogleDocsAPI(tok).append_text(document_id, body.text, index=body.index)


@router.post("/sheets")
def api_sheets_create(
    body: CreateTitleRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_sheets", settings=settings)
    return GoogleSheetsAPI(tok).create_spreadsheet(body.title)


@router.get("/sheets/{spreadsheet_id}/values")
def api_sheets_read(
    spreadsheet_id: str,
    range_a1: str = Query(default="Sheet1!A1:Z100"),
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_sheets", settings=settings)
    return GoogleSheetsAPI(tok).read_values(spreadsheet_id, range_a1)


@router.put("/sheets/{spreadsheet_id}/values")
def api_sheets_write(
    spreadsheet_id: str,
    body: SheetWriteRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_sheets", settings=settings)
    return GoogleSheetsAPI(tok).write_values(spreadsheet_id, body.range_a1, body.values)


@router.post("/slides")
def api_slides_create(
    body: CreateTitleRequest,
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_slides", settings=settings)
    return GoogleSlidesAPI(tok).create_presentation(body.title)


@router.post("/slides/{presentation_id}/slides")
def api_slides_add(
    presentation_id: str,
    layout: str = Query(default="TITLE_AND_BODY"),
    principal: Principal = Depends(require_perm("tools:execute")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_slides", settings=settings)
    return GoogleSlidesAPI(tok).add_slide(presentation_id, layout=layout)


# --- Google Cloud ---
@router.get("/cloud/projects")
def api_gcp_projects(
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_cloud", settings=settings)
    projects = GoogleCloudAPI(tok).list_projects()
    return {"total": len(projects), "projects": projects}


@router.get("/cloud/projects/{project_id}/services")
def api_gcp_services(
    project_id: str,
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="google_cloud", settings=settings)
    services = GoogleCloudAPI(tok).list_enabled_services(project_id)
    return {"total": len(services), "services": services}
