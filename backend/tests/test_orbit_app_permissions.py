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
    assert "Allow ULTRON to open Spotify" in first.json()["prompt"]

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


def test_orbit_device_wide_permission_and_universal_apps(client: TestClient, auth_headers: dict) -> None:
    # Approve device-wide ORBIT_APPLICATION_LAUNCH on iphone_xr_pwa
    dp = client.post(
        "/api/v1/devices/apps/device-permission",
        headers=auth_headers["owner"],
        json={
            "device_id": "iphone_xr_pwa",
            "device_label": "iPhone XR PWA",
            "decision": "ALWAYS_ALLOW",
        },
    )
    assert dp.status_code == 200
    assert dp.json()["permission_scope"] == "ORBIT_APPLICATION_LAUNCH"
    assert dp.json()["status"] == "ALWAYS_ALLOW"

    # Launch multiple distinct apps without repeated ULTRON approval
    for query, expected_id, expect_url in [
        ("YouTube", "youtube", True),
        ("Instagram", "instagram", True),
        ("TikTok", "tiktok", True),
        ("my browser", "browser", True),
        ("my gallery", "gallery", True),
        ("my banking application", "banking", False),
        ("my camera", "camera", False),
        ("Notion", "notion", False),
    ]:
        res = client.post(
            "/api/v1/devices/apps/launch",
            headers=auth_headers["owner"],
            json={"app_id": query, "device_id": "iphone_xr_pwa", "platform": "ios"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "READY_TO_LAUNCH"
        assert body["app_id"] == expected_id
        assert body["permission_mode"] == "ORBIT_APPLICATION_LAUNCH"
        assert body["app_recognised"] is True
        assert body["launch_url_resolved"] is expect_url
        assert body["os_confirmed"] is False

    # Different device still requires approval
    other_dev = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={"app_id": "YouTube", "device_id": "android_pixel_8", "platform": "android"},
    )
    assert other_dev.status_code == 200
    assert other_dev.json()["status"] == "APPROVAL_REQUIRED"

    # Revoke device-wide permission restores APPROVAL_REQUIRED
    rev = client.post(
        "/api/v1/devices/apps/device-permission",
        headers=auth_headers["owner"],
        json={"device_id": "iphone_xr_pwa", "device_label": "iPhone XR PWA", "decision": "REVOKED"},
    )
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    after_rev = client.post(
        "/api/v1/devices/apps/launch",
        headers=auth_headers["owner"],
        json={"app_id": "YouTube", "device_id": "iphone_xr_pwa", "platform": "ios"},
    )
    assert after_rev.status_code == 200
    assert after_rev.json()["status"] == "APPROVAL_REQUIRED"


def test_orbit_custom_app_registration_security_and_library(client: TestClient, auth_headers: dict) -> None:
    # Reject unsafe URI schemes and shell metacharacters
    for bad_scheme in ["javascript:alert(1)", "file:///etc/passwd", "spotify://;rm -rf /"]:
        bad = client.post(
            "/api/v1/devices/apps/register",
            headers=auth_headers["owner"],
            json={"name": "BadApp", "ios_scheme": bad_scheme},
        )
        assert bad.status_code == 422

    # Register custom banking app
    reg = client.post(
        "/api/v1/devices/apps/register",
        headers=auth_headers["owner"],
        json={
            "name": "Monzo",
            "aliases": ["my bank", "monzo bank"],
            "category": "Finance",
            "ios_scheme": "monzo://",
            "universal_link": "https://monzo.com",
            "android_package": "co.uk.getmondo",
            "web_fallback": "https://web.monzo.com",
        },
    )
    assert reg.status_code == 200
    assert reg.json()["app_id"] == "monzo"

    # Resolve by alias
    resolved = client.post(
        "/api/v1/devices/apps/resolve",
        headers=auth_headers["owner"],
        json={"query": "my bank", "platform": "ios"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["app_id"] == "monzo"
    assert resolved.json()["launch_url"] == "monzo://"
    assert resolved.json()["is_registered"] is True

    # Library & discovery endpoints
    lib = client.get("/api/v1/devices/apps/library?device_id=iphone_xr_pwa", headers=auth_headers["owner"])
    assert lib.status_code == 200
    assert lib.json()["total"] >= 20
    assert any(a["app_id"] == "monzo" for a in lib.json()["apps"])

    disc = client.get("/api/v1/devices/apps/discovery?platform=ios&device_id=iphone_xr_pwa", headers=auth_headers["owner"])
    assert disc.status_code == 200
    assert disc.json()["capabilities"]["ios"]["automatic_app_enumeration"] is False

    # Delete custom app
    deleted = client.delete("/api/v1/devices/apps/register/monzo", headers=auth_headers["owner"])
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "DELETED"
