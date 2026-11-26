"""Exhaustive verification of ALL 60 Specialist Agents (AGT-01 through AGT-60) individually."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ALL_60_AGENT_IDS = [f"AGT-{i:02d}" for i in range(1, 61)]


def test_catalog_contains_exact_60_agents(client: TestClient, auth_headers: dict[str, dict[str, str]]) -> None:
    resp = client.get("/api/v1/agents", headers=auth_headers["owner"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 60
    ids = {a["agent_id"] for a in body["agents"]}
    assert ids == set(ALL_60_AGENT_IDS)


@pytest.mark.parametrize("agent_id", ALL_60_AGENT_IDS)
def test_individual_specialist_agent_manifest_and_execution(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
    agent_id: str,
) -> None:
    """Verify every single specialist agent AGT-01..AGT-60 individually has a valid contract and executes cleanly."""
    manifest_resp = client.get(f"/api/v1/agents/{agent_id}/manifest", headers=auth_headers["owner"])
    assert manifest_resp.status_code == 200, f"Manifest failed for {agent_id}: {manifest_resp.text}"
    m = manifest_resp.json()
    assert m["agent_id"] == agent_id
    assert m["approved"] is True
    assert m["domain"]
    assert m["contract"]["input_schema"]["type"] == "object"
    assert m["contract"]["output_schema"]["properties"]["agent_id"]["const"] == agent_id
    assert len(m["contract"]["execution_workflow"]) == 4
    assert m["contract"]["quality_benchmarks"]["zero_fabricated_telemetry"] is True

    invoke_resp = client.post(
        f"/api/v1/agents/{agent_id}/invoke",
        headers=auth_headers["owner"],
        json={
            "prompt": f"Execute domain verification check for {m['domain']} ({agent_id}).",
            "context": {"verification_run": True, "target_agent": agent_id},
        },
    )
    assert invoke_resp.status_code == 200, f"Invoke failed for {agent_id}: {invoke_resp.text}"
    out = invoke_resp.json()
    assert out["agent_id"] == agent_id
    assert out["domain"] == m["domain"]
    assert out["execution_mode"] in {"local_deterministic_fallback", "gemini_live"}
    assert agent_id in out["output"]
