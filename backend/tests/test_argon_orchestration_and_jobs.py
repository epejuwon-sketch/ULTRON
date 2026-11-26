"""Comprehensive ARGON orchestration tests: parallel DAG waves, pause/resume/retry, verification, idempotency, kill switch, and worker queue."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_argon_parallel_dag_waves_and_independent_verification(client: TestClient, auth_headers: dict) -> None:
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={
            "title": "Parallel Research & Security Audit",
            "objective": "Run parallel analysis and aggregate verification",
            "max_concurrency": 3,
            "custom_dag": [
                {"step_number": 1, "agent_id": "AGT-01", "description": "Decompose scope", "depends_on": []},
                {"step_number": 2, "agent_id": "AGT-02", "description": "Research branch A", "depends_on": [1]},
                {"step_number": 3, "agent_id": "AGT-20", "description": "Security branch B", "depends_on": [1]},
                {"step_number": 4, "agent_id": "AGT-25", "description": "Final verification", "depends_on": [2, 3]},
            ],
        },
    )
    assert created.status_code == 201
    tid = created.json()["task_id"]

    executed = client.post(f"/api/v1/tasks/{tid}/execute", headers=auth_headers["operator"])
    assert executed.status_code == 200
    body = executed.json()
    assert body["lifecycle_state"] == "COMPLETED"
    assert body["progress_percent"] == 100
    assert body["result"]["parallel_waves"] == 3
    assert body["verification"]["verified"] is True
    assert body["verification"]["checked_steps"] == 4


def test_argon_pause_resume_failure_retry_and_kill_switch(client: TestClient, auth_headers: dict) -> None:
    created = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={"title": "Pause/Resume Test", "objective": "Check system diagnostics"},
    )
    tid = created.json()["task_id"]

    # Pause & resume
    paused = client.post(f"/api/v1/tasks/{tid}/pause", headers=auth_headers["operator"])
    assert paused.status_code == 200
    assert paused.json()["lifecycle_state"] == "PAUSED"

    # Cannot execute while paused
    assert client.post(f"/api/v1/tasks/{tid}/execute", headers=auth_headers["operator"]).status_code == 409

    resumed = client.post(f"/api/v1/tasks/{tid}/resume", headers=auth_headers["operator"])
    assert resumed.status_code == 200
    assert resumed.json()["lifecycle_state"] == "READY"

    # Simulate failure -> retry succeeds
    failed = client.post(
        f"/api/v1/tasks/{tid}/transition",
        headers=auth_headers["operator"],
        json={"next_state": "FAILED", "error_detail": "Simulated transient worker fault"},
    )
    assert failed.status_code == 200
    retried = client.post(f"/api/v1/tasks/{tid}/retry", headers=auth_headers["operator"])
    assert retried.status_code == 200
    assert retried.json()["lifecycle_state"] == "COMPLETED"
    assert retried.json()["retry_count"] == 1

    # OWNER emergency kill-switch halts autonomous execution
    assert (
        client.put(
            "/api/v1/settings",
            headers=auth_headers["operator"],
            json={"key": "autonomous_execution_enabled", "value": False},
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/settings",
            headers=auth_headers["owner"],
            json={"key": "autonomous_execution_enabled", "value": False},
        ).status_code
        == 200
    )

    t2 = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={"title": "Blocked by Kill Switch", "objective": "Analyze telemetry"},
    ).json()["task_id"]
    blocked = client.post(f"/api/v1/tasks/{t2}/execute", headers=auth_headers["operator"])
    assert blocked.status_code == 409
    assert "kill-switch" in blocked.json()["error"]["message"]


def test_task_idempotency_key_replay_and_conflict(client: TestClient, auth_headers: dict) -> None:
    hdrs = dict(auth_headers["operator"])
    hdrs["Idempotency-Key"] = "idem-task-create-001"
    payload = {"title": "Idempotent Task", "objective": "Summarize daily system metrics"}

    first = client.post("/api/v1/tasks", headers=hdrs, json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/tasks", headers=hdrs, json=payload)
    assert second.status_code == 201
    assert second.headers.get("X-Idempotency-Replayed") == "true"
    assert second.json()["task_id"] == first.json()["task_id"]

    # Same key with different body returns 409 Conflict
    mismatch = client.post(
        "/api/v1/tasks",
        headers=hdrs,
        json={"title": "Different Task", "objective": "Different objective"},
    )
    assert mismatch.status_code == 409


def test_background_job_queue_and_scheduler(client: TestClient, auth_headers: dict) -> None:
    task = client.post(
        "/api/v1/tasks",
        headers=auth_headers["operator"],
        json={"title": "Queued Background Task", "objective": "Run async background synthesis"},
    ).json()

    enqueued = client.post(f"/api/v1/tasks/{task['task_id']}/enqueue", headers=auth_headers["operator"])
    assert enqueued.status_code == 202
    assert enqueued.json()["queued"] is True

    sched = client.post(
        "/api/v1/argon/schedules",
        headers=auth_headers["owner"],
        json={"name": "Hourly Memory Prune", "job_type": "PRUNE_MEMORY", "interval_seconds": 3600},
    )
    assert sched.status_code == 201

    processed = client.post("/api/v1/argon/jobs/process", headers=auth_headers["owner"])
    assert processed.status_code == 200
    assert processed.json()["succeeded"] >= 1

    fetched = client.get(f"/api/v1/tasks/{task['task_id']}", headers=auth_headers["operator"]).json()
    assert fetched["lifecycle_state"] == "COMPLETED"
