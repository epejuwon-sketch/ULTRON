"""Tests for Caravan Command Centre aggregation, source toggle RBAC, and tenant isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_caravan_command_centre_metrics_toggle_and_isolation(client: TestClient, auth_headers: dict) -> None:
    # 1. Create a source and an opportunity
    src = client.post(
        "/api/v1/caravan/sources",
        headers=auth_headers["owner"],
        json={
            "name": "Nigerian Innovation Fund",
            "source_type": "PUBLIC_PORTAL",
            "base_url": "https://nif.ng/grants",
        },
    )
    assert src.status_code == 201, src.text
    src_id = src.json()["source_id"]

    opp = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "title": "NIF Seed Grant",
            "provider_org": "Nigerian Innovation Fund",
            "funding_type": "GRANT",
            "source_url": "https://nif.ng/grants/seed",
            "eligibility_requirements": "Nigeria Technology Seed",
            "geographic_restrictions": "Nigeria",
            "source_id": src_id,
        },
    )
    assert opp.status_code == 201, opp.text
    opp_id = opp.json()["opportunity_id"]

    # 2. Verify Command Centre reflects real backend state
    cc = client.get("/api/v1/caravan/command-centre?days=30", headers=auth_headers["owner"])
    assert cc.status_code == 200, cc.text
    body = cc.json()
    ov = body["executive_overview"]
    assert ov["sources_total"] >= 1
    assert ov["sources_healthy"] >= 1
    assert ov["opportunities_total"] >= 1
    assert ov["awaiting_review_count"] >= 1
    assert body["financial_overview"]["payment_integration_status"] == "NOT_CONNECTED"
    assert body["financial_overview"]["live_payments_enabled"] is False
    assert body["financial_overview"]["read_only"] is True
    assert any(a["action"] == "CARAVAN_OPPORTUNITY_CREATED" for a in body["activity_timeline"])
    assert body["standalone_platform"]["deployed_url"] == "https://caravan-juwon2.vercel.app"
    assert body["standalone_platform"]["deployment_status"] in ("READY", "UNREACHABLE")
    assert body["infrastructure_and_integrations"]["vercel_project"] == "caravan"

    # 3. VIEWER cannot toggle source; OWNER can disable and re-enable
    viewer_try = client.post(
        f"/api/v1/caravan/sources/{src_id}/toggle",
        headers=auth_headers["viewer"],
        json={"enabled": False},
    )
    assert viewer_try.status_code == 403

    dis = client.post(
        f"/api/v1/caravan/sources/{src_id}/toggle",
        headers=auth_headers["owner"],
        json={"enabled": False},
    )
    assert dis.status_code == 200
    assert dis.json()["status"] == "DISABLED"

    cc2 = client.get("/api/v1/caravan/command-centre?days=30", headers=auth_headers["owner"]).json()
    assert cc2["executive_overview"]["sources_disabled"] >= 1

    # 4. Verify opportunity advances verified_count
    rev = client.post(
        f"/api/v1/caravan/discovery/opportunities/{opp_id}/review",
        headers=auth_headers["owner"],
        json={"decision": "VERIFIED", "supporting_evidence": "Verified at nif.ng"},
    )
    assert rev.status_code == 200
    cc3 = client.get("/api/v1/caravan/command-centre?days=30", headers=auth_headers["owner"]).json()
    assert cc3["executive_overview"]["verified_count"] >= 1
