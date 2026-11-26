"""Tests for CARAVAN live status probe, remote S2S bridge operations, and Connection Center verification."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.permissions import Principal, Role
from app.services.caravan_command_service import (
    probe_caravan_live,
    execute_remote_caravan_sweep,
    execute_remote_caravan_discovery,
)
from app.services.integration_manager import verify_provider_live


def test_caravan_live_probe_against_production(client: TestClient, auth_headers: dict) -> None:
    """Verify live status endpoint probes the live production CARAVAN instance."""
    res = client.get("/api/v1/caravan/live-status", headers=auth_headers["owner"])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["name"] == "CARAVAN Standalone Platform"
    assert data["deployed_url"] == "https://caravan-juwon2.vercel.app"
    assert data["branch"] == "main"
    assert data["deployment_status"] == "READY"
    assert data["backend_health"] == "VERIFIED_LIVE"
    assert data["database_status"] == "CONNECTED"
    assert data["environment"] == "production"
    assert data["health_latency_ms"] > 0


def test_caravan_connection_center_live_verification(client: TestClient, auth_headers: dict) -> None:
    """Verify CARAVAN card in Connection Center can be live verified honestly."""
    res = client.post("/api/v1/integrations/caravan/verify", headers=auth_headers["owner"])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["provider"] == "caravan"
    assert data["live_verified"] is True
    assert data["capability_state"] == "AVAILABLE"
    assert "CARAVAN live production healthy" in data["detail"]
    assert data["latency_ms"] > 0


def test_remote_caravan_discovery_trigger(client: TestClient, auth_headers: dict) -> None:
    """Verify triggering remote CARAVAN discovery cycle from ULTRON."""
    # VIEWER cannot trigger remote discovery
    viewer_res = client.post("/api/v1/caravan/remote/discovery", headers=auth_headers["viewer"])
    assert viewer_res.status_code == 403

    # OWNER triggers remote discovery
    owner_res = client.post("/api/v1/caravan/remote/discovery", headers=auth_headers["owner"])
    assert owner_res.status_code == 200, owner_res.text
    body = owner_res.json()
    assert body["status"] == "COMPLETED"
    assert body["job"] == "AUTONOMOUS_DAILY_FUNDING_DISCOVERY"
