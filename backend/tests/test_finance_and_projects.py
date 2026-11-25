"""Tests for Financial Command Center and Developer & Coding Infrastructure."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_financial_command_center_budgets_reports_and_approval_gate(
    client: TestClient, auth_headers: dict
) -> None:
    # Create monthly API spend budget
    bdg = client.post(
        "/api/v1/finance/budgets",
        headers=auth_headers["owner"],
        json={"name": "Gemini API Monthly", "category": "ai_api", "limit_usd": 40.0, "alert_threshold_pct": 75.0},
    )
    assert bdg.status_code == 201

    # Record revenue + small API spend (triggers 80%+ budget alert notification)
    rev = client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["owner"],
        json={
            "entry_type": "REVENUE",
            "category": "saas",
            "amount_usd": 2500.0,
            "description": "Enterprise subscription",
        },
    )
    assert rev.status_code == 201
    assert rev.json()["status"] == "RECORDED"

    api_spend = client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["operator"],
        json={
            "entry_type": "API_SPEND",
            "category": "ai_api",
            "amount_usd": 35.0,
            "description": "Gemini API batch inference",
        },
    )
    assert api_spend.status_code == 201
    assert api_spend.json()["status"] == "RECORDED"

    # Owner distribution ALWAYS requires ApprovalGate and never executes live payment rails
    dist = client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["owner"],
        json={
            "entry_type": "OWNER_DISTRIBUTION",
            "category": "distribution",
            "amount_usd": 500.0,
            "description": "Q4 owner draw",
        },
    )
    assert dist.status_code == 201
    assert dist.json()["status"] == "PENDING_APPROVAL"
    assert dist.json()["payment_rail_executed"] is False
    apr_id = dist.json()["approval"]["approval_id"]

    # Approve via ApprovalGate -> transaction status updates to APPROVED
    decided = client.post(
        f"/api/v1/approvals/{apr_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "Authorized Q4 draw"},
    )
    assert decided.status_code == 200
    assert decided.json()["linked_resource_state"] == "APPROVED"

    # Investments & Reserves
    assert (
        client.post(
            "/api/v1/finance/investments",
            headers=auth_headers["owner"],
            json={"asset_name": "T-Bills", "asset_class": "TREASURY", "cost_basis_usd": 10000.0, "current_value_usd": 10450.0},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/finance/reserves",
            headers=auth_headers["owner"],
            json={"name": "Operating Buffer", "balance_usd": 15000.0, "target_usd": 20000.0},
        ).status_code
        == 201
    )

    report = client.get("/api/v1/finance/reports/summary", headers=auth_headers["owner"]).json()
    assert report["total_revenue_usd"] == 2500.0
    assert report["total_expenses_usd"] >= 35.0
    assert report["owner_distributions_usd"] == 500.0
    assert report["total_reserves_usd"] == 15000.0
    assert report["live_payment_rail_connected"] is False

    fin_audit = client.get("/api/v1/finance/audit", headers=auth_headers["owner"]).json()
    assert fin_audit["total"] >= 4


def test_developer_projects_ast_analysis_code_proposals_and_deployment_rollback(
    client: TestClient, auth_headers: dict
) -> None:
    prj = client.post(
        "/api/v1/projects",
        headers=auth_headers["operator"],
        json={
            "name": "ULTRON OS Backend",
            "repo_full_name": "epejuwon-sketch/ULTRON",
            "budget_usd": 5000.0,
        },
    )
    assert prj.status_code == 201
    pid = prj.json()["project_id"]

    # Local git repository inspection
    repo = client.get(f"/api/v1/projects/{pid}/repository", headers=auth_headers["operator"])
    assert repo.status_code == 200
    assert repo.json()["local_git"]["available"] is True

    # Real Python AST static security analysis catches eval()
    analysis = client.post(
        f"/api/v1/projects/{pid}/analyze",
        headers=auth_headers["operator"],
        json={"filename": "sample.py", "source_code": "def run(x):\n    return eval(x)\n"},
    )
    assert analysis.status_code == 200
    assert analysis.json()["analysis"]["syntax_valid"] is True
    assert len(analysis.json()["analysis"]["security_findings"]) >= 1

    # Code generation proposal never auto-applies
    proposal = client.post(
        f"/api/v1/projects/{pid}/code-proposals",
        headers=auth_headers["operator"],
        json={"specification": "Add health latency histogram", "target_branch": "feat/latency-hist"},
    )
    assert proposal.status_code == 200
    assert proposal.json()["auto_applied"] is False
    assert proposal.json()["requires_human_review"] is True

    # Production deployment requires ApprovalGate -> OWNER approves -> rollback works
    dep = client.post(
        f"/api/v1/projects/{pid}/deployments",
        headers=auth_headers["operator"],
        json={"environment": "production", "git_ref": "v2026.2.0", "previous_ref": "v2026.1.0"},
    )
    assert dep.status_code == 201
    assert dep.json()["status"] == "WAITING_FOR_APPROVAL"
    dep_id = dep.json()["deployment_id"]
    apr_id = dep.json()["approval"]["approval_id"]

    approved = client.post(
        f"/api/v1/approvals/{apr_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "CI green"},
    )
    assert approved.json()["linked_resource_state"] == "APPROVED_READY_TO_DEPLOY"

    # Rollback requires OWNER (`projects:deploy`)
    assert (
        client.post(
            f"/api/v1/projects/{pid}/deployments/{dep_id}/rollback",
            headers=auth_headers["operator"],
            json={"reason": "Unauthorized rollback"},
        ).status_code
        == 403
    )
    rb = client.post(
        f"/api/v1/projects/{pid}/deployments/{dep_id}/rollback",
        headers=auth_headers["owner"],
        json={"reason": "Latency regression"},
    )
    assert rb.status_code == 200
    assert rb.json()["status"] == "ROLLED_BACK"


def test_financial_milestones_tracking_endpoint(client: TestClient, auth_headers: dict) -> None:
    res = client.get("/api/v1/finance/milestones", headers=auth_headers["owner"])
    assert res.status_code == 200
    data = res.json()
    assert "reserve_milestone_feb_2027" in data
    assert data["reserve_milestone_feb_2027"]["target_amount_ngn"] == 50_000_000.0
    assert "range_rover_milestone" in data
    assert data["range_rover_milestone"]["post_purchase_balance_target_ngn"] == 300_000_000.0
    assert data["range_rover_milestone"]["ready_for_purchase"] is False
    assert len(data["planned_purchases"]["items"]) >= 15
    assert len(data["financial_priority_order"]) == 7
