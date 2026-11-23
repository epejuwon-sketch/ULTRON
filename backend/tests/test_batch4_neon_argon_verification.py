"""Batch 4 tests: ARGON outcome classification (completed/partial/failed/unverified) and ApprovalGate."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.argon_orchestrator import verify_task_results
from fastapi.testclient import TestClient


def test_verify_task_results_distinguishes_all_four_outcomes() -> None:
    completed_step = SimpleNamespace(
        step_number=1,
        agent_id="AGT-01",
        status="COMPLETED",
        output_json='{"output": "Done", "agent_id": "AGT-01", "execution_mode": "local_deterministic_fallback"}',
        error_detail=None,
    )
    failed_step = SimpleNamespace(
        step_number=2,
        agent_id="AGT-02",
        status="FAILED",
        output_json="{}",
        error_detail="Upstream timeout",
    )
    unverified_step = SimpleNamespace(
        step_number=3,
        agent_id="AGT-25",
        status="COMPLETED",
        output_json="{}",
        error_detail=None,
    )

    assert verify_task_results([completed_step])["outcome_classification"] == "COMPLETED"
    assert verify_task_results([completed_step, failed_step])["outcome_classification"] == "PARTIALLY_COMPLETED"
    assert verify_task_results([failed_step])["outcome_classification"] == "FAILED"
    assert verify_task_results([unverified_step])["outcome_classification"] == "UNVERIFIED"


def test_argon_task_execution_returns_outcome_classification_and_approval_gate(
    client: TestClient, auth_headers: dict
) -> None:
    # Low-spend task executes and passes verification
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["owner"],
        json={
            "title": "Verify Batch 4 DAG",
            "objective": "Audit NEON model routing and verify ARGON DAG execution",
            "preferred_agent_id": "AGT-20",
            "financial_amount_usd": 0.0,
        },
    )
    assert created.status_code == 201
    tid = created.json()["task_id"]

    executed = client.post(f"/api/v1/tasks/{tid}/execute", headers=auth_headers["owner"])
    assert executed.status_code == 200
    body = executed.json()
    assert body["lifecycle_state"] == "COMPLETED"
    assert body["verification"]["outcome_classification"] == "COMPLETED"
    assert body["steps"][0]["attempt_count"] >= 1
    assert isinstance(body["steps"][1]["depends_on"], list)

    # High-spend task requires ApprovalGate before execution
    gated = client.post(
        "/api/v1/tasks",
        headers=auth_headers["owner"],
        json={
            "title": "High-Spend Cloud Provisioning",
            "objective": "Provision GPU cluster",
            "preferred_agent_id": "AGT-21",
            "financial_amount_usd": 250.0,
        },
    )
    assert gated.status_code == 201
    assert gated.json()["lifecycle_state"] == "WAITING_FOR_APPROVAL"
