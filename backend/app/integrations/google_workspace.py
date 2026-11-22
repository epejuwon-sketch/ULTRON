"""Official Google Ecosystem REST clients: Drive, Gmail, Calendar, Docs, Sheets, Slides, and Google Cloud.

Each service requires its own authorized OAuth 2.0 access token with least-privilege scopes;
this module never assumes one Google credential grants access to every Google product.
"""

from __future__ import annotations

import base64
import time
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.exceptions import AuthorizationError, IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class _BaseGoogleAPI:
    provider_name: str
    verify_url: str
    verify_params: dict[str, Any] = {}

    def __init__(self, access_token: str | None, http_client: httpx.Client | None = None) -> None:
        self._token = (access_token or "").strip()
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": content_type,
        }

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str = "application/json",
        timeout: float = 12.0,
    ) -> httpx.Response:
        if not self.is_configured():
            raise IntegrationError(f"{self.provider_name} is not connected with an authorized OAuth token.")
        try:
            if self._client is not None:
                resp = self._client.request(
                    method,
                    url,
                    headers=self._headers(content_type),
                    params=params,
                    json=json_body,
                    content=content,
                    timeout=timeout,
                )
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(
                        method,
                        url,
                        headers=self._headers(content_type),
                        params=params,
                        json=json_body,
                        content=content,
                    )
        except httpx.HTTPError as exc:
            raise IntegrationError(f"{self.provider_name} network error: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"{self.provider_name} failed: {classify_http_error(resp.status_code)}")
        return resp

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return IntegrationStatus(
                provider=self.provider_name,
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                detail=f"{self.provider_name} OAuth token not connected.",
            )
        started = time.perf_counter()
        try:
            resp = self._request("GET", self.verify_url, params=self.verify_params or None, timeout=timeout_seconds)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return IntegrationStatus(
                provider=self.provider_name,
                configured=True,
                capability_state=HonestCapabilityState.AVAILABLE,
                live_verified=True,
                endpoint=self.verify_url,
                latency_ms=latency_ms,
                detail=f"{self.provider_name} live verification passed (HTTP {resp.status_code}).",
            )
        except IntegrationError as exc:
            return IntegrationStatus(
                provider=self.provider_name,
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=self.verify_url,
                detail=str(exc),
            )


class GoogleDriveAPI(_BaseGoogleAPI):
    provider_name = "google_drive"
    BASE = "https://www.googleapis.com/drive/v3"
    UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
    verify_url = "https://www.googleapis.com/drive/v3/about"
    verify_params = {"fields": "user"}

    def search_files(self, query: str = "", page_size: int = 20) -> list[dict[str, Any]]:
        q = f"trashed = false and name contains '{query.replace(chr(39), '')}'" if query else "trashed = false"
        resp = self._request(
            "GET",
            f"{self.BASE}/files",
            params={"q": q, "pageSize": min(100, page_size), "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"},
        )
        return resp.json().get("files", [])

    def read_document_text(self, file_id: str, export_mime: str = "text/plain") -> dict[str, Any]:
        meta = self._request("GET", f"{self.BASE}/files/{file_id}", params={"fields": "id,name,mimeType"}).json()
        mime = meta.get("mimeType", "")
        if mime.startswith("application/vnd.google-apps."):
            resp = self._request("GET", f"{self.BASE}/files/{file_id}/export", params={"mimeType": export_mime})
        else:
            resp = self._request("GET", f"{self.BASE}/files/{file_id}", params={"alt": "media"})
        return {"file_id": file_id, "name": meta.get("name"), "mime_type": mime, "content": resp.text}

    def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        return self._request("POST", f"{self.BASE}/files", json_body=body).json()

    def upload_text_file(self, name: str, content: str, mime_type: str = "text/plain") -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"{self.UPLOAD_BASE}/files",
            params={"uploadType": "media"},
            content=content.encode("utf-8"),
            content_type=mime_type,
        )
        data = resp.json()
        file_id = data.get("id")
        if file_id and name:
            self._request("PATCH", f"{self.BASE}/files/{file_id}", json_body={"name": name})
            data["name"] = name
        return data


class GoogleGmailAPI(_BaseGoogleAPI):
    provider_name = "google_gmail"
    BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
    verify_url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"

    def search_messages(self, query: str = "", max_results: int = 20) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"maxResults": min(50, max_results)}
        if query:
            params["q"] = query
        return self._request("GET", f"{self.BASE}/messages", params=params).json().get("messages", [])

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.BASE}/threads/{thread_id}", params={"format": "full"}).json()

    def _build_raw_mime(self, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    def create_draft(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        raw = self._build_raw_mime(to, subject, body)
        return self._request("POST", f"{self.BASE}/drafts", json_body={"message": {"raw": raw}}).json()

    def send_message(self, *, to: str, subject: str, body: str, approval_verified: bool = False) -> dict[str, Any]:
        if not approval_verified:
            raise AuthorizationError("Gmail send_message requires explicit ApprovalGate authorization (`approval_verified=True`).")
        raw = self._build_raw_mime(to, subject, body)
        return self._request("POST", f"{self.BASE}/messages/send", json_body={"raw": raw}).json()

    def modify_labels(self, message_id: str, add_labels: list[str] | None = None, remove_labels: list[str] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.BASE}/messages/{message_id}/modify",
            json_body={"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []},
        ).json()


class GoogleCalendarAPI(_BaseGoogleAPI):
    provider_name = "google_calendar"
    BASE = "https://www.googleapis.com/calendar/v3"
    verify_url = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
    verify_params = {"maxResults": 1}

    def list_calendars(self) -> list[dict[str, Any]]:
        return self._request("GET", f"{self.BASE}/users/me/calendarList").json().get("items", [])

    def search_events(self, calendar_id: str = "primary", query: str = "", max_results: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"maxResults": min(100, max_results), "singleEvents": "true", "orderBy": "startTime"}
        if query:
            params["q"] = query
        return self._request("GET", f"{self.BASE}/calendars/{calendar_id}/events", params=params).json().get("items", [])

    def create_event(self, *, calendar_id: str = "primary", summary: str, start_iso: str, end_iso: str, description: str = "") -> dict[str, Any]:
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        return self._request("POST", f"{self.BASE}/calendars/{calendar_id}/events", json_body=body).json()

    def update_event(self, *, calendar_id: str = "primary", event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"{self.BASE}/calendars/{calendar_id}/events/{event_id}", json_body=patch).json()

    def check_availability(self, *, time_min_iso: str, time_max_iso: str, calendar_ids: list[str] | None = None) -> dict[str, Any]:
        items = [{"id": cid} for cid in (calendar_ids or ["primary"])]
        return self._request(
            "POST",
            f"{self.BASE}/freeBusy",
            json_body={"timeMin": time_min_iso, "timeMax": time_max_iso, "items": items},
        ).json()


class GoogleDocsAPI(_BaseGoogleAPI):
    provider_name = "google_docs"
    BASE = "https://docs.googleapis.com/v1"
    verify_url = "https://www.googleapis.com/oauth2/v3/tokeninfo"

    def create_document(self, title: str) -> dict[str, Any]:
        return self._request("POST", f"{self.BASE}/documents", json_body={"title": title}).json()

    def read_document(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.BASE}/documents/{document_id}").json()

    def append_text(self, document_id: str, text: str, index: int = 1) -> dict[str, Any]:
        body = {"requests": [{"insertText": {"location": {"index": index}, "text": text}}]}
        return self._request("POST", f"{self.BASE}/documents/{document_id}:batchUpdate", json_body=body).json()


class GoogleSheetsAPI(_BaseGoogleAPI):
    provider_name = "google_sheets"
    BASE = "https://sheets.googleapis.com/v4"
    verify_url = "https://www.googleapis.com/oauth2/v3/tokeninfo"

    def create_spreadsheet(self, title: str) -> dict[str, Any]:
        return self._request("POST", f"{self.BASE}/spreadsheets", json_body={"properties": {"title": title}}).json()

    def read_values(self, spreadsheet_id: str, range_a1: str) -> dict[str, Any]:
        return self._request("GET", f"{self.BASE}/spreadsheets/{spreadsheet_id}/values/{range_a1}").json()

    def write_values(self, spreadsheet_id: str, range_a1: str, values: list[list[Any]]) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"{self.BASE}/spreadsheets/{spreadsheet_id}/values/{range_a1}",
            params={"valueInputOption": "USER_ENTERED"},
            json_body={"range": range_a1, "majorDimension": "ROWS", "values": values},
        ).json()


class GoogleSlidesAPI(_BaseGoogleAPI):
    provider_name = "google_slides"
    BASE = "https://slides.googleapis.com/v1"
    verify_url = "https://www.googleapis.com/oauth2/v3/tokeninfo"

    def create_presentation(self, title: str) -> dict[str, Any]:
        return self._request("POST", f"{self.BASE}/presentations", json_body={"title": title}).json()

    def get_presentation(self, presentation_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.BASE}/presentations/{presentation_id}").json()

    def add_slide(self, presentation_id: str, layout: str = "TITLE_AND_BODY") -> dict[str, Any]:
        body = {"requests": [{"createSlide": {"slideLayoutReference": {"predefinedLayout": layout}}}]}
        return self._request("POST", f"{self.BASE}/presentations/{presentation_id}:batchUpdate", json_body=body).json()


class GoogleCloudAPI(_BaseGoogleAPI):
    provider_name = "google_cloud"
    CRM_BASE = "https://cloudresourcemanager.googleapis.com/v3"
    SVC_BASE = "https://serviceusage.googleapis.com/v1"
    verify_url = "https://cloudresourcemanager.googleapis.com/v3/projects:search"
    verify_params = {"pageSize": 5}

    def list_projects(self, page_size: int = 20) -> list[dict[str, Any]]:
        return self._request("GET", f"{self.CRM_BASE}/projects:search", params={"pageSize": page_size}).json().get("projects", [])

    def list_enabled_services(self, project_id: str, page_size: int = 50) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"{self.SVC_BASE}/projects/{project_id}/services",
            params={"filter": "state:ENABLED", "pageSize": page_size},
        ).json().get("services", [])
