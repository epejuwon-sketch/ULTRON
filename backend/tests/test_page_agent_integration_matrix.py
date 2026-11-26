"""Comprehensive test suite for the 112-Page <-> 60-Agent Integration Matrix.

Verifies:
1. All 112 pages exist exactly once sequentially (001 to 112) without gaps or duplicates.
2. Every page has an explicit owner (primary_agent or backend_service).
3. All primary and supporting agents exist in the 60-agent catalog (AGT-01 to AGT-60).
4. All 60 specialist agents are accounted for in the registry.
5. All endpoints (/api/v1/agents/page-matrix, /api/v1/agents/{agent_id}/pages,
   /api/v1/pages, /api/v1/pages/{page_id}, /api/v1/pages/{page_id}/agents) return
   truthful, typed data and enforce RBAC permissions.
6. CARAVAN and Master Terminal integration specs are strictly validated.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.agent_catalog import AGENT_CATALOG_60
from app.services.page_agent_registry import (
    PAGE_INTEGRATION_MATRIX,
    get_page_spec,
    get_pages_for_agent,
    validate_registry_integrity,
)


def test_registry_integrity_direct():
    """Verify registry integrity function validates 112 pages with zero errors."""
    validation = validate_registry_integrity()
    assert validation["valid"] is True, f"Registry integrity failed: {validation['errors']}"
    assert validation["total_pages"] == 112
    assert len(validation["errors"]) == 0


def test_112_pages_strictly_sequential():
    """Verify all 112 numbers from 1 to 112 are present without gaps."""
    numbers = [p["number"] for p in PAGE_INTEGRATION_MATRIX]
    assert len(numbers) == 112
    assert sorted(numbers) == list(range(1, 113))

    page_ids = [p["page_id"] for p in PAGE_INTEGRATION_MATRIX]
    assert len(page_ids) == 112
    expected_ids = [f"{i:03d}" for i in range(1, 113)]
    assert page_ids == expected_ids


def test_every_page_has_defined_owner_and_service():
    """Verify that every page has an owner: either a primary agent or a backend service."""
    for p in PAGE_INTEGRATION_MATRIX:
        assert p["name"], f"Page {p['page_id']} has no name"
        assert p["subsystem"], f"Page {p['page_id']} has no subsystem"
        assert p["module_id"], f"Page {p['page_id']} has no module_id"
        assert p["subpage_id"], f"Page {p['page_id']} has no subpage_id"
        assert p["backend_service"], f"Page {p['page_id']} missing backend_service"
        assert isinstance(p["available_tools"], list)
        assert isinstance(p["required_permissions"], list)
        assert isinstance(p["api_endpoints"], list)
        assert p["operational_status"] in {"OPERATIONAL", "PARTIALLY_OPERATIONAL", "PLANNED"}
        assert p["integration_status"] in {"VERIFIED", "NOT VERIFIED"}

        # Owner rule: If primary_agent is None, backend_service must be specified
        has_owner = bool(p["primary_agent"]) or bool(p["backend_service"])
        assert has_owner, f"Page {p['page_id']} has no primary agent and no backend service"


def test_all_referenced_agents_exist_in_60_agent_catalog():
    """Verify that all referenced agent IDs exist in AGENT_CATALOG_60."""
    valid_agents = frozenset(a[0] for a in AGENT_CATALOG_60)
    assert len(valid_agents) == 60, f"Expected 60 agents, found {len(valid_agents)}"

    for p in PAGE_INTEGRATION_MATRIX:
        if p["primary_agent"]:
            assert p["primary_agent"] in valid_agents, (
                f"Page {p['page_id']} primary_agent {p['primary_agent']} not in AGENT_CATALOG_60"
            )
        for sup in p["supporting_agents"]:
            assert sup in valid_agents, (
                f"Page {p['page_id']} supporting_agent {sup} not in AGENT_CATALOG_60"
            )


def test_all_60_agents_mapped():
    """Verify that every agent in AGENT_CATALOG_60 is active and assigned across the matrix."""
    valid_agents = [a[0] for a in AGENT_CATALOG_60]
    unmapped = []
    for aid in valid_agents:
        pages = get_pages_for_agent(aid)
        total = pages["total_owned"] + pages["total_supporting"]
        if total == 0:
            unmapped.append(aid)

    assert len(unmapped) == 0, f"Agents with zero mapped pages: {unmapped}"


def test_caravan_and_terminal_page_specs():
    """Verify Pages 086-090 (CARAVAN) and Page 112 (Master Terminal)."""
    p86 = get_page_spec(86)
    assert p86 is not None
    assert p86["primary_agent"] == "AGT-01"
    assert "caravan_command_service" in p86["backend_service"]

    p87 = get_page_spec("087")
    assert p87 is not None
    assert p87["primary_agent"] == "AGT-56"
    assert "caravan_product_service" in p87["backend_service"]

    p88 = get_page_spec(88)
    assert p88 is not None
    assert p88["primary_agent"] == "AGT-10"
    assert "caravan_product_service" in p88["backend_service"]

    p90 = get_page_spec(90)
    assert p90 is not None
    assert p90["primary_agent"] == "AGT-56"
    assert "caravan_discovery_service" in p90["backend_service"]

    p112 = get_page_spec(112)
    assert p112 is not None
    assert p112["page_id"] == "112"
    assert p112["name"] == "ULTRON Master Terminal"
    assert p112["primary_agent"] == "AGT-01"
    assert "AGT-60" in p112["supporting_agents"]
    assert "terminal_router" in p112["backend_service"]
    assert p112["integration_status"] == "VERIFIED"


def test_api_agents_page_matrix_endpoint(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test GET /api/v1/agents/page-matrix."""
    headers = auth_headers["owner"]
    res = client.get("/api/v1/agents/page-matrix", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_pages"] == 112
    assert data["valid"] is True
    assert len(data["matrix"]) == 112


def test_api_agents_pages_by_agent_endpoint(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test GET /api/v1/agents/{agent_id}/pages."""
    headers = auth_headers["owner"]
    res = client.get("/api/v1/agents/AGT-01/pages", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "AGT-01"
    assert data["total_owned"] > 0
    assert any(p["page_id"] == "112" for p in data["primary_pages"])
    assert any(p["page_id"] == "001" for p in data["primary_pages"])

    # Invalid agent returns 404
    res_invalid = client.get("/api/v1/agents/AGT-999/pages", headers=headers)
    assert res_invalid.status_code == 404


def test_api_pages_endpoints(client: TestClient, auth_headers: dict[str, dict[str, str]]):
    """Test GET /api/v1/pages, /api/v1/pages/{page_id}, and /api/v1/pages/{page_id}/agents."""
    headers = auth_headers["owner"]

    # 1. List all pages
    res_list = client.get("/api/v1/pages", headers=headers)
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] == 112
    assert list_data["valid"] is True

    # 2. Filter by primary_agent
    res_filtered = client.get("/api/v1/pages?primary_agent=AGT-01", headers=headers)
    assert res_filtered.status_code == 200
    filt_data = res_filtered.json()
    assert filt_data["total"] > 0
    assert all(p["primary_agent"] == "AGT-01" for p in filt_data["pages"])

    # 3. Get single page spec
    res_page = client.get("/api/v1/pages/112", headers=headers)
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert page_data["page_id"] == "112"
    assert page_data["primary_agent"] == "AGT-01"

    # 4. Get page agents
    res_agents = client.get("/api/v1/pages/112/agents", headers=headers)
    assert res_agents.status_code == 200
    agents_data = res_agents.json()
    assert agents_data["page_id"] == "112"
    assert agents_data["primary_agent"] == "AGT-01"
    assert "AGT-60" in agents_data["supporting_agents"]
    assert "terminal_router" in agents_data["backend_service"]

    # 5. Non-existent page
    res_404 = client.get("/api/v1/pages/999", headers=headers)
    assert res_404.status_code == 404


def test_rbac_unauthenticated_access_blocked(client: TestClient):
    """Test that page registry endpoints reject unauthenticated requests."""
    res = client.get("/api/v1/agents/page-matrix")
    assert res.status_code == 401

    res_pages = client.get("/api/v1/pages")
    assert res_pages.status_code == 401
