"""Tests for Caravan Phase 4 Nigeria Funding Directory and Scheduled ARGON Discovery."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient


def test_nigeria_directory_seed_schedule_trigger_and_overlap_guard(
    client: TestClient, auth_headers: dict, monkeypatch
) -> None:
    # 1. Directory endpoint lists official Nigerian institutions
    dir_res = client.get("/api/v1/caravan/discovery/nigeria-directory", headers=auth_headers["owner"])
    assert dir_res.status_code == 200
    assert dir_res.json()["total"] == 8

    # 2. VIEWER cannot seed Nigeria directory or configure schedule
    assert (
        client.post("/api/v1/caravan/discovery/nigeria-directory/seed", headers=auth_headers["viewer"]).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/caravan/command-centre/schedule",
            headers=auth_headers["viewer"],
            json={"enabled": True, "interval_seconds": 3600},
        ).status_code
        == 403
    )

    # 3. OWNER seeds Nigeria directory (idempotent on second call)
    s1 = client.post("/api/v1/caravan/discovery/nigeria-directory/seed", headers=auth_headers["owner"])
    assert s1.status_code == 200, s1.text
    assert s1.json()["added_count"] == 8
    s2 = client.post("/api/v1/caravan/discovery/nigeria-directory/seed", headers=auth_headers["owner"])
    assert s2.status_code == 200
    assert s2.json()["added_count"] == 0
    assert s2.json()["skipped_count"] == 8

    # 4. Configure, pause, and resume recurring schedule
    sch_on = client.post(
        "/api/v1/caravan/command-centre/schedule",
        headers=auth_headers["owner"],
        json={"enabled": True, "interval_seconds": 1800},
    )
    assert sch_on.status_code == 200, sch_on.text
    assert sch_on.json()["enabled"] is True
    assert sch_on.json()["interval_seconds"] == 1800

    sch_off = client.post(
        "/api/v1/caravan/command-centre/schedule",
        headers=auth_headers["owner"],
        json={"enabled": False, "interval_seconds": 1800},
    )
    assert sch_off.status_code == 200
    assert sch_off.json()["enabled"] is False

    # 5. Trigger manual discovery sweep and verify overlap guard returns 409
    trig1 = client.post("/api/v1/caravan/command-centre/trigger-discovery", headers=auth_headers["owner"])
    assert trig1.status_code == 200, trig1.text
    trig2 = client.post("/api/v1/caravan/command-centre/trigger-discovery", headers=auth_headers["owner"])
    assert trig2.status_code == 409

    # 6. Command Centre reflects scheduled_discovery telemetry
    cc = client.get("/api/v1/caravan/command-centre?days=30", headers=auth_headers["owner"])
    assert cc.status_code == 200
    sd = cc.json()["scheduled_discovery"]
    assert sd["configured"] is True
    assert sd["active_jobs_count"] == 1
    assert sd["sources_awaiting_discovery"] == 8

    # 7. Worker processes CARAVAN_DISCOVERY_SWEEP safely with mocked HTTP
    class _FakeResp:
        def __init__(self, code: int, text: str):
            self.status_code = code
            self.text = text
            self.headers = {"content-type": "text/html"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            if url.endswith("/robots.txt"):
                return _FakeResp(404, "")
            return _FakeResp(200, "<html><title>Nigerian MSME Grant Programme</title><body>Nigeria grant up to NGN 2,000,000</body></html>")

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    from app.core.config import get_settings
    from app.db.session import get_session_factory
    from app.services.job_scheduler import process_due_jobs

    settings = get_settings()
    with get_session_factory(settings)() as db:
        summary = process_due_jobs(db, settings=settings, max_jobs=5)
    assert summary["succeeded"] >= 1
