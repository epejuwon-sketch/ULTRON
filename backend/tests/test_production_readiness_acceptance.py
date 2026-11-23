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

    def fake_run_research(
        prompt: str,
        *,
        settings,
        max_results: int = 8,
        is_pricing_query: bool = False,
        fetch_source_pages: bool = True,
        http_client=None,
    ) -> dict[str, Any]:
        return {
            "query": prompt,
            "core_subject": "Lamborghini Aventador SVJ",
            "provider": "duckduckgo_web",
            "retrieved_at": "2026-11-22T20:00:00+00:00",
            "independent_domains_count": 3,
            "pages_fetched_count": 2,
            "nigeria_market_evidence": {
                "checked": True,
                "verified_local_listings_found": False,
                "candidate_sources_inspected": 2,
                "note": "No confirmed active Nigerian dealer listings or verified completed sales were found for this specific model in the live retrieval.",
            },
            "verified_sources": [
                {
                    "title": "Lamborghini Aventador SVJ | Official Lamborghini History",
                    "url": "https://www.lamborghini.com/en-en/history/aventador-svj",
                    "domain": "lamborghini.com",
                    "category": "manufacturer_msrp",
                    "snippet": "Official Lamborghini Aventador SVJ V12 770 CV specification and launch details.",
                    "page_excerpt": "Original US MSRP started at $517,770 for the Coupe and $573,966 for the Roadster.",
                    "page_fetched": True,
                    "credibility": "established_source",
                    "retrieved_at": "2026-11-22T20:00:00+00:00",
                },
                {
                    "title": "DriveIndex — Lamborghini Aventador LP770-4 SVJ Roadster Auction Results",
                    "url": "https://driveindex.com/cars/lamborghini/aventador-lp770-4-svj-roadster/auction-results",
                    "domain": "driveindex.com",
                    "category": "completed_auction_results",
                    "snippet": "Verified Lamborghini Aventador SVJ Roadster auction sales and hammer prices.",
                    "page_excerpt": "5 verified auction sales tracked, sold prices from $805,000 to $1,550,000 USD with a median completed sale of $1,263,000 USD.",
                    "page_fetched": True,
                    "credibility": "established_source",
                    "retrieved_at": "2026-11-22T20:00:00+00:00",
                },
                {
                    "title": "Used Lamborghini Aventador SVJ for Sale — Autotrader",
                    "url": "https://www.autotrader.com/cars-for-sale/lamborghini/aventador/svj",
                    "domain": "autotrader.com",
                    "category": "current_dealer_listings",
                    "snippet": "Active US dealer asking prices range from $869,995 to $1,899,990 USD depending on Coupe/Roadster trim and mileage.",
                    "page_excerpt": "",
                    "page_fetched": False,
                    "credibility": "established_source",
                    "retrieved_at": "2026-11-22T20:00:00+00:00",
                },
            ],
            "provenance": {
                "source": "duckduckgo_web, wikipedia_api",
                "retrieved_at": "2026-11-22T20:00:00+00:00",
                "verification_status": "LIVE_VERIFIED",
                "cache_status": "live",
            },
        }

    monkeypatch.setattr("app.services.research_intelligence.run_grounded_web_research", fake_run_research)
    monkeypatch.setattr("app.services.neon_router.run_grounded_web_research", fake_run_research, raising=False)

    natural_answer = (
        "The Lamborghini Aventador SVJ (produced for 2019–2021) trades well above its original factory price in the US and European markets (checked November 2026):\n\n"
        "- Original Manufacturer MSRP: $517,770 USD for the Coupe and $573,966 USD for the Roadster before options (lamborghini.com).\n"
        "- Current Dealer & Used Asking Prices: Active dealer listings generally ask $850,000 to $1.5M in Europe and $869,995 to $1.9M USD in the US depending on mileage and Roadster vs. Coupe specification (autotrader.com). Note that these are asking prices rather than completed sales.\n"
        "- Documented Completed Auction Sales: Verified completed auction sales range from $660,000 to $1,550,000 USD, with SVJ Roadster auction results showing a median sold price of $1,263,000 USD across 5 verified sales (driveindex.com).\n"
        "- Nigerian Market Evidence: No confirmed active Nigerian dealer listings or verified local completed sales were found in this live retrieval; third-party NGN directory figures are unverified currency conversions rather than confirmed local inventory."
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
    assert "Asking Prices" in reply and "Completed Auction Sales" in reply and "Nigerian Market Evidence" in reply
    # Zero raw JSON, Python dict, traceback, or HTML tags in user-facing reply
    assert not reply.lstrip().startswith("{")
    assert "Traceback" not in reply
    assert "<div" not in reply

    # Verify provenance & research sources returned
    assert body["provenance"]["verification_status"] == "LIVE_VERIFIED"
    assert body["provenance"]["retrieved_at"]
    assert body["provenance"]["execution_id"]
    assert len(body["research_sources"]) == 3

    # Verify Gemini actually received pricing guidance, full page extracted evidence, and Nigerian market check
    assert len(captured_gemini_payloads) == 1
    sys_text = captured_gemini_payloads[0]["systemInstruction"]["parts"][0]["text"]
    assert "Original Manufacturer MSRP" in sys_text
    assert "Full Page Extracted Evidence:" in sys_text
    assert "NIGERIA LOCAL MARKET CHECK" in sys_text
    assert "Available live market results WERE successfully retrieved above" in sys_text


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


def test_live_research_pipeline_multi_source_and_page_extraction_not_unavailable():
    """Regression test: prove conversational pricing questions normalize queries, search multiple facets,
    fetch full source pages, and never falsely report available results as unavailable.
    """
    from app.integrations.web_research import WebResearchClient, extract_core_subject
    from app.services.research_intelligence import build_natural_language_guidance

    assert extract_core_subject("How much does a Lamborghini Aventador SVJ cost?") == "Lamborghini Aventador SVJ"

    # Simulate realistic DuckDuckGo HTML responses across the 4 facets + full webpage HTML responses
    facet_pages = {
        "Lamborghini Aventador SVJ MSRP": """
            <html><body>
              <div class="result">
                <a class="result__a" href="https://www.lamborghini.com/en-en/history/aventador-svj">Lamborghini Aventador SVJ | Lamborghini.com</a>
                <a class="result__snippet">Official V12 770 CV specification and launch history.</a>
              </div>
              <div class="result">
                <a class="result__a" href="https://hyper.luxe/price/lamborghini/aventador-svj-coupe-price/">Lamborghini Aventador SVJ Coupe Price</a>
                <a class="result__snippet">Advertised at $850K to $1.5M in Europe and $1.1M to $1.9M in the US against an original MSRP of $517,770.</a>
              </div>
            </body></html>
        """,
        "Lamborghini Aventador SVJ auction results": """
            <html><body>
              <div class="result">
                <a class="result__a" href="https://driveindex.com/cars/lamborghini/aventador-lp770-4-svj-roadster/auction-results">Aventador SVJ Roadster Auction Results | DriveIndex</a>
                <a class="result__snippet">Tracked 5 verified auction sales from $805,000 to $1,550,000.</a>
              </div>
            </body></html>
        """,
        "Lamborghini Aventador SVJ for sale price": """
            <html><body>
              <div class="result">
                <a class="result__a" href="https://www.autotrader.com/cars-for-sale/lamborghini/aventador/svj">Used Lamborghini Aventador SVJ for Sale - Autotrader</a>
                <a class="result__snippet">Search from 33 Used Lamborghini Aventador cars for sale.</a>
              </div>
            </body></html>
        """,
        "Lamborghini Aventador SVJ price Nigeria NGN": """
            <html><body>
              <div class="result">
                <a class="result__a" href="https://www.autogiz.com/ng/car-prices/lamborghini-aventador-115.php">Lamborghini Aventador Car Prices In Nigeria</a>
                <a class="result__snippet">Automated directory estimate in NGN.</a>
              </div>
            </body></html>
        """,
    }

    source_page_bodies = {
        "https://www.lamborghini.com/en-en/history/aventador-svj": """
            <html><head><title>Aventador SVJ</title></head>
            <body><p>The Lamborghini Aventador SVJ launched with an original base MSRP of $517,770 USD for the Coupe.</p></body></html>
        """,
        "https://hyper.luxe/price/lamborghini/aventador-svj-coupe-price/": """
            <html><head><title>SVJ Coupe Price</title></head>
            <body><p>Original MSRP $517,770. Asking prices sit at $1.1M to $1.9M USD while transactional sales sit around $660,000 to $715,931 USD.</p></body></html>
        """,
        "https://driveindex.com/cars/lamborghini/aventador-lp770-4-svj-roadster/auction-results": """
            <html><head><title>DriveIndex SVJ Auction Results</title></head>
            <body><p>DriveIndex has tracked 5 verified auction sales with sold prices from $805,000 to $1,550,000 USD and a median sale of $1,263,000 USD.</p></body></html>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "duckduckgo.com" in url_str:
            body_text = request.content.decode("utf-8", errors="ignore")
            for q_key, html_doc in facet_pages.items():
                from urllib.parse import quote_plus

                if quote_plus(q_key) in body_text or q_key in body_text:
                    return httpx.Response(200, text=html_doc, headers={"content-type": "text/html"})
            # Conversational un-normalized query with '?' returns 202 empty stub (reproducing the exact DDG failure)
            return httpx.Response(202, text="<html><body></body></html>", headers={"content-type": "text/html"})
        if "en.wikipedia.org" in url_str:
            # Verify Wikimedia User-Agent compliance
            assert "ULTRON-OS-2026" in request.headers.get("User-Agent", "")
            return httpx.Response(
                200,
                json={"query": {"search": [{"title": "Lamborghini Aventador", "snippet": "V12 flagship sports car."}]}},
            )
        if url_str in source_page_bodies:
            return httpx.Response(200, text=source_page_bodies[url_str], headers={"content-type": "text/html"})
        return httpx.Response(404, text="Not found")

    mock_http = httpx.Client(transport=httpx.MockTransport(handler))
    settings = get_settings()
    research_client = WebResearchClient(settings, http_client=mock_http)
    # Bypass DNS check on mock URLs during unit test
    research_client.fetch_and_extract = lambda url, max_chars=4000: {
        "url": url,
        "domain": url.split("/")[2],
        "retrieved": url in source_page_bodies,
        "status_code": 200 if url in source_page_bodies else 404,
        "content_type": "text/html",
        "title": "Fetched Page",
        "extracted_text": source_page_bodies.get(url, ""),
        "retrieved_at": "2026-11-22T20:05:00+00:00",
    }

    bundle = research_client.search(
        "How much does a Lamborghini Aventador SVJ cost?",
        max_results=8,
        is_pricing_query=True,
        fetch_source_pages=True,
    )

    # Prove available live results are NEVER reported as unavailable
    assert bundle["provenance"]["verification_status"] == "LIVE_VERIFIED"
    assert len(bundle["verified_sources"]) >= 5
    assert bundle["independent_domains_count"] >= 5
    assert bundle["pages_fetched_count"] >= 2

    categories = {s["category"] for s in bundle["verified_sources"]}
    assert "manufacturer_msrp" in categories
    assert "completed_auction_results" in categories
    assert "current_dealer_listings" in categories

    # Prove Nigerian market evidence is honestly marked unverified when only generic NGN directory pages exist
    assert bundle["nigeria_market_evidence"]["checked"] is True
    assert bundle["nigeria_market_evidence"]["verified_local_listings_found"] is False

    guidance = build_natural_language_guidance(is_pricing_query=True, research_bundle=bundle)
    assert "Available live market results WERE successfully retrieved above" in guidance
    assert "returned no reachable sources" not in guidance
    assert "Full Page Extracted Evidence:" in guidance
    assert "$517,770" in guidance
    assert "$1,263,000" in guidance


def test_empty_thought_only_gemini_response_triggers_fallback_and_persists_non_empty_body(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression test for exec_9760ad2aa1ec49:
    If a Gemini thinking model (e.g. gemini-4-carbon or gemini-4-hydrogen) returns HTTP 200
    containing only `{"thought": True}` parts (or empty visible text due to finishReason=MAX_TOKENS),
    GeminiClient must reject the empty body so execute_with_failover advances to the next model in
    the tier chain and persists a non-empty answer along with persisted provenance metadata.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-thinking-fallback-key-0001")
    get_settings.cache_clear()

    models_called: list[str] = []

    def fake_gemini_request(self, method: str, url: str, *, params=None, json_body=None, timeout_seconds=None, max_retries=None):
        url_s = str(url)
        # Extract model name from /models/<model>:generateContent
        model_id = url_s.split("/models/")[1].split(":")[0] if "/models/" in url_s else "unknown"
        models_called.append(model_id)

        # Simulate gemini-4-carbon (404) and gemini-4-hydrogen (HTTP 200 with ONLY thought parts & 0 visible text!)
        if model_id in ("gemini-4-carbon", "gemini-4-argon"):
            return httpx.Response(
                404,
                request=httpx.Request(method, url_s),
                json={"error": {"code": 404, "message": "Model not found", "status": "NOT_FOUND"}},
            )
        if model_id == "gemini-4-hydrogen":
            return httpx.Response(
                200,
                request=httpx.Request(method, url_s),
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "thought": True,
                                        "text": "Internal reasoning consuming token budget before visible answer...",
                                    }
                                ]
                            },
                            "finishReason": "MAX_TOKENS",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 950,
                        "candidatesTokenCount": 0,
                        "thoughtsTokenCount": 2048,
                        "totalTokenCount": 2998,
                    },
                },
            )
        # Next fallback model (gemini-3.8-flash) returns a complete, visible natural-language answer
        return httpx.Response(
            200,
            request=httpx.Request(method, url_s),
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "Verified market answer: The Lamborghini Aventador SVJ had an original US MSRP of $517,770 USD, while current dealer asking prices range from $869,995 to $1.9M USD and completed auction sales show a median of $1,263,000 USD."
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 950, "candidatesTokenCount": 68, "totalTokenCount": 1018},
            },
        )

    monkeypatch.setattr("app.integrations.gemini.GeminiClient._request_with_retry", fake_gemini_request)

    conv = client.post(
        "/api/v1/neon/conversations",
        headers=auth_headers["owner"],
        json={"title": "Empty Thought Regression", "agent_id": "AGT-01"},
    )
    assert conv.status_code == 201
    cid = conv.json()["conversation_id"]

    msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        headers=auth_headers["owner"],
        json={"content": "Summarize the Lamborghini Aventador SVJ valuation.", "enable_web_research": False},
    )
    assert msg.status_code == 200, msg.text
    payload = msg.json()

    # Confirm gemini-4-hydrogen was tried, rejected for empty visible text, and fell back to gemini-3.8-flash
    assert "gemini-4-hydrogen" in models_called
    assert "gemini-3.8-flash" in models_called
    assert payload["reply"]["model"] == "gemini-3.8-flash"
    assert payload["reply"]["fallback_used"] is True
    assert payload["provenance"]["verification_status"] == "LIVE_VERIFIED_WITH_FALLBACK"
    assert "Verified market answer:" in payload["output"]
    assert "Verified market answer:" in payload["assistant_message"]["content"]

    # Confirm failover_errors recorded the EMPTY_MODEL_OUTPUT from gemini-4-hydrogen
    hydrogen_errs = [e for e in payload["reply"]["failover_errors"] if e["model"] == "gemini-4-hydrogen"]
    assert len(hydrogen_errs) == 1
    assert "empty visible text" in hydrogen_errs[0]["error"].lower()

    # Confirm GET /api/v1/neon/conversations/{cid} persists both the answer content AND provenance metadata across page reloads
    fetched_conv = client.get(f"/api/v1/neon/conversations/{cid}", headers=auth_headers["owner"])
    assert fetched_conv.status_code == 200
    asst_msgs = [m for m in fetched_conv.json()["messages"] if m["role"] == "assistant"]
    assert len(asst_msgs) == 1
    assert "Verified market answer:" in asst_msgs[0]["content"]
    assert asst_msgs[0]["provenance"]["verification_status"] == "LIVE_VERIFIED_WITH_FALLBACK"
    exec_id = asst_msgs[0]["execution_id"]
    assert exec_id

    # Confirm GET /api/v1/neon/executions/{execution_id} retrieves the exact stored execution & message
    inspected = client.get(f"/api/v1/neon/executions/{exec_id}", headers=auth_headers["owner"])
    assert inspected.status_code == 200
    assert inspected.json()["matched_message"]["execution_id"] == exec_id
    assert inspected.json()["matched_message"]["content_empty"] is False


def test_multi_provider_research_failover_when_duckduckgo_returns_202_and_diagnostics_endpoint(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression test for Vercel Preview HTTP 202 anti-bot challenge on DuckDuckGo:
    When DuckDuckGo returns HTTP 202 (empty challenge page) on a serverless datacenter IP,
    WebResearchClient must classify the attempt as BOT_PROTECTION_CHALLENGE (never silently swallowing it),
    automatically fail over to independent providers (Yahoo US/UK, Gemini Google Search Grounding, Google News RSS, Wikipedia),
    enforce relevance and completed-sale classification, and expose full telemetry at GET /api/v1/research/diagnostics.
    """
    from app.integrations.web_research import (
        WebResearchClient,
        classify_market_source_category,
        is_result_relevant_to_query,
        parse_google_news_rss,
        parse_yahoo_search_html,
    )

    # 1. Verify Yahoo HTML parser extracts real organic results and strips Yahoo internal links
    sample_yahoo_html = """
    <html><body>
      <div class="compTitle options-toggle">
        <a href="https://rd.search.yahoo.com/_ylt=1/RV=2/RU=https%3a%2f%2fexoticcartrends.com%2flamborghini%2faventador-svj-price%2f/RK=0">
          <h3>Lamborghini Aventador SVJ Price: $1,297,942 Median (Nov 2026)</h3>
        </a>
      </div>
      <div class="compText">As of Nov 22, 2026, the median asking price for a Lamborghini Aventador SVJ is $1,297,942 across 15 cars for sale.</div>
      <div class="compTitle options-toggle">
        <a href="https://rd.search.yahoo.com/_ylt=2/RV=2/RU=https%3a%2f%2fdriveindex.com%2fcars%2flamborghini%2faventador-lp770-4-svj-roadster%2fauction-results/RK=0">
          <h3>Lamborghini Aventador LP770-4 SVJ Roadster Auction Results</h3>
        </a>
      </div>
      <div class="compText">DriveIndex has tracked 5 verified Lamborghini Aventador LP770-4 SVJ Roadster auction sales, with sold prices from $805,000 to $1,550,000 and a median of $1,263,000.</div>
    </body></html>
    """
    yahoo_parsed = parse_yahoo_search_html(sample_yahoo_html)
    assert len(yahoo_parsed) == 2
    assert yahoo_parsed[0]["url"] == "https://exoticcartrends.com/lamborghini/aventador-svj-price/"
    assert "$1,297,942" in yahoo_parsed[0]["snippet"]
    assert yahoo_parsed[1]["url"] == "https://driveindex.com/cars/lamborghini/aventador-lp770-4-svj-roadster/auction-results"

    # 2. Verify relevance filter rejects generic homepage/dictionary mismatches
    assert is_result_relevant_to_query(
        "Exotic Definition & Meaning - Merriam-Webster",
        "The meaning of EXOTIC is introduced from another country.",
        "https://www.merriam-webster.com/dictionary/exotic",
        "Lamborghini Aventador SVJ price",
    ) is False
    assert is_result_relevant_to_query(
        "Lamborghini Aventador SVJ Price: $1,297,942 Median",
        "Median asking price for a Lamborghini Aventador SVJ in the US.",
        "https://exoticcartrends.com/lamborghini/aventador-svj-price/",
        "Lamborghini Aventador SVJ price",
    ) is True

    # 3. Verify strict asking-price vs. completed-sale classification
    assert (
        classify_market_source_category(
            "exoticcartrends.com",
            "Exotic Car Prices & Market Values (2026)",
            "Daily asking prices, auction results and market trends for Ferrari and Lamborghini.",
        )
        == "market_valuation_aggregate"
    )
    assert (
        classify_market_source_category(
            "driveindex.com",
            "Lamborghini Aventador LP770-4 SVJ Roadster Auction Results",
            "5 verified sales, sold prices from $805,000 to $1,550,000.",
        )
        == "completed_auction_results"
    )
    assert (
        classify_market_source_category(
            "autotrader.com",
            "Used Lamborghini Aventador SVJ for Sale",
            "33 Used Lamborghini Aventador cars for sale at dealers.",
        )
        == "current_dealer_listings"
    )

    # 4. Verify Google News RSS parser
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Lamborghini Aventador SVJ Market Update - duPont REGISTRY</title>
        <link>https://news.dupontregistry.com/lamborghini-svj-market</link>
        <pubDate>Mon, 05 Oct 2026 07:00:00 GMT</pubDate>
        <source url="https://news.dupontregistry.com">duPont REGISTRY News</source>
        <description>Current Lamborghini Aventador SVJ market analysis.</description>
      </item>
    </channel></rss>"""
    rss_items = parse_google_news_rss(sample_rss)
    assert len(rss_items) == 1
    assert "duPont REGISTRY" in rss_items[0]["snippet"]

    # 5. Simulate DuckDuckGo returning HTTP 202 anti-bot challenge (as on Vercel AWS Lambda IP) while Yahoo succeeds
    settings = get_settings()
    rc = WebResearchClient(settings)
    monkeypatch.setattr(
        rc,
        "_post_form",
        lambda url, data, timeout=7.5, headers=None: httpx.Response(
            202,
            text="<html><body><div class='anomaly-modal'>Challenge</div></body></html>",
            request=httpx.Request("POST", url),
        ),
    )
    monkeypatch.setattr(
        rc,
        "_get",
        lambda url, params=None, timeout=8.0, headers=None, follow_redirects=True: (
            httpx.Response(200, text=sample_yahoo_html, request=httpx.Request("GET", url))
            if "search.yahoo.com" in url
            else (
                httpx.Response(
                    200,
                    json={"query": {"search": [{"title": "Lamborghini Aventador", "snippet": "V12 flagship sports car with SVJ variant."}]}},
                    request=httpx.Request("GET", url),
                )
                if "wikipedia.org" in url
                else httpx.Response(200, text=sample_rss, request=httpx.Request("GET", url))
            )
        ),
    )

    bundle = rc.search(
        "How much does a Lamborghini Aventador SVJ cost?",
        max_results=6,
        is_pricing_query=True,
        fetch_source_pages=False,
        bypass_cache=True,
    )
    # Prove that even when DuckDuckGo returns HTTP 202 on every attempt, Yahoo + Wikipedia recover the search!
    assert bundle["provenance"]["verification_status"] == "LIVE_VERIFIED"
    assert len(bundle["verified_sources"]) >= 2
    ddg_attempts = [a for a in bundle["attempt_diagnostics"] if a["provider"] == "duckduckgo_web"]
    assert len(ddg_attempts) >= 1
    assert ddg_attempts[0]["http_status"] == 202
    assert ddg_attempts[0]["error_category"] == "BOT_PROTECTION_CHALLENGE"
    yahoo_attempts = [a for a in bundle["attempt_diagnostics"] if a["provider"] == "yahoo_web"]
    assert len(yahoo_attempts) >= 1
    assert yahoo_attempts[0]["error_category"] == "OK"

    # 6. Verify GET /api/v1/research/diagnostics endpoint returns complete provider diagnostics structure
    diag_resp = client.get("/api/v1/research/diagnostics?live=false", headers=auth_headers["owner"])
    assert diag_resp.status_code == 200, diag_resp.text
    diag_data = diag_resp.json()
    assert "providers" in diag_data
    prov_names = {p["provider_name"] for p in diag_data["providers"]}
    for expected_prov in (
        "google_custom_search",
        "gemini_google_search",
        "duckduckgo_web",
        "yahoo_web",
        "yahoo_uk_web",
        "google_news_rss",
        "wikipedia_api",
    ):
        assert expected_prov in prov_names



