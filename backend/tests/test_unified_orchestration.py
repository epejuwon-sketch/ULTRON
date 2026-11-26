"""Tests for unified natural-language NEON + ARGON + Ecosystem orchestration (/api/v1/orchestrate)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_unified_natural_language_orchestration_low_risk_and_approval_gated(
    client: TestClient, auth_headers: dict
) -> None:
    # Seed a memory so orchestration recalls real context
    client.post(
        "/api/v1/memory",
        headers=auth_headers["operator"],
        json={"content": "Supabase PostgreSQL uses pgvector and RLS in ULTRON OS 2026.", "memory_type": "SEMANTIC"},
    )

    # Low-risk natural-language objective -> NEON routes & ARGON executes + verifies end-to-end
    res = client.post(
        "/api/v1/orchestrate",
        headers=auth_headers["operator"],
        json={"objective": "Review our Supabase PostgreSQL schema and index optimization strategy"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["executed"] is True
    assert body["orchestration_status"] == "COMPLETED"
    assert body["neon_routing"]["selected_agent_id"] == "AGT-28"
    assert body["context_used"]["recalled_memories"] >= 1
    assert body["task"]["verification"]["verified"] is True

    # High-value objective -> NEON + ARGON automatically halt at ApprovalGate
    gated = client.post(
        "/api/v1/orchestrate",
        headers=auth_headers["operator"],
        json={"objective": "Execute wire transfer for cloud infrastructure invoice", "financial_amount_usd": 1200.0},
    )
    assert gated.status_code == 200
    gbody = gated.json()
    assert gbody["executed"] is False
    assert gbody["requires_approval"] is True
    assert gbody["orchestration_status"] == "WAITING_FOR_APPROVAL"
    assert gbody["approval"]["approval_id"] is not None
