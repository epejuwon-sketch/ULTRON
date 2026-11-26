"""Tests for multi-tier memory recall, TTL pruning, governed tool execution, and SSRF protection."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_memory_store_semantic_search_and_delete(client: TestClient, auth_headers: dict) -> None:
    m1 = client.post(
        "/api/v1/memory",
        headers=auth_headers["operator"],
        json={
            "content": "Supabase PostgreSQL hosts tenant-scoped tables with pgvector and RLS policies.",
            "memory_type": "SEMANTIC",
            "namespace": "architecture",
            "importance_score": 0.9,
        },
    )
    assert m1.status_code == 201
    m2 = client.post(
        "/api/v1/memory",
        headers=auth_headers["operator"],
        json={
            "content": "Lunch catering invoice for Lagos office event.",
            "memory_type": "EPISODIC",
            "namespace": "architecture",
            "importance_score": 0.2,
        },
    )
    assert m2.status_code == 201

    search = client.post(
        "/api/v1/memory/search",
        headers=auth_headers["operator"],
        json={"query": "Supabase pgvector RLS database", "namespace": "architecture", "limit": 5},
    )
    assert search.status_code == 200
    results = search.json()["results"]
    assert len(results) == 2
    assert results[0]["memory_id"] == m1.json()["memory_id"]
    assert results[0]["relevance_score"] > results[1]["relevance_score"]

    # Delete requires OWNER/ADMIN
    assert client.delete(f"/api/v1/memory/{m2.json()['memory_id']}", headers=auth_headers["operator"]).status_code == 403
    assert client.delete(f"/api/v1/memory/{m2.json()['memory_id']}", headers=auth_headers["owner"]).status_code == 200


def test_memory_ttl_pruning(client: TestClient, auth_headers: dict) -> None:
    created = client.post(
        "/api/v1/memory",
        headers=auth_headers["operator"],
        json={"content": "Short-lived working context", "memory_type": "WORKING", "ttl_seconds": 1},
    )
    assert created.status_code == 201
    time.sleep(1.1)
    pruned = client.post("/api/v1/memory/prune", headers=auth_headers["owner"])
    assert pruned.status_code == 200
    assert pruned.json()["pruned_count"] >= 1


def test_tools_execution_approval_gate_and_ssrf_guard(client: TestClient, auth_headers: dict) -> None:
    catalog = client.get("/api/v1/tools", headers=auth_headers["operator"])
    assert catalog.status_code == 200
    assert catalog.json()["total"] == 9

    diag = client.post(
        "/api/v1/tools/system_diagnostics/execute",
        headers=auth_headers["operator"],
        json={"arguments": {}},
    )
    assert diag.status_code == 200
    assert diag.json()["status"] == "COMPLETED"
    assert diag.json()["output"]["registered_agents"] == 60

    # Below $50 soft limit -> auto-approved
    small_tx = client.post(
        "/api/v1/tools/financial_transfer_request/execute",
        headers=auth_headers["operator"],
        json={"arguments": {"amount_usd": 25.0, "currency": "USD", "destination": "API credits"}},
    )
    assert small_tx.status_code == 200
    assert small_tx.json()["status"] == "COMPLETED"
    assert small_tx.json()["output"]["gated"] is False

    # Above $50 soft limit -> gated at ApprovalGate
    large_tx = client.post(
        "/api/v1/tools/financial_transfer_request/execute",
        headers=auth_headers["operator"],
        json={"arguments": {"amount_usd": 750.0, "currency": "USD", "destination": "London Treasury"}},
    )
    assert large_tx.status_code == 200
    assert large_tx.json()["status"] == "WAITING_FOR_APPROVAL"
    assert large_tx.json()["approval_id"] is not None

    # SSRF guard blocks localhost, cloud metadata, and private IPs
    for blocked_url in (
        "http://127.0.0.1:8000/health",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "file:///etc/passwd",
    ):
        resp = client.post(
            "/api/v1/tools/http_fetch_public/execute",
            headers=auth_headers["operator"],
            json={"arguments": {"url": blocked_url}},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "SECURITY_VIOLATION"

    history = client.get("/api/v1/tools/executions/history", headers=auth_headers["operator"])
    assert history.status_code == 200
    assert history.json()["total"] >= 3
