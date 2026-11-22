"""End-to-end production readiness acceptance tests for ULTRON OS 2026.

Covers:
1. Natural-language human output enforcement & sanitization (no raw JSON/dicts/HTML/stack traces).
2. Automatic live web research detection, DuckDuckGo HTML parsing, pricing taxonomy
   (MSRP, asking prices, auctions, estimated market value) and Lamborghini Aventador SVJ acceptance test.
3. Two-way File & Image Hub: folders, search, rename/move, inline visual preview,
   Generate ZIP bundle, cross-tenant isolation, and multimodal Gemini attachment ingestion
   (real PNG bytes as inlineData + PDF text sent to Gemini).
4. Uniform data provenance fields and ApprovalGate immutability.
"""

from __future__ import annotations

import base64
import io
import zipfile
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.web_research import _DuckDuckGoResultParser
from app.services.research_intelligence import (
    detect_research_intent,
    sanitize_user_facing_text,
)

# Valid 1x1 red PNG bytes
SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _make_minimal_pdf(text: str) -> bytes:
    """Create a valid minimal single-page PDF containing readable text."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"trailer << /Root 1 0 R >>\n%%EOF\n",
    ]
    return b"".join(parts)


def test_research_intent_and_natural_language_sanitizer():
    intent = detect_research_intent("How much does a Lamborghini Aventador SVJ cost?")
    assert intent["needs_research"] is True
    assert intent["is_pricing_query"] is True

    probe = detect_research_intent('Reply exactly: "NEON Gemini connection successful."')
    assert probe["needs_research"] is False
    assert probe["is_pricing_query"] is False

    # Sanitizer converts accidental bare JSON object into readable human prose
    raw_json = '{"model": "Lamborghini Aventador SVJ", "msrp_usd": "$517,770", "market_range": "$600,000 - $900,000"}'
    cleaned_json = sanitize_user_facing_text(raw_json)
    assert not cleaned_json.lstrip().startswith("{")
    assert "Lamborghini Aventador SVJ" in cleaned_json
    assert "$517,770" in cleaned_json

    # Sanitizer converts Python dict repr into readable human prose
    raw_dict = "{'status': 'verified', 'estimated_value': '$680,000 USD'}"
    cleaned_dict = sanitize_user_facing_text(raw_dict)
    assert not cleaned_dict.lstrip().startswith("{")
    assert "$680,000 USD" in cleaned_dict

    # Sanitizer strips Python tracebacks and raw HTML tags
    raw_trace = "Summary ready.\nTraceback (most recent call last):\n  File 'app.py', line 12\nRuntimeError: boom"
    cleaned_trace = sanitize_user_facing_text(raw_trace)
    assert "Traceback" not in cleaned_trace
    assert "Summary ready." in cleaned_trace

    raw_html = "<div><h1>Price Guide</h1><p>Asking prices start around $600,000.</p></div>"
    cleaned_html = sanitize_user_facing_text(raw_html)
    assert "<div>" not in cleaned_html
    assert "Asking prices start around $600,000." in cleaned_html


def test_duckduckgo_html_result_parser():
    sample_html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.caranddriver.com%2Flamborghini%2Faventador-svj">
          Lamborghini Aventador SVJ Pricing &amp; Specs — Car and Driver
        </a>
        <a class="result__snippet">Original US MSRP started around $517,770; collector examples trade higher.</a>
      </div>
      <div class="result">
        <a class="result__a" href="https://bringatrailer.com/lamborghini/aventador-svj/">
          Bring a Trailer — Lamborghini Aventador SVJ Auction Results
        </a>
        <div class="result__snippet">Recent verified auction sales ranged from $625,000 to $860,000 USD.</div>
      </div>
    </body></html>
    """
    parser = _DuckDuckGoResultParser()
    parser.feed(sample_html)
    assert len(parser.results) == 2
    assert parser.results[0]["url"] == "https://www.caranddriver.com/lamborghini/aventador-svj"
    assert "Car and Driver" in parser.results[0]["title"]
    assert "$517,770" in parser.results[0]["snippet"]
    assert parser.results[1]["url"] == "https://bringatrailer.com/lamborghini/aventador-svj/"


def test_lamborghini_aventador_svj_natural_language_and_live_research_flow(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """Acceptance Test D: Natural-language grounded answer with pricing breakdown & provenance."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-acceptance-0001")
    get_settings.cache_clear()

    captured_gemini_payloads: list[dict[str, Any]] = []

    def fake_run_research(prompt: str, *, settings, max_results: int = 5, http_client=None) -> dict[str, Any]:
        return {
            "query": prompt,
            "provider": "duckduckgo_public_web",
            "retrieved_at": "2026-11-22T20:00:00+00:00",
            "verified_sources": [
                {
                    "title": "Car and Driver — Lamborghini Aventador SVJ Review & MSRP",
                    "url": "https://www.caranddriver.com/lamborghini/aventador-svj",
                    "domain": "caranddriver.com",
                    "snippet": "Original US MSRP started at $517,770 for the Coupe and $573,966 for the Roadster.",
                    "credibility": "established_source",
                    "retrieved_at": "2026-11-22T20:00:00+00:00",
                },
                {
                    "title": "Bring a Trailer — Lamborghini Aventador SVJ Auction Results",
                    "url": "https://bringatrailer.com/lamborghini/aventador-svj/",
                    "domain": "bringatrailer.com",
                    "snippet": "Recent US auction sales typically range between $625,000 and $860,000 USD depending on mileage and Roadster trim.",
                    "credibility": "established_source",
                    "retrieved_at": "2026-11-22T20:00:00+00:00",
                },
            ],
            "provenance": {
                "source": "duckduckgo_public_web",
                "retrieved_at": "2026-11-22T20:00:00+00:00",
                "verification_status": "LIVE_VERIFIED",
                "cache_status": "live",
            },
        }

    monkeypatch.setattr("app.services.research_intelligence.run_grounded_web_research", fake_run_research)
    monkeypatch.setattr("app.services.neon_router.run_grounded_web_research", fake_run_research, raising=False)

    natural_answer = (
        "The Lamborghini Aventador SVJ (produced for 2019–2021) trades well above its original factory price in the US market (USD, checked November 2026):\n\n"
        "- Original Manufacturer MSRP: $517,770 USD for the Coupe and $573,966 USD for the Roadster before options.\n"
        "- Current Dealer & Used Asking Prices: Listings generally range from $620,000 to $900,000+ USD depending on mileage, specification, and Roadster vs. Coupe.\n"
        "- Historical Auction Sales: Verified US auction results commonly fall between $625,000 and $860,000 USD.\n"
        "- Estimated Market Value: Around $675,000 to $775,000 USD for well-documented, low-mileage examples."
    )

    def fake_gemini_request(self, method: str, url: str, *, params=None, json_body=None, timeout_seconds=None, max_retries=None):
        captured_gemini_payloads.append(json_body or {})
        return httpx.Response(
            200,
            request=httpx.Request(method, url),
            json={
                "candidates": [{"content": {"parts": [{"text": natural_answer}]}}],
                "usageMetadata": {"promptTokenCount": 140, "candidatesTokenCount": 95},
            },
        )

    monkeypatch.setattr("app.integrations.gemini.GeminiClient._request_with_retry", fake_gemini_request)

    conv = client.post(
        "/api/v1/neon/conversations",
        headers=auth_headers["owner"],
        json={"title": "Supercar Pricing", "agent_id": "AGT-01"},
    )
    assert conv.status_code == 201, conv.text
    cid = conv.json()["conversation_id"]

    msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        headers=auth_headers["owner"],
        json={
            "content": "How much does a Lamborghini Aventador SVJ cost?",
            "enable_web_research": True,
        },
    )
    assert msg.status_code == 200, msg.text
    body = msg.json()

    reply = body["reply"]["output"]
    assert "Original Manufacturer MSRP" in reply
    assert "$517,770" in reply
    assert "Dealer" in reply and "Auction" in reply and "Estimated Market Value" in reply
    # Zero raw JSON, Python dict, traceback, or HTML tags in user-facing reply
    assert not reply.lstrip().startswith("{")
    assert "Traceback" not in reply
    assert "<div" not in reply

    # Verify provenance & research sources returned
    assert body["provenance"]["verification_status"] == "LIVE_VERIFIED"
    assert body["provenance"]["retrieved_at"]
    assert body["provenance"]["execution_id"]
    assert len(body["research_sources"]) == 2

    # Verify Gemini actually received pricing guidance and live sources
    assert len(captured_gemini_payloads) == 1
    sys_text = captured_gemini_payloads[0]["systemInstruction"]["parts"][0]["text"]
    assert "original manufacturer MSRP" in sys_text
    assert "bringatrailer.com" in sys_text


def test_file_hub_two_way_multimodal_neon_and_tenant_isolation(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """Acceptance Test C: Upload PNG + PDF, folders, rename, preview, Generate ZIP, attach both to NEON, verify tenant isolation."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-acceptance-0002")
    get_settings.cache_clear()

    # 1. Upload real PNG into 'photos' folder
    png_up = client.post(
        "/api/v1/files/upload",
        headers=auth_headers["owner"],
        files={"file": ("dashboard-shot.png", SAMPLE_PNG_BYTES, "image/png")},
        data={"folder": "photos"},
    )
    assert png_up.status_code == 201, png_up.text
    png_data = png_up.json()
    assert png_data["folder"] == "photos"
    assert png_data["is_image"] is True
    assert png_data["preview_url"].endswith("/preview")
    png_id = png_data["file_id"]

    # 2. Upload real PDF into 'reports' folder
    pdf_bytes = _make_minimal_pdf("ULTRON Q4 Revenue Report: Net Margin 38 Percent")
    pdf_up = client.post(
        "/api/v1/files/upload",
        headers=auth_headers["owner"],
        files={"file": ("q4-report.pdf", pdf_bytes, "application/pdf")},
        data={"folder": "reports"},
    )
    assert pdf_up.status_code == 201, pdf_up.text
    pdf_data = pdf_up.json()
    assert pdf_data["folder"] == "reports"
    pdf_id = pdf_data["file_id"]

    # 3. Folder filter & list all folders
    list_all = client.get("/api/v1/files", headers=auth_headers["owner"])
    assert list_all.status_code == 200
    assert list_all.json()["total"] == 2
    assert "photos" in list_all.json()["folders"]
    assert "reports" in list_all.json()["folders"]

    list_photos = client.get("/api/v1/files?folder=photos", headers=auth_headers["owner"])
    assert list_photos.status_code == 200
    assert list_photos.json()["total"] == 1
    assert list_photos.json()["files"][0]["file_id"] == png_id

    # 4. Rename & move folder via PATCH
    patched = client.patch(
        f"/api/v1/files/{png_id}",
        headers=auth_headers["owner"],
        json={"filename": "verified-capture.png", "folder": "inspected"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["filename"] == "verified-capture.png"
    assert patched.json()["folder"] == "inspected"

    # 5. Inline authenticated preview & download
    prev = client.get(f"/api/v1/files/{png_id}/preview", headers=auth_headers["owner"])
    assert prev.status_code == 200
    assert prev.headers["content-type"].startswith("image/png")
    assert prev.content == SAMPLE_PNG_BYTES

    dl = client.get(f"/api/v1/files/{png_id}/download", headers=auth_headers["owner"])
    assert dl.status_code == 200
    assert dl.content == SAMPLE_PNG_BYTES

    # 6. Generate ZIP archive with fixed schema (`files: {name: content}`)
    zip_resp = client.post(
        "/api/v1/files/generate-zip",
        headers=auth_headers["owner"],
        json={"archive_name": "ultron-pack.zip", "files": {"brief.md": "# Executive Summary\nAll systems ready."}},
    )
    assert zip_resp.status_code == 201, zip_resp.text
    zip_dl = client.get(f"/api/v1/files/{zip_resp.json()['file_id']}/download", headers=auth_headers["owner"])
    assert zip_dl.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_dl.content)) as zf:
        assert "brief.md" in zf.namelist()
        assert "Executive Summary" in zf.read("brief.md").decode("utf-8")

    # 7. Attach BOTH uploaded image + PDF to NEON and verify Gemini receives real image inlineData + PDF content
    captured_payloads: list[dict[str, Any]] = []

    def fake_gemini_request(self, method: str, url: str, *, params=None, json_body=None, timeout_seconds=None, max_retries=None):
        captured_payloads.append(json_body or {})
        return httpx.Response(
            200,
            request=httpx.Request(method, url),
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "I reviewed your uploaded image (verified-capture.png) and Q4 report (q4-report.pdf). The report highlights a 38 percent net margin."
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 210, "candidatesTokenCount": 42},
            },
        )

    monkeypatch.setattr("app.integrations.gemini.GeminiClient._request_with_retry", fake_gemini_request)

    conv = client.post(
        "/api/v1/neon/conversations",
        headers=auth_headers["owner"],
        json={"title": "Multimodal Review", "agent_id": "AGT-01"},
    )
    assert conv.status_code == 201
    cid = conv.json()["conversation_id"]

    msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        headers=auth_headers["owner"],
        json={
            "content": "Analyze both attached files and summarize what you find.",
            "file_ids": [png_id, pdf_id],
            "enable_web_research": False,
        },
    )
    assert msg.status_code == 200, msg.text
    reply_body = msg.json()
    assert len(reply_body["attached_files"]) == 2
    assert "verified-capture.png" in reply_body["reply"]["output"]

    # Confirm Gemini request actually contained real PNG base64 inlineData AND PDF filename/text
    assert len(captured_payloads) == 1
    user_parts = captured_payloads[0]["contents"][0]["parts"]
    inline_parts = [p["inlineData"] for p in user_parts if "inlineData" in p]
    assert len(inline_parts) == 1
    assert inline_parts[0]["mimeType"] == "image/png"
    assert base64.b64decode(inline_parts[0]["data"]) == SAMPLE_PNG_BYTES
    text_part = user_parts[0]["text"]
    assert "q4-report.pdf" in text_part

    # 8. Cross-tenant isolation check — a second tenant cannot preview or download tenant 1's file
    other_org = client.post(
        "/api/v1/auth/bootstrap-owner",
        json={
            "username": "other_owner",
            "email": "other@external.local",
            "password": "OtherStrongPassword!2026",
            "tenant_id": "TENANT-OTHER-99",
            "organization_name": "Other Tenant",
        },
    )
    if other_org.status_code == 201:
        other_login = client.post(
            "/api/v1/auth/login",
            json={"username": "other_owner", "password": "OtherStrongPassword!2026"},
        )
        other_hdr = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        assert client.get(f"/api/v1/files/{png_id}/preview", headers=other_hdr).status_code == 404
        assert client.get(f"/api/v1/files/{png_id}/download", headers=other_hdr).status_code == 404


def test_approval_gate_remains_immutable_for_high_value_finance(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Verify ApprovalGate cannot be bypassed on financial spend above policy limit ($50)."""
    resp = client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["owner"],
        json={
            "entry_type": "EXPENSE",
            "amount_usd": 250.0,
            "category": "Infrastructure",
            "description": "Cloud GPU cluster reservation",
        },
    )
    assert resp.status_code in (200, 201, 202), resp.text
    data = resp.json()
    assert (
        data.get("approval_required") is True
        or data.get("status") == "PENDING_APPROVAL"
        or data.get("approval_id") is not None
    )


def test_shared_auth_refresh_rotation_and_consistent_gemini_status(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify refresh token rotation restores Command Centre + NEON endpoints and Gemini status is consistent."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-consistent-key-0001")
    get_settings.cache_clear()

    login_payload = auth_headers["owner_login"]
    refresh_token = login_payload["refresh_token"]
    assert refresh_token.startswith("ultron_rt_")

    # Rotate via POST /api/v1/auth/refresh
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200, refreshed.text
    new_session = refreshed.json()
    assert new_session["access_token"] != login_payload["access_token"]
    assert new_session["refresh_token"] != refresh_token
    new_hdr = {"Authorization": f"Bearer {new_session['access_token']}"}

    # Old refresh token must be rejected after rotation
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401

    # Verify both Command Centre and NEON authenticated endpoints succeed with the rotated access token
    for path in (
        "/api/v1/monitoring/overview",
        "/api/v1/agents",
        "/api/v1/tasks",
        "/api/v1/notifications",
        "/api/v1/audit/logs?limit=25",
        "/api/v1/neon/conversations",
        "/api/v1/neon/models",
        "/api/v1/neon/tiers",
        "/api/v1/neon/usage",
        "/api/v1/neon/gemini/diagnostics?discover=false",
    ):
        r = client.get(path, headers=new_hdr)
        assert r.status_code == 200, f"{path} failed with {r.status_code}: {r.text}"

    # Verify consistent Gemini configured status across /health, /health/ready, and /api/v1/neon/gemini/diagnostics
    h = client.get("/health").json()
    rdy = client.get("/health/ready").json()
    diag = client.get("/api/v1/neon/gemini/diagnostics?discover=false", headers=new_hdr).json()
    assert h["integrations"]["providers"]["gemini"]["configured"] is True
    assert h["integrations"]["capabilities"]["gemini"]["configured"] is True
    assert rdy["config"]["integrations_configured"]["gemini"] is True
    assert diag["configured"] is True

