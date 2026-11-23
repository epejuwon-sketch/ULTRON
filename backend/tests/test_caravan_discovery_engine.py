"""Tests for Caravan Phase 3 Real Funding Discovery Engine (SSRF, robots.txt, extraction, duplicates, NEON, ARGON)."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient


def test_discovery_ssrf_and_robots_blocked(client: TestClient, auth_headers: dict, monkeypatch) -> None:
    # 1. SSRF private IP blocked
    ssrf = client.post(
        "/api/v1/caravan/discovery/extract-preview",
        headers=auth_headers["owner"],
        json={"source_url": "http://169.254.169.254/latest/meta-data/"},
    )
    assert ssrf.status_code >= 400

    # 2. robots.txt Disallow respected
    class _RobotsResp:
        def __init__(self, code: int, text: str = ""):
            self.status_code = code
            self.text = text
            self.headers = {"content-type": "text/plain"}

    class _RobotsClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            if url.endswith("/robots.txt"):
                return _RobotsResp(200, "User-agent: *\nDisallow: /private-grants/\n")
            return _RobotsResp(200, "<html><title>Should not fetch</title></html>")

    monkeypatch.setattr(httpx, "Client", _RobotsClient)
    blocked = client.post(
        "/api/v1/caravan/discovery/extract-preview",
        headers=auth_headers["owner"],
        json={"source_url": "https://example.org/private-grants/seed"},
    )
    assert blocked.status_code == 422
    assert "robots.txt" in blocked.text


def test_discovery_argon_ingestion_duplicates_neon_facts_and_admin_review(
    client: TestClient, auth_headers: dict, monkeypatch
) -> None:
    src = client.post(
        "/api/v1/caravan/sources",
        headers=auth_headers["owner"],
        json={
            "name": "Bank of Industry Nigeria",
            "source_type": "OFFICIAL_REGISTRY",
            "base_url": "https://boi.ng/youth-grant-feed.json",
        },
    )
    assert src.status_code == 201, src.text
    src_id = src.json()["source_id"]

    feed_payload = json.dumps({
        "items": [
            {
                "title": "BOI Youth Innovation Grant",
                "funding_type": "GRANT",
                "amount_display": "NGN 5,000,000",
                "currency": "NGN",
                "geographic_restrictions": "Nigeria",
                "eligibility_requirements": "Nigerian youth-led MSMEs in technology or manufacturing.",
                "deadline_at": "2027-06-30",
                "source_url": "https://boi.ng/programs/youth-innovation-grant",
            },
            {
                "title": "BOI Youth Innovation Grant",
                "funding_type": "GRANT",
                "source_url": "https://boi.ng/programs/youth-innovation-grant",
            },
        ]
    })

    class _FakeResp:
        def __init__(self, code: int, text: str, ctype: str):
            self.status_code = code
            self.text = text
            self.headers = {"content-type": ctype}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            if url.endswith("/robots.txt"):
                return _FakeResp(404, "", "text/plain")
            return _FakeResp(200, feed_payload, "application/json")

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    # First ingestion creates 1 NEEDS_REVIEW opportunity and skips the duplicate in feed
    ing1 = client.post(f"/api/v1/caravan/discovery/ingest/{src_id}", headers=auth_headers["owner"])
    assert ing1.status_code == 200, ing1.text
    body1 = ing1.json()
    assert body1["extracted_count"] == 2
    assert body1["created_count"] == 1
    assert body1["duplicates_skipped"] == 1
    assert body1["verification_status"] == "NEEDS_REVIEW"
    opp_id = body1["created_opportunity_ids"][0]

    # Second ingestion skips already-ingested opportunity
    ing2 = client.post(f"/api/v1/caravan/discovery/ingest/{src_id}", headers=auth_headers["owner"])
    assert ing2.status_code == 200
    assert ing2.json()["created_count"] == 0
    assert ing2.json()["duplicates_skipped"] == 2

    # Non-admin VIEWER cannot review/verify discovered opportunities
    viewer_try = client.post(
        f"/api/v1/caravan/discovery/opportunities/{opp_id}/review",
        headers=auth_headers["viewer"],
        json={"decision": "VERIFIED", "supporting_evidence": "Confirmed on boi.ng"},
    )
    assert viewer_try.status_code == 403

    # Missing supporting evidence cannot mark VERIFIED
    no_ev = client.post(
        f"/api/v1/caravan/discovery/opportunities/{opp_id}/review",
        headers=auth_headers["owner"],
        json={"decision": "VERIFIED", "supporting_evidence": ""},
    )
    assert no_ev.status_code == 422

    # Valid admin verification transitions NEEDS_REVIEW -> VERIFIED
    ok = client.post(
        f"/api/v1/caravan/discovery/opportunities/{opp_id}/review",
        headers=auth_headers["owner"],
        json={"decision": "VERIFIED", "supporting_evidence": "Confirmed official BOI circular."},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["verification_status"] == "VERIFIED"

    # NEON extract-preview separates sourced_facts from ai_interpretation and flags missing fields
    prev = client.post(
        "/api/v1/caravan/discovery/extract-preview",
        headers=auth_headers["owner"],
        json={
            "source_url": "https://example.org/lagos-fellowship",
            "provider_org": "Lagos Hub",
            "raw_text": "<html><title>Lagos Tech Fellowship</title><body>Open to founders in Lagos, Nigeria.</body></html>",
        },
    )
    assert prev.status_code == 200, prev.text
    pbody = prev.json()
    assert "sourced_facts" in pbody and "ai_interpretation" in pbody
    assert pbody["ai_interpretation"]["requires_human_verification"] is True
    assert "deadline_at" in pbody["sourced_facts"]["items"][0]["missing_fields"]
