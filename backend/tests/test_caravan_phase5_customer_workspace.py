"""Tests for Caravan Phase 5 Customer Onboarding, Application Workspace, Deadlines, and Reminders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def test_caravan_onboarding_workspace_and_deadline_reminders(client: TestClient, auth_headers: dict) -> None:
    # 1. Complete customer onboarding with Nigeria state_location and funding_goals
    acc = client.put(
        "/api/v1/caravan/account",
        headers=auth_headers["owner"],
        json={
            "organization_name": "Abuja Agritech Labs",
            "entity_type": "STARTUP",
            "country": "Nigeria",
            "state_location": "Abuja",
            "sector": "Agriculture",
            "stage": "SEED",
            "funding_goals": "Seed grant for solar irrigation pilot",
            "onboarding_completed": True,
        },
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["state_location"] == "Abuja"
    assert acc.json()["funding_goals"] == "Seed grant for solar irrigation pilot"
    assert acc.json()["profile_completion_pct"] == 100

    # 2. Create & verify an opportunity with an approaching deadline (within 7 days)
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    opp = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "title": "Abuja Agritech Innovation Grant",
            "provider_org": "Federal Ministry of Agriculture",
            "funding_type": "GRANT",
            "source_url": "https://fmard.gov.ng/agritech-grant",
            "eligibility_requirements": "Nigeria Agriculture Seed Startup",
            "geographic_restrictions": "Nigeria",
            "deadline_at": soon,
        },
    )
    assert opp.status_code == 201, opp.text
    opp_id = opp.json()["opportunity_id"]

    ver = client.post(
        f"/api/v1/caravan/discovery/opportunities/{opp_id}/review",
        headers=auth_headers["owner"],
        json={"decision": "VERIFIED", "supporting_evidence": "Confirmed on fmard.gov.ng"},
    )
    assert ver.status_code == 200

    # 3. Overview includes upcoming_deadlines and recently_verified
    ov = client.get("/api/v1/caravan/overview", headers=auth_headers["owner"])
    assert ov.status_code == 200
    assert any(o["opportunity_id"] == opp_id for o in ov.json()["upcoming_deadlines"])
    assert any(o["opportunity_id"] == opp_id for o in ov.json()["recently_verified"])

    # 4. Start application & update checklist + draft notes in Application Workspace
    app = client.post(
        "/api/v1/caravan/applications",
        headers=auth_headers["owner"],
        json={"opportunity_id": opp_id, "notes": "Initial draft"},
    )
    assert app.status_code == 201, app.text
    app_id = app.json()["application_id"]

    updated = client.patch(
        f"/api/v1/caravan/applications/{app_id}",
        headers=auth_headers["owner"],
        json={
            "status": "PREPARING",
            "notes": "CAC certificate and pitch deck ready",
            "checklist": [
                {"item": "Confirm eligibility", "done": True},
                {"item": "Attach CAC certificate", "done": True},
                {"item": "Final review", "done": False},
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["progress_pct"] == 67
    assert updated.json()["status"] == "PREPARING"

    # 5. Trigger approaching deadline reminders
    rem = client.post("/api/v1/caravan/applications/deadline-reminders?within_days=14", headers=auth_headers["owner"])
    assert rem.status_code == 200, rem.text
    assert rem.json()["reminders_created"] >= 1

    notifs = client.get("/api/v1/caravan/notifications", headers=auth_headers["owner"]).json()["notifications"]
    assert any(n["category"] == "DEADLINE" for n in notifs)
