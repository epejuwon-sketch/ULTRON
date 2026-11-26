"""Tests for Multi-Device Connectivity Mesh, permissions, cross-device sync, revocation, and Desktop Agent folder sandbox."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_device_pairing_permissions_cross_device_sync_and_revocation(
    client: TestClient, auth_headers: dict
) -> None:
    # Empty state initially
    empty = client.get("/api/v1/devices", headers=auth_headers["owner"]).json()
    assert empty["total"] == 0
    assert empty["empty_state"] is not None

    # 1. Init pairing code for Windows desktop
    init_resp = client.post(
        "/api/v1/devices/pair/init",
        headers=auth_headers["owner"],
        json={
            "target_platform": "windows",
            "requested_permissions": {"authorized_folder_read": True, "camera": False},
            "authorized_folders": ["C:/Users/Owner/ULTRON_Workspace"],
        },
    )
    assert init_resp.status_code == 201
    pair_code = init_resp.json()["pairing_code"]

    # 2. Complete pairing -> receive single-display device token
    paired = client.post(
        "/api/v1/devices/pair/complete",
        json={
            "pairing_code": pair_code,
            "device_name": "Workstation-Win11",
            "platform": "windows",
            "os_version": "Windows 11 Pro",
            "capabilities": ["device_status", "authorized_folder_read"],
        },
    )
    assert paired.status_code == 201
    dev_id = paired.json()["device_id"]
    dev_token = paired.json()["device_token"]
    dev_hdr = {"X-Device-Token": dev_token}

    # Replay pairing code MUST fail
    assert (
        client.post(
            "/api/v1/devices/pair/complete",
            json={"pairing_code": pair_code, "device_name": "Rogue", "platform": "windows"},
        ).status_code
        == 401
    )

    # 3. Heartbeat authenticated by X-Device-Token
    hb = client.post(
        f"/api/v1/devices/{dev_id}/heartbeat",
        headers=dev_hdr,
        json={"telemetry": {"cpu_count": 16, "disk_free_gb": 220.5}},
    )
    assert hb.status_code == 200
    assert hb.json()["status"] == "ONLINE"

    # 4. Unpermitted sensitive action (camera) is DENIED with 403
    assert (
        client.post(
            f"/api/v1/devices/{dev_id}/tasks",
            headers=auth_headers["operator"],
            json={"action": "capture_camera", "payload": {}},
        ).status_code
        == 403
    )

    # 5. Permitted non-sensitive action (folder_list) queues PENDING -> device polls & reports COMPLETED
    dispatched = client.post(
        f"/api/v1/devices/{dev_id}/tasks",
        headers=auth_headers["operator"],
        json={"action": "folder_list", "payload": {"path": "C:/Users/Owner/ULTRON_Workspace"}},
    )
    assert dispatched.status_code == 201
    dt_id = dispatched.json()["device_task_id"]
    assert dispatched.json()["status"] == "PENDING"

    polled = client.get(f"/api/v1/devices/{dev_id}/tasks/pending", headers=dev_hdr).json()
    assert polled["total"] == 1
    assert polled["tasks"][0]["device_task_id"] == dt_id

    reported = client.post(
        f"/api/v1/devices/{dev_id}/tasks/{dt_id}/report",
        headers=dev_hdr,
        json={"status": "COMPLETED", "result": {"entries": ["notes.md"]}},
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "COMPLETED"

    # 6. Enable app_launch explicitly -> dispatch triggers ApprovalGate (WAITING_FOR_APPROVAL) -> OWNER approves -> PENDING
    assert (
        client.patch(
            f"/api/v1/devices/{dev_id}/permissions",
            headers=auth_headers["owner"],
            json={"permissions": {"app_launch": True}},
        ).status_code
        == 200
    )
    sens = client.post(
        f"/api/v1/devices/{dev_id}/tasks",
        headers=auth_headers["operator"],
        json={"action": "launch_app", "payload": {"app": "vscode"}},
    )
    assert sens.status_code == 201
    assert sens.json()["status"] == "WAITING_FOR_APPROVAL"
    apr_id = sens.json()["approval"]["approval_id"]
    dec = client.post(
        f"/api/v1/approvals/{apr_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "User confirmed launch"},
    )
    assert dec.json()["linked_resource_state"] == "PENDING"

    # 7. Revoke device session -> device token immediately fails with 401
    assert client.post(f"/api/v1/devices/{dev_id}/revoke", headers=auth_headers["owner"]).status_code == 200
    assert client.post(f"/api/v1/devices/{dev_id}/heartbeat", headers=dev_hdr, json={}).status_code == 401


def test_desktop_agent_sandbox_blocks_path_traversal(tmp_path: Path) -> None:
    agent_path = Path(__file__).resolve().parents[2] / "device_agent" / "ultron_desktop_agent.py"
    spec = importlib.util.spec_from_file_location("ultron_desktop_agent", agent_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    allowed_dir = tmp_path / "authorized"
    allowed_dir.mkdir()
    sample_file = allowed_dir / "hello.txt"
    sample_file.write_text("ULTRON Authorized Content", encoding="utf-8")

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("TOP SECRET", encoding="utf-8")

    # Allowed file read succeeds
    res = mod.execute_sandboxed_task("folder_read", {"path": str(sample_file)}, [allowed_dir])
    assert "ULTRON Authorized Content" in res["content"]

    # Path traversal outside authorized folder MUST raise PermissionError
    with pytest.raises(PermissionError):
        mod.execute_sandboxed_task("folder_read", {"path": str(allowed_dir / ".." / "secret.txt")}, [allowed_dir])
    with pytest.raises(PermissionError):
        mod.execute_sandboxed_task("launch_app", {"app": "rm -rf"}, [allowed_dir])
