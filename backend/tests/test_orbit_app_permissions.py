"""Tests for ORBIT persistent per-user, per-device, per-application launch permissions."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_orbit_app_launch_one_time_approval_and_scoping(client: TestClient, auth_headers: dict) -> None:
    # 1. First Spotify request requires approval
    first = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={
            "app_id": "spotify",
            "device_id": "iphone_xr_pwa",
            "device_label": "iPhone XR PWA",
            "platform": "ios",
            "target_uri": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "APPROVAL_REQUIRED"
    assert first.json()["prompt"] == "Allow ULTRON to open Spotify on this device whenever you request it?"

    # 2. Allow once works without persisting ALWAYS_ALLOW
    once = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={
            "app_id": "spotify",
            "device_id": "iphone_xr_pwa",
            "platform": "ios",
            "target_uri": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            "allow_once": True,
        },
    )
    assert once.status_code == 200
    assert once.json()["status"] == "READY_TO_LAUNCH"
    assert once.json()["permission_mode"] == "ALLOW_ONCE"
    assert once.json()["launch_url"] == "spotify://playlist/37i9dQZF1DXcBWIGoYBM5M"
    assert once.json()["web_fallback_url"] == "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

    # 3. Grant ALWAYS_ALLOW for Spotify on iphone_xr_pwa
    saved = client.post(
        "/api/v1/devices/apps/permissions",
        headers=auth_headers["owner"],
        json={
            "app_id": "spotify",
            "device_id": "iphone_xr_pwa",
            "device_label": "iPhone XR PWA",
            "decision": "ALWAYS_ALLOW",
        },
    )
    assert saved.status_code == 200
    perm_id = saved.json()["permission_id"]
    assert saved.json()["status"] == "ALWAYS_ALLOW"

    # 4. Subsequent Spotify request on iphone_xr_pwa skips prompt
    auto = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={
            "app_id": "spotify",
            "device_id": "iphone_xr_pwa",
            "platform": "ios",
            "target_uri": "spotify:track:4cOdK2wGLETKBW3PvgPWqT",
        },
    )
    assert auto.status_code == 200
    assert auto.json()["status"] == "READY_TO_LAUNCH"
    assert auto.json()["permission_mode"] == "ALWAYS_ALLOW"
    assert auto.json()["launch_url"] == "spotify://track/4cOdK2wGLETKBW3PvgPWqT"

    # 5. Scoped strictly to app & device: WhatsApp or another device still requires approval
    other_app = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={"app_id": "whatsapp", "device_id": "iphone_xr_pwa", "platform": "ios"},
    )
    assert other_app.status_code == 200
    assert other_app.json()["status"] == "APPROVAL_REQUIRED"

    other_device = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={"app_id": "spotify", "device_id": "windows_desktop_01", "platform": "windows"},
    )
    assert other_device.status_code == 200
    assert other_device.json()["status"] == "APPROVAL_REQUIRED"

    # 6. Revoke permission restores APPROVAL_REQUIRED
    rev = client.post(f"/api/v1/devices/apps/permissions/{perm_id}/revoke", headers=auth_headers["owner"])
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    after_revoke = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={"app_id": "spotify", "device_id": "iphone_xr_pwa", "platform": "ios"},
    )
    assert after_revoke.status_code == 200
    assert after_revoke.json()["status"] == "APPROVAL_REQUIRED"
