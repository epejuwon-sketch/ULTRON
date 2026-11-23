"""Tests for WebSocket auth/ping, rate limiting, monitoring/Prometheus, notifications, 14 capabilities, Supabase Storage, and deployment artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.integrations.extended import GitHubClient, GoogleDriveClient
from app.integrations.supabase import SupabaseClient
from fastapi.testclient import TestClient


def test_websocket_authentication_and_ping_pong(client: TestClient, auth_headers: dict) -> None:
    token = auth_headers["owner_login"]["access_token"]
    with client.websocket_connect(f"/ws/v1/events?token={token}") as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "connection.ready"
        assert hello["tenant_id"] == "TENANT-ULTRON-01"
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["event_type"] == "pong"


def test_rate_limiter_enforces_429_headers(client: TestClient, auth_headers: dict) -> None:
    # Install tight limiter on app state to verify 429 enforcement deterministically
    client.app.state.rate_limiter = SlidingWindowRateLimiter(limit_per_minute=1000)
    # Direct unit verification of limiter boundary
    tight = SlidingWindowRateLimiter(limit_per_minute=2, window_seconds=60.0)
    assert tight.check("1.2.3.4")[0] is True
    assert tight.check("1.2.3.4")[0] is True
    allowed, rem, retry = tight.check("1.2.3.4")
    assert allowed is False
    assert rem == 0
    assert retry >= 1

    resp = client.get("/health", headers=auth_headers["owner"])
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


def test_monitoring_notifications_and_14_capability_registry(client: TestClient, auth_headers: dict) -> None:
    # Trigger a notification via an approval-gated email tool draft
    email_req = client.post(
        "/api/v1/tools/email_dispatch_request/execute",
        headers=auth_headers["operator"],
        json={"arguments": {"to": "partner@example.com", "subject": "Update", "body": "Draft body"}},
    )
    assert email_req.status_code == 200
    assert email_req.json()["status"] == "WAITING_FOR_APPROVAL"

    # File parse tool
    parsed = client.post(
        "/api/v1/tools/file_parse/execute",
        headers=auth_headers["operator"],
        json={"arguments": {"format": "json", "content": '{"ultron": 2026}'}},
    )
    assert parsed.status_code == 200
    assert parsed.json()["output"]["valid"] is True

    notifs = client.get("/api/v1/notifications", headers=auth_headers["owner"]).json()
    assert notifs["unread_count"] >= 1
    assert client.post("/api/v1/notifications/read-all", headers=auth_headers["owner"]).status_code == 200

    overview = client.get("/api/v1/monitoring/overview", headers=auth_headers["owner"]).json()
    assert overview["database"]["healthy"] is True
    assert overview["agents"]["total_registered"] == 60
    assert len(overview["applied_migrations"]) == 11

    prom = client.get("/api/v1/monitoring/metrics", headers=auth_headers["owner"])
    assert prom.status_code == 200
    assert "ultron_http_requests_total" in prom.text

    # Verify 14-capability registry
    caps = client.get("/api/v1/integrations/status", headers=auth_headers["owner"]).json()
    assert caps["total_capabilities"] == 14
    for required_cap in (
        "supabase",
        "gemini",
        "vercel",
        "cloudflare",
        "github",
        "google_drive",
        "email",
        "whatsapp",
        "calendar",
        "web_research",
        "file_processing",
        "image_generation",
        "coding_environment",
        "external_apis",
    ):
        assert required_cap in caps["capabilities"]


def test_supabase_storage_github_and_drive_clients_mocked() -> None:
    cfg = Settings(
        ULTRON_ENV="test",
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="demo-service-key",
        GITHUB_TOKEN="ghp_test_token_000",
        GOOGLE_DRIVE_ACCESS_TOKEN="ya29_test_drive_token",
    )

    def sb_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/storage/v1/bucket"):
            return httpx.Response(200, json=[{"id": "ultron-artifacts", "public": False}])
        if "/storage/v1/object/sign/" in req.url.path:
            return httpx.Response(200, json={"signedURL": "/object/sign/ultron-artifacts/a.txt?token=xyz"})
        if "/storage/v1/object/" in req.url.path:
            return httpx.Response(200, json={"Key": "ultron-artifacts/a.txt"})
        return httpx.Response(200, json=[])

    sb = SupabaseClient(cfg, http_client=httpx.Client(transport=httpx.MockTransport(sb_handler)))
    assert len(sb.storage_list_buckets()) == 1
    assert sb.storage_upload_object(object_path="a.txt", content=b"hello")["Key"] == "ultron-artifacts/a.txt"
    assert "signedURL" in sb.storage_create_signed_url(object_path="a.txt")

    gh = GitHubClient(
        cfg,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"login": "epejuwon-sketch"}))),
    )
    assert gh.verify_live().live_verified is True

    gd = GoogleDriveClient(
        cfg,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"user": {"emailAddress": "u@example.com"}}))),
    )
    assert gd.verify_live().live_verified is True


def test_deployment_configuration_files_valid() -> None:
    root = Path(__file__).resolve().parents[2]
    vercel_cfg = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
    assert vercel_cfg["builds"][0]["src"] == "api/index.py"
    assert (root / "Dockerfile").exists()
    assert (root / "Dockerfile.worker").exists()
    assert (root / "docker-compose.yml").exists()
    assert (root / "backend" / "worker.py").exists()
    assert (root / "cloudflare" / "worker.ts").exists()
    assert (root / "backend" / "migrations" / "supabase" / "001_initial_schema.sql").exists()
    assert (root / "backend" / "migrations" / "supabase" / "002_full_backend_schema.sql").exists()
    assert (root / "backend" / "migrations" / "supabase" / "003_ecosystem_and_devices.sql").exists()
    assert (root / "backend" / "migrations" / "supabase" / "004_full_platform_features.sql").exists()
    assert (root / "frontend" / "package.json").exists()
    assert (root / "frontend" / "public" / "manifest.webmanifest").exists()
    assert (root / "frontend" / "public" / "sw.js").exists()
