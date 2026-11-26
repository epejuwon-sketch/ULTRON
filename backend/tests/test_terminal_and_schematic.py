"""Tests for ULTRON Master Terminal (Page 112) execution and truthful state reporting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_master_terminal_command_execution(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test standard natural language command through Master Terminal with truthful state sequence."""
    owner_headers = auth_headers["owner"]
    payload = {
        "prompt": "Inspect CARAVAN funding opportunities and verify under-18 eligibility rules",
        "voice_input": False,
    }
    resp = client.post("/api/v1/terminal/command", json=payload, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "COMPLETED"
    assert "transcript" in data
    assert len(data["transcript"]) >= 4

    # Assert sequential states exist
    states = [step["state"] for step in data["transcript"]]
    assert "UNDERSTANDING" in states
    assert "PLANNING" in states
    assert "RESEARCHING" in states or "EXECUTING" in states
    assert "VERIFYING" in states
    assert "COMPLETED" in states

    # Assert assigned agent and verification
    assert data["assigned_agent"]["agent_id"] in ["AGT-01", "AGT-56", "AGT-10", "AGT-02"]
    assert len(data["verification_checks"]) > 0
    assert all(c["status"] == "VERIFIED" for c in data["verification_checks"])
    assert data["relevant_page"]["number"] == 86


def test_master_terminal_approval_gate_for_financial_mutation(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test that financial transfer/spend requests halt at AWAITING_APPROVAL."""
    owner_headers = auth_headers["owner"]
    payload = {
        "prompt": "Transfer 500,000 NGN to external vendor for advertising campaign",
        "voice_input": True,
    }
    resp = client.post("/api/v1/terminal/command", json=payload, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "AWAITING_APPROVAL"
    states = [step["state"] for step in data["transcript"]]
    assert "AWAITING_APPROVAL" in states
    assert data["relevant_page"]["number"] == 22  # Approval Centre


def test_master_terminal_diagnostics_command(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test diagnostics inquiry through Master Terminal."""
    owner_headers = auth_headers["owner"]
    payload = {
        "prompt": "Run full system diagnostics and check health probes",
        "voice_input": False,
    }
    resp = client.post("/api/v1/terminal/command", json=payload, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "COMPLETED"
    assert data["relevant_page"]["number"] == 7  # System Health


def test_master_terminal_history(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test that terminal commands are logged to history and queryable."""
    owner_headers = auth_headers["owner"]
    # Run a command first
    client.post("/api/v1/terminal/command", json={"prompt": "Check system status"}, headers=owner_headers)
    resp = client.get("/api/v1/terminal/history", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "history" in data
    assert len(data["history"]) >= 1
    assert data["history"][0]["prompt"] == "Check system status"
