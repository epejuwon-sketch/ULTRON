"""Tests for FILE HUB, FORGE & Live Preview, Creative Studio (Voice/Visual), BRIDGE, PULSE, and CARAVAN BI."""

from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient
from PIL import Image


def test_file_hub_upload_secret_redaction_and_generation(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    secret_tok = "AIza" + "SyFileHubSecretTest0123456789abcdef"
    upload = client.post(
        "/api/v1/files/upload",
        headers=auth_headers["owner"],
        files={"file": ("notes.txt", f"Project notes with secret {secret_tok}".encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["scan_status"] == "REDACTED"
    assert body["secrets_redacted"] >= 1
    assert body["untrusted_content_tagged"] is True
    assert secret_tok not in body["extracted_text"]

    # Blocked executable rejected
    exe_resp = client.post(
        "/api/v1/files/upload",
        headers=auth_headers["owner"],
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )
    assert exe_resp.status_code == 422

    # Generate downloadable ZIP
    zresp = client.post(
        "/api/v1/files/generate-zip",
        headers=auth_headers["owner"],
        json={"archive_name": "export_bundle", "files": {"README.md": "# Export", "data.json": '{"ok": true}'}},
    )
    assert zresp.status_code == 201
    fid = zresp.json()["file_id"]
    dl = client.get(f"/api/v1/files/{fid}/download", headers=auth_headers["owner"])
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # ZIP magic bytes


def test_forge_project_generation_aegis_verification_and_live_preview(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    res = client.post(
        "/api/v1/forge/projects",
        headers=auth_headers["owner"],
        json={
            "name": "Caravan Founder Portal",
            "template": "react_vite",
            "prompt": "Build a clean mobile-first portal for African startup founders.",
        },
    )
    assert res.status_code == 201
    proj = res.json()
    assert proj["status"] == "VERIFIED"
    assert proj["aegis_verdict"]["passed"] is True
    assert "package.json" in proj["file_list"]
    assert proj["archive_file_id"]

    # Live Preview HTML served with CSP sandbox
    preview = client.get(f"/api/v1/forge/projects/{proj['forge_id']}/preview", headers=auth_headers["owner"])
    assert preview.status_code == 200
    assert "Caravan Founder Portal" in preview.text
    assert "Content-Security-Policy" in preview.headers


def test_creative_voice_visual_bridge_caravan_and_pulse(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # Voice turn
    v = client.post(
        "/api/v1/creative/voice/turn",
        headers=auth_headers["owner"],
        json={"transcript": "Summarize today's system readiness.", "mode": "push_to_talk"},
    )
    assert v.status_code == 200
    assert v.json()["spoken_reply"]

    # Visual frame analysis with real PNG bytes
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color=(6, 182, 212)).save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    vis = client.post(
        "/api/v1/creative/visual/analyze",
        headers=auth_headers["owner"],
        json={"prompt": "Describe this frame", "image_base64": img_b64, "mime_type": "image/png", "source": "camera"},
    )
    assert vis.status_code == 200
    assert vis.json()["image_metadata"]["width"] == 64
    assert vis.json()["image_metadata"]["height"] == 48

    # Creative Studio graphic job produces downloadable SVG
    job = client.post(
        "/api/v1/creative/jobs",
        headers=auth_headers["owner"],
        json={"media_type": "GRAPHIC", "prompt": "ULTRON OS 2026 Institutional Banner"},
    )
    assert job.status_code == 201
    assert job.json()["output_file_id"]

    # BRIDGE safe share vs SSRF blocked share
    good_share = client.post(
        "/api/v1/bridge/share",
        headers=auth_headers["owner"],
        json={"title": "Research Link", "url": "https://example.org/ai-report", "shared_text": "Review this report"},
    )
    assert good_share.status_code == 201
    assert good_share.json()["aegis_url_verdict"] == "SAFE"

    bad_share = client.post(
        "/api/v1/bridge/share",
        headers=auth_headers["owner"],
        json={"title": "SSRF", "url": "http://127.0.0.1:8000/admin"},
    )
    assert bad_share.status_code == 422

    # CARAVAN empty state (zero fabricated metrics!)
    empty_bi = client.get("/api/v1/caravan/summary", headers=auth_headers["owner"]).json()
    assert empty_bi["has_data"] is False
    assert empty_bi["totals"]["signups"] == 0

    # Ingest real CARAVAN events and verify aggregation
    client.post(
        "/api/v1/caravan/events",
        headers=auth_headers["owner"],
        json={"event_type": "SIGNUP", "country": "Nigeria", "city": "Lagos", "acquisition_source": "ORGANIC", "count_value": 10},
    )
    client.post(
        "/api/v1/caravan/events",
        headers=auth_headers["owner"],
        json={"event_type": "CONVERSION", "country": "Nigeria", "city": "Lagos", "acquisition_source": "ORGANIC", "count_value": 2},
    )
    client.post(
        "/api/v1/caravan/events",
        headers=auth_headers["owner"],
        json={"event_type": "REVENUE", "country": "United Kingdom", "city": "London", "acquisition_source": "PARTNER", "amount_usd": 450.0},
    )
    bi = client.get("/api/v1/caravan/summary", headers=auth_headers["owner"]).json()
    assert bi["has_data"] is True
    assert bi["totals"]["signups"] == 10
    assert bi["totals"]["conversion_rate_pct"] == 20.0
    assert bi["totals"]["revenue_usd"] == 450.0
    assert bi["by_country"]["Nigeria"] == 12

    # PULSE live page hydrates directly from live CARAVAN backend state
    page = client.post(
        "/api/v1/pulse/pages",
        headers=auth_headers["owner"],
        json={"title": "Caravan Live Growth", "page_type": "CARAVAN"},
    ).json()
    live = client.get(f"/api/v1/pulse/pages/{page['page_id']}/live", headers=auth_headers["owner"]).json()
    assert live["live_data"]["totals"]["signups"] == 10
