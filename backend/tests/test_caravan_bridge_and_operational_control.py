"""Tests for ULTRON x CARAVAN operational control policy, owner approval gates, and kill switch."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_caravan_bridge_and_operational_control_gates(client: TestClient, auth_headers: dict) -> None:
    # 1. Inspect bridge status & operational control policy
    st = client.get("/api/v1/caravan/bridge/status", headers=auth_headers["owner"])
    assert st.status_code == 200
    body = st.json()
    assert body["bridge"] == "ultron-caravan-s2s"
    assert body["caravan_repo_present"] is False
    assert body["degraded_mode_supported"] is True
    assert body["operational_control"]["autonomous_execution_enabled"] is True

    # 2. Autonomous permitted actions succeed without owner approval
    for cat in ("RESEARCH", "ANALYSIS", "TESTING", "INTERNAL_REPORTING", "APPROVED_DEVELOPMENT"):
        res = client.post(
            "/api/v1/caravan/bridge/action",
            headers=auth_headers["owner"],
            json={"action_category": cat, "summary": f"Caravan {cat} check"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["authorized"] is True
        assert res.json()["requires_owner_approval"] is False

    # 3. Owner-approval-required actions create pending AEGIS approval and do not auto-authorize
    for cat in (
        "SPEND_MONEY",
        "PAYMENT_OR_TRANSFER",
        "EXTERNAL_OUTREACH",
        "PUBLISH_CAMPAIGN",
        "CONTRACTUAL_COMMITMENT",
        "PRODUCTION_CHANGE",
    ):
        res = client.post(
            "/api/v1/caravan/bridge/action",
            headers=auth_headers["owner"],
            json={"action_category": cat, "summary": f"Caravan {cat} request"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["authorized"] is False
        assert data["requires_owner_approval"] is True
        assert data["approval"]["status"] == "PENDING"

    # 4. OWNER emergency kill switch halts even autonomous RESEARCH
    halt = client.put(
        "/api/v1/settings/autonomous_execution_enabled",
        headers=auth_headers["owner"],
        json={"value": False},
    )
    assert halt.status_code == 200

    halted_res = client.post(
        "/api/v1/caravan/bridge/action",
        headers=auth_headers["owner"],
        json={"action_category": "RESEARCH", "summary": "Should be halted by kill switch"},
    )
    assert halted_res.status_code == 409
