"""Tests for ARGON task orchestration, DAG cycle detection, and ApprovalGate workflow."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_low_risk_task_plan_and_execution_creates_memory(client: TestClient, auth_headers: dict) -> None:
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={
            "title": "Architecture Review",
            "objective": "Review Python FastAPI architecture and database index design",
            "financial_amount_usd": 0.0,
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["lifecycle_state"] == "READY"
    assert task["approval"] is None
    assert len(task["steps"]) == 3

    executed = client.post(f"/api/v1/tasks/{task['task_id']}/execute", headers=auth_headers["operator"])
    assert executed.status_code == 200
    done = executed.json()
    assert done["lifecycle_state"] == "COMPLETED"
    assert all(s["status"] == "COMPLETED" for s in done["steps"])

    # Episodic memory should have been indexed automatically
    mem = client.post(
        "/api/v1/memory/search",
        headers=auth_headers["operator"],
        json={"query": "Architecture Review FastAPI", "namespace": "task_executions"},
    )
    assert mem.status_code == 200
    assert mem.json()["total_matches"] >= 1


def test_custom_dag_circular_dependency_rejected(client: TestClient, auth_headers: dict) -> None:
    bad = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={
            "title": "Cyclic DAG",
            "objective": "Test cycle detection",
            "custom_dag": [
                {"step_number": 1, "agent_id": "AGT-01", "description": "Step 1", "depends_on": [2]},
                {"step_number": 2, "agent_id": "AGT-03", "description": "Step 2", "depends_on": [1]},
            ],
        },
    )
    assert bad.status_code == 422
    assert "Circular dependency" in bad.json()["error"]["message"]


def test_approval_gate_blocks_high_value_task_until_owner_approves(
    client: TestClient, auth_headers: dict
) -> None:
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={
            "title": "Vendor Settlement",
            "objective": "Execute wire transfer to cloud vendor",
            "financial_amount_usd": 500.0,
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["lifecycle_state"] == "WAITING_FOR_APPROVAL"
    approval_id = task["approval"]["approval_id"]

    # Direct execution is blocked
    assert (
        client.post(f"/api/v1/tasks/{task['task_id']}/execute", headers=auth_headers["operator"]).status_code
        == 409
    )
    # Manual transition bypass is blocked
    assert (
        client.post(
            f"/api/v1/tasks/{task['task_id']}/transition",
            headers=auth_headers["owner"],
            json={"next_state": "READY"},
        ).status_code
        == 409
    )
    # OPERATOR cannot approve
    assert (
        client.post(
            f"/api/v1/approvals/{approval_id}/decide",
            headers=auth_headers["operator"],
            json={"decision": "APPROVED", "note": "Unauthorized attempt"},
        ).status_code
        == 403
    )

    # OWNER approves -> linked task moves to READY -> can now execute
    decided = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "Verified invoice #2026-11"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "APPROVED"
    assert decided.json()["linked_task_state"] == "READY"

    executed = client.post(f"/api/v1/tasks/{task['task_id']}/execute", headers=auth_headers["operator"])
    assert executed.status_code == 200
    assert executed.json()["lifecycle_state"] == "COMPLETED"


def test_approval_gate_rejection_cancels_task(client: TestClient, auth_headers: dict) -> None:
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={
            "title": "Risky Prod Mutation",
            "objective": "Deploy production hotfix and drop table cache",
            "financial_amount_usd": 0.0,
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["lifecycle_state"] == "WAITING_FOR_APPROVAL"
    approval_id = task["approval"]["approval_id"]

    rejected = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "REJECTED", "note": "Requires maintenance window"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["linked_task_state"] == "CANCELLED"

    fetched = client.get(f"/api/v1/tasks/{task['task_id']}", headers=auth_headers["owner"]).json()
    assert fetched["lifecycle_state"] == "CANCELLED"
