"""Mocked transport tests for Google Ecosystem (Drive, Gmail, Calendar, Docs, Sheets, Slides, Cloud), Web Research, Gemini Nov 2026 features, GitHub Engineering, Vercel, and Cloudflare."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import AuthorizationError
from app.integrations.cloudflare import CloudflareClient
from app.integrations.gemini import GeminiClient
from app.integrations.github_client import GitHubEngineeringClient
from app.integrations.google_workspace import (
    GoogleCalendarAPI,
    GoogleCloudAPI,
    GoogleDocsAPI,
    GoogleDriveAPI,
    GoogleGmailAPI,
    GoogleSheetsAPI,
    GoogleSlidesAPI,
)
from app.integrations.vercel import VercelClient
from app.integrations.web_research import WebResearchClient


def test_google_workspace_and_cloud_clients_mocked() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "drive/v3/files" in url and req.method == "GET":
            return httpx.Response(200, json={"files": [{"id": "f1", "name": "ULTRON Blueprint"}]})
        if "drive/v3/files" in url and req.method == "POST":
            return httpx.Response(200, json={"id": "fld1", "name": "Projects"})
        if "gmail/v1/users/me/messages" in url and req.method == "GET":
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if "gmail/v1/users/me/drafts" in url:
            return httpx.Response(200, json={"id": "drf1"})
        if "gmail/v1/users/me/messages/send" in url:
            return httpx.Response(200, json={"id": "sent1"})
        if "calendar/v3/users/me/calendarList" in url:
            return httpx.Response(200, json={"items": [{"id": "primary"}]})
        if "calendar/v3/freeBusy" in url:
            return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})
        if "docs.googleapis.com/v1/documents" in url and req.method == "POST":
            return httpx.Response(200, json={"documentId": "doc1", "title": "Report"})
        if "sheets.googleapis.com/v4/spreadsheets" in url and req.method == "POST":
            return httpx.Response(200, json={"spreadsheetId": "sh1"})
        if "sheets.googleapis.com/v4/spreadsheets/sh1/values" in url:
            return httpx.Response(200, json={"values": [["Metric", "Value"], ["MRR", "5000"]]})
        if "slides.googleapis.com/v1/presentations" in url and req.method == "POST":
            return httpx.Response(200, json={"presentationId": "sl1"})
        if "cloudresourcemanager.googleapis.com/v3/projects:search" in url:
            return httpx.Response(200, json={"projects": [{"projectId": "ultron-prod-2026"}]})
        if "serviceusage.googleapis.com/v1/projects/" in url:
            return httpx.Response(200, json={"services": [{"name": "aiplatform.googleapis.com"}]})
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))

    drive = GoogleDriveAPI("tok", http_client=http)
    assert len(drive.search_files("ULTRON")) == 1
    assert drive.create_folder("Projects")["id"] == "fld1"

    gmail = GoogleGmailAPI("tok", http_client=http)
    assert len(gmail.search_messages("invoice")) == 1
    assert gmail.create_draft(to="a@b.com", subject="Hi", body="Hello")["id"] == "drf1"
    # Sending without approval_verified=True MUST raise AuthorizationError
    with pytest.raises(AuthorizationError):
        gmail.send_message(to="a@b.com", subject="Hi", body="Hello")
    assert gmail.send_message(to="a@b.com", subject="Hi", body="Hello", approval_verified=True)["id"] == "sent1"

    cal = GoogleCalendarAPI("tok", http_client=http)
    assert len(cal.list_calendars()) == 1
    assert "calendars" in cal.check_availability(time_min_iso="2026-11-22T00:00:00Z", time_max_iso="2026-11-23T00:00:00Z")

    assert GoogleDocsAPI("tok", http_client=http).create_document("Report")["documentId"] == "doc1"
    sheets = GoogleSheetsAPI("tok", http_client=http)
    assert sheets.create_spreadsheet("KPIs")["spreadsheetId"] == "sh1"
    assert len(sheets.read_values("sh1", "A1:B2")["values"]) == 2
    assert GoogleSlidesAPI("tok", http_client=http).create_presentation("Deck")["presentationId"] == "sl1"

    gcp = GoogleCloudAPI("tok", http_client=http)
    assert gcp.list_projects()[0]["projectId"] == "ultron-prod-2026"
    assert len(gcp.list_enabled_services("ultron-prod-2026")) == 1


def test_gmail_send_route_enforces_approval_gate(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/google/gmail/send-request",
        headers=auth_headers["operator"],
        json={"to": "ceo@example.com", "subject": "Board Update", "body": "Quarterly summary"},
    )
    assert resp.status_code == 200
    assert resp.json()["gated"] is True
    assert resp.json()["status"] == "WAITING_FOR_APPROVAL"


def test_gemini_nov2026_discovery_function_calling_and_multimodal() -> None:
    cfg = Settings(ULTRON_ENV="test", GEMINI_API_KEY="AIzaTestNov2026Key1234567890")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"models": [{"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "supportedGenerationMethods": ["generateContent"]}]},
            )
        if ":generateContent" in req.url.path:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Calling diagnostics tool."},
                                    {"functionCall": {"name": "system_diagnostics", "args": {}}},
                                ]
                            }
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 12, "totalTokenCount": 42},
                },
            )
        return httpx.Response(404)

    g = GeminiClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    discovered = g.list_models()
    assert discovered[0]["id"] == "gemini-3.8-flash"

    res = g.generate_content(
        prompt="Inspect image and run diagnostics",
        model="gemini-3.8-flash",
        function_declarations=[{"name": "system_diagnostics", "description": "Check system"}],
        multimodal_parts=[{"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}}],
    )
    assert res["function_calls"][0]["name"] == "system_diagnostics"
    assert res["usage"]["total_tokens"] == 42


def test_github_engineering_protected_branch_and_cloud_clients() -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        GITHUB_TOKEN="ghp_test_token_123",
        VERCEL_TOKEN="vrc_test_token",
        VERCEL_PROJECT_ID="prj_123",
        CLOUDFLARE_API_TOKEN="cf_test_token",
        CLOUDFLARE_ACCOUNT_ID="acc_123",
        CLOUDFLARE_ZONE_ID="zone_123",
    )

    def gh_handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.endswith("/user"):
            return httpx.Response(200, json={"login": "epejuwon-sketch"})
        if "/contents/" in url and req.method == "GET":
            return httpx.Response(200, json={"path": "README.md", "sha": "abc", "size": 8, "content": base64.b64encode(b"# ULTRON").decode()})
        if "/pulls" in url and req.method == "POST":
            return httpx.Response(201, json={"number": 2, "html_url": "https://github.com/epejuwon-sketch/ULTRON/pull/2"})
        if "/actions/runs" in url:
            return httpx.Response(200, json={"workflow_runs": [{"id": 99, "conclusion": "success"}]})
        return httpx.Response(200, json=[])

    gh = GitHubEngineeringClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(gh_handler)))
    assert gh.verify_live().live_verified is True
    assert gh.get_file_content("epejuwon-sketch/ULTRON", "README.md")["content"] == "# ULTRON"
    assert len(gh.list_workflow_runs("epejuwon-sketch/ULTRON")) == 1
    assert gh.create_pull_request("epejuwon-sketch/ULTRON", title="Feat", head="feat/x")["number"] == 2

    # Direct write to protected main branch MUST be blocked
    with pytest.raises(AuthorizationError):
        gh.upsert_file("epejuwon-sketch/ULTRON", path="README.md", branch="main", content="x", message="bad")
    with pytest.raises(AuthorizationError):
        gh.create_release("epejuwon-sketch/ULTRON", tag_name="v1.0", name="v1.0")

    # Vercel & Cloudflare extended methods
    v = VercelClient(
        cfg,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"projects": [{"id": "prj_123"}], "deployments": [{"uid": "d1"}], "domains": [{"name": "ultron.dev"}], "envs": [{"id": "e1", "key": "ULTRON_ENV", "target": ["production"], "type": "plain"}]})
            )
        ),
    )
    assert len(v.list_projects()) == 1
    assert len(v.list_deployments()) == 1
    assert v.list_env_metadata()[0]["key"] == "ULTRON_ENV"

    cf = CloudflareClient(
        cfg,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"success": True, "result": [{"id": "z1"}]}))
        ),
    )
    assert len(cf.list_zones()) == 1
    assert len(cf.list_dns_records()) == 1
    assert len(cf.list_workers()) == 1


def test_web_research_citations_and_ssrf_protection() -> None:
    cfg = Settings(ULTRON_ENV="test")

    def web_handler(req: httpx.Request) -> httpx.Response:
        if "wikipedia.org" in str(req.url):
            return httpx.Response(
                200,
                json={"query": {"search": [{"title": "FastAPI", "snippet": "Modern Python web framework"}]}},
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>ULTRON Doc</title></head><body><script>evil()</script><p>Verified info.</p></body></html>",
        )

    client = WebResearchClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(web_handler)))
    res = client.search("FastAPI")
    assert len(res["verified_sources"]) == 1
    assert res["citations"][0].startswith("https://en.wikipedia.org/wiki/")

    page = client.fetch_and_extract("https://example.com/doc")
    assert page["title"] == "ULTRON Doc"
    assert "Verified info." in page["extracted_text"]
    assert "evil()" not in page["extracted_text"]
