"""Tests for 60-agent catalog seeding, filtering, state governance, and NEON routing."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_60_agents_seeded_and_filterable(client: TestClient, auth_headers: dict) -> None:
    all_agents = client.get("/api/v1/agents", headers=auth_headers["viewer"])
    assert all_agents.status_code == 200
    assert all_agents.json()["total"] == 60

    core = client.get("/api/v1/agents?tier=CORE_25", headers=auth_headers["viewer"])
    ext = client.get("/api/v1/agents?tier=EXTENSIBLE_35", headers=auth_headers["viewer"])
    assert core.json()["total"] == 25
    assert ext.json()["total"] == 35


def test_neon_routing_and_agent_invocation(client: TestClient, auth_headers: dict) -> None:
    tiers = client.get("/api/v1/agents/reasoning-tiers", headers=auth_headers["operator"])
    assert tiers.status_code == 200
    assert len(tiers.json()["tiers"]) == 5

    preview = client.post(
        "/api/v1/agents/route",
        headers=auth_headers["operator"],
        json={"objective": "Design a FastAPI endpoint and Python refactor", "financial_amount_usd": 0.0},
    )
    assert preview.status_code == 200
    route_data = preview.json()
    assert route_data["selected_agent_id"] == "AGT-03"
    assert route_data["requires_approval_gate"] is False

    # High financial amount triggers ApprovalGate routing flag
    high_preview = client.post(
        "/api/v1/agents/route",
        headers=auth_headers["operator"],
        json={"objective": "Process treasury settlement", "financial_amount_usd": 250.0},
    )
    assert high_preview.status_code == 200
    assert high_preview.json()["requires_approval_gate"] is True
    assert high_preview.json()["risk_level"] == "HIGH"

    # Invoke agent offline honestly reports local_deterministic_fallback
    invoked = client.post(
        "/api/v1/agents/AGT-05/invoke",
        headers=auth_headers["operator"],
        json={"prompt": "Outline Supabase and Vercel split-stack architecture"},
    )
    assert invoked.status_code == 200
    assert invoked.json()["agent_id"] == "AGT-05"
    assert invoked.json()["execution_mode"] == "local_deterministic_fallback"

    # Only OWNER/ADMIN can update agent capability state
    assert (
        client.patch(
            "/api/v1/agents/AGT-05/state",
            headers=auth_headers["operator"],
            json={"capability_state": "VERIFIED_TESTED"},
        ).status_code
        == 403
    )
    updated = client.patch(
        "/api/v1/agents/AGT-05/state",
        headers=auth_headers["owner"],
        json={"capability_state": "VERIFIED_TESTED"},
    )
    assert updated.status_code == 200
    assert updated.json()["capability_state"] == "VERIFIED_TESTED"
