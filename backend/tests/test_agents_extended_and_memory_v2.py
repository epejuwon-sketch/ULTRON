"""Tests for agent manifests, inter-agent messaging, ApprovalGate extension registration, memory versioning, and user preferences."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_agent_manifest_messaging_and_approved_extension_registration(
    client: TestClient, auth_headers: dict
) -> None:
    manifest = client.get("/api/v1/agents/AGT-03/manifest", headers=auth_headers["operator"])
    assert manifest.status_code == 200
    mdata = manifest.json()
    assert mdata["agent_id"] == "AGT-03"
    assert mdata["execution_backing"] == "RULE_AND_TOOL_BACKED_OFFLINE"
    assert "metrics" in mdata

    msg = client.post(
        "/api/v1/agents/messages",
        headers=auth_headers["operator"],
        json={
            "from_agent_id": "AGT-01",
            "to_agent_id": "AGT-03",
            "subject": "Schema review handoff",
            "payload": {"migration": "002_full_backend_schema.sql"},
        },
    )
    assert msg.status_code == 201
    inbox = client.get("/api/v1/agents/messages?agent_id=AGT-03", headers=auth_headers["operator"])
    assert inbox.status_code == 200
    assert inbox.json()["total"] == 1

    # Propose dynamic extension agent -> gated at ApprovalGate
    proposed = client.post(
        "/api/v1/agents/register",
        headers=auth_headers["owner"],
        json={
            "agent_id": "AGT-EXT-01",
            "name": "Telemetry Forecasting Agent",
            "domain": "Observability",
            "role_description": "Forecasts API latency and storage growth trends.",
            "tools": ["system_diagnostics"],
        },
    )
    assert proposed.status_code == 201
    assert proposed.json()["approved"] is False
    approval_id = proposed.json()["approval"]["approval_id"]

    # OWNER approves extension -> becomes AVAILABLE & approved
    decided = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "Extension audited and approved"},
    )
    assert decided.status_code == 200
    assert decided.json()["linked_resource_state"] == "AVAILABLE"

    ag = client.get("/api/v1/agents/AGT-EXT-01", headers=auth_headers["operator"]).json()
    assert ag["approved"] is True
    assert ag["capability_state"] == "AVAILABLE"


def test_memory_six_tiers_versioning_privacy_and_user_preferences(
    client: TestClient, auth_headers: dict
) -> None:
    # Store PROJECT memory and update it to v2
    v1 = client.post(
        "/api/v1/memory",
        headers=auth_headers["operator"],
        json={
            "content": "Initial project milestone: PostgreSQL schema draft.",
            "memory_type": "PROJECT",
            "project_id": "prj_demo_01",
            "namespace": "ultron",
        },
    )
    assert v1.status_code == 201
    assert v1.json()["version"] == 1

    v2 = client.patch(
        f"/api/v1/memory/{v1.json()['memory_id']}",
        headers=auth_headers["operator"],
        json={"content": "Updated project milestone: PostgreSQL + pgvector + RLS finalized.", "importance_score": 0.95},
    )
    assert v2.status_code == 200
    assert v2.json()["version"] == 2

    hist = client.get(f"/api/v1/memory/{v2.json()['memory_id']}/history", headers=auth_headers["operator"])
    assert hist.status_code == 200
    assert hist.json()["total_versions"] == 2

    # PRIVATE memory stored by OWNER is hidden from OPERATOR search
    priv = client.post(
        "/api/v1/memory",
        headers=auth_headers["owner"],
        json={
            "content": "Private executive compensation note alpha99",
            "memory_type": "LONG_TERM",
            "access_level": "PRIVATE",
        },
    )
    assert priv.status_code == 201

    ops_search = client.post(
        "/api/v1/memory/search",
        headers=auth_headers["operator"],
        json={"query": "compensation note alpha99"},
    ).json()
    assert all("alpha99" not in r["content"] for r in ops_search["results"])

    owner_search = client.post(
        "/api/v1/memory/search",
        headers=auth_headers["owner"],
        json={"query": "compensation note alpha99"},
    ).json()
    assert any("alpha99" in r["content"] for r in owner_search["results"])

    # User preferences CRUD
    assert (
        client.put(
            "/api/v1/memory/preferences",
            headers=auth_headers["operator"],
            json={"key": "default_reasoning_tier", "value": 3},
        ).status_code
        == 200
    )
    prefs = client.get("/api/v1/memory/preferences", headers=auth_headers["operator"]).json()
    assert prefs["preferences"]["default_reasoning_tier"] == 3
