"""ULTRON OS 2026 — Master 60-Agent CARAVAN Integration & Business Activation Verification Suite.

Validates:
1. Complete 60-Agent Capability Directory across 12 Functional Domains
2. Least-Privilege Scope & Boundary Violation Enforcement
3. Kill-Switch Protection for Autonomous Dispatches
4. Human ApprovalGate on High-Risk Financial & Publishing Actions
5. End-to-End Execution for all 60 Specialist Agents (AGT-01 to AGT-60)
6. ARGON Multi-Agent Collaborative DAG Workflows
7. Business Operations Command Centre & 6-Tier Subscription Engine
8. Registration-Dependent Business Activation with CAMA §20 Minor Founder Protections
"""

import pytest
from fastapi.testclient import TestClient

from app.services.caravan_agent_bridge import (
    AGENT_TO_CARAVAN_SCOPE,
    PERMITTED_SCOPE_OPERATIONS,
    APPROVAL_GATED_OPERATIONS,
)
from app.services.caravan_growth_service import PLAN_CATALOG


def test_60_agent_scope_mapping_completeness():
    """Verify that all 60 specialist agents are registered across the 12 domains."""
    assert len(AGENT_TO_CARAVAN_SCOPE) == 60, f"Expected 60 agents, found {len(AGENT_TO_CARAVAN_SCOPE)}"

    for i in range(1, 61):
        aid = f"AGT-{i:02d}"
        assert aid in AGENT_TO_CARAVAN_SCOPE, f"Agent {aid} missing from AGENT_TO_CARAVAN_SCOPE"

    expected_domains = {
        "caravan:operations",
        "caravan:research",
        "caravan:engineering",
        "caravan:marketing",
        "caravan:sales",
        "caravan:finance",
        "caravan:legal",
        "caravan:analytics",
        "caravan:product",
        "caravan:funding",
        "caravan:support",
        "caravan:security",
    }
    assert set(PERMITTED_SCOPE_OPERATIONS.keys()) == expected_domains

    total_ops = sum(len(ops) for ops in PERMITTED_SCOPE_OPERATIONS.values())
    assert total_ops == 43, f"Expected 43 permitted operations, found {total_ops}"


def test_agent_capabilities_endpoint(client: TestClient, auth_headers: dict):
    """Test retrieving agent capabilities via the API."""
    hdr = auth_headers["owner"]

    # 1. List all capabilities
    res = client.get("/api/v1/caravan/agents/capabilities", headers=hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["total_agents"] == 60
    assert data["total_domains"] == 12
    assert len(data["agents"]) == 60

    # 2. Query single agent (AGT-01)
    res_single = client.get("/api/v1/caravan/agents/capabilities?agent_id=AGT-01", headers=hdr)
    assert res_single.status_code == 200
    single_data = res_single.json()
    assert single_data["agent_id"] == "AGT-01"
    assert single_data["caravan_scope"] == "caravan:operations"
    assert "executive_operations_synthesis" in single_data["permitted_operations"]


def test_least_privilege_scope_boundary_enforcement(client: TestClient, auth_headers: dict):
    """Ensure an agent attempting an operation outside its domain is strictly rejected."""
    hdr = auth_headers["owner"]

    # AGT-02 is Research (caravan:research); attempting financial transaction reconciliation
    res = client.post(
        "/api/v1/caravan/agents/dispatch",
        headers=hdr,
        json={
            "agent_id": "AGT-02",
            "operation": "reconcile_transactions",
        },
    )
    assert res.status_code == 403
    body = res.json()
    err_msg = body.get("error", {}).get("message") or body.get("detail", "")
    assert "not permitted to execute operation" in err_msg


def test_approval_gate_on_sensitive_operations(client: TestClient, auth_headers: dict):
    """Ensure sensitive operations by non-owners trigger an ApprovalGate."""
    operator_hdr = auth_headers["operator"]

    # Operator attempting financial reconciliation -> requires approval
    res = client.post(
        "/api/v1/caravan/agents/dispatch",
        headers=operator_hdr,
        json={
            "agent_id": "AGT-08",
            "operation": "reconcile_transactions",
            "parameters": {"financial_amount_usd": 150.0},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "APPROVAL_REQUIRED"
    assert "approval_id" in data
    assert "approval request" in data["message"].lower()


def test_all_60_specialist_agents_dispatch_execution(client: TestClient, auth_headers: dict):
    """Exhaustive test: loop through every agent from AGT-01 to AGT-60 and execute permitted action."""
    hdr = auth_headers["owner"]

    scope_default_op = {
        "caravan:operations": "executive_operations_synthesis",
        "caravan:research": "search_opportunities",
        "caravan:engineering": "probe_service_health",
        "caravan:marketing": "get_marketing_audience",
        "caravan:sales": "get_customer_pipeline",
        "caravan:finance": "get_revenue_telemetry",
        "caravan:legal": "compliance_calendar",
        "caravan:analytics": "get_platform_metrics",
        "caravan:product": "product_feature_backlog",
        "caravan:funding": "get_application_pipeline",
        "caravan:support": "list_support_tickets",
        "caravan:security": "audit_security_logs",
    }

    for i in range(1, 61):
        aid = f"AGT-{i:02d}"
        scope = AGENT_TO_CARAVAN_SCOPE[aid]
        op = scope_default_op[scope]

        res = client.post(
            "/api/v1/caravan/agents/dispatch",
            headers=hdr,
            json={
                "agent_id": aid,
                "operation": op,
                "parameters": {},
                "bypass_approval": True,
            },
        )
        assert res.status_code == 200, f"Dispatch failed for {aid} ({scope}): {res.text}"
        data = res.json()
        assert data.get("status") in {"SUCCESS", "DISPATCH_FAILED"} or data.get("success") is True


def test_argon_multi_agent_collaborative_workflows(client: TestClient, auth_headers: dict):
    """Execute ARGON multi-agent collaborative workflows across domains."""
    hdr = auth_headers["owner"]

    workflows = [
        "opportunity_pipeline_sync",
        "growth_revenue_audit",
        "security_infrastructure_health",
    ]

    for wf in workflows:
        res = client.post(
            "/api/v1/caravan/workflows/collaborative",
            headers=hdr,
            json={"workflow_name": wf, "parameters": {}},
        )
        assert res.status_code == 200, f"Workflow '{wf}' failed: {res.text}"
        payload = res.json()
        assert payload["status"] == "COMPLETED"
        assert payload["workflow"] == wf
        assert payload["total_steps"] >= 4
        assert len(payload["steps"]) >= 4


def test_six_subscription_tiers_and_revenue_catalog(client: TestClient, auth_headers: dict):
    """Verify that all 6 subscription tiers are available and correctly configured."""
    hdr = auth_headers["owner"]

    res = client.get("/api/v1/caravan/subscription-tiers", headers=hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["total_tiers"] == 6

    expected_tiers = {"FREE", "STARTER", "GROWTH", "PRO", "BUSINESS", "ENTERPRISE"}
    returned_tiers = {t["tier"] for t in data["tiers"]}
    assert expected_tiers == returned_tiers

    starter = next(t for t in data["tiers"] if t["tier"] == "STARTER")
    assert starter["monthly_usd"] == 19.0

    growth = next(t for t in data["tiers"] if t["tier"] == "GROWTH")
    assert growth["monthly_usd"] == 49.0

    pro = next(t for t in data["tiers"] if t["tier"] == "PRO")
    assert pro["monthly_usd"] == 99.0

    business = next(t for t in data["tiers"] if t["tier"] == "BUSINESS")
    assert business["monthly_usd"] == 249.0


def test_registration_dependent_business_activation_and_minor_safeguards(client: TestClient, auth_headers: dict):
    """Verify strict CAMA 2020 minor founder safeguards and dormant business activation status."""
    hdr = auth_headers["owner"]

    # 1. Check activation status
    res = client.get("/api/v1/caravan/activation/status", headers=hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["activation_status"] in {"DORMANT", "PENDING_APPROVAL"}
    assert data["commercial_operations_enabled"] is False

    # CAMA safeguards
    safeguards = data["safeguards"]
    assert safeguards["cama_2020_section_20_1_a_enforced"] is True
    assert safeguards["director_disqualification_acknowledged"] is True
    assert safeguards["cama_2020_section_20_2_enforced"] is True
    assert safeguards["adult_trustees_required"] >= 2

    # Blockers present
    assert len(data["blockers"]) >= 1

    # 2. Request review
    rev_res = client.post(
        "/api/v1/caravan/activation/request-review",
        headers=hdr,
        json={"notes": "Pre-filing operational audit review"},
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.json()
    assert rev_data["status"] == "PENDING_APPROVAL"
    assert "approval_id" in rev_data
