"""Tests for ULTRON Finance Centre Premium Cards: CRUD, Pillow image sanitization, PCI guard, and RBAC."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image


def _make_sample_card_png() -> bytes:
    img = Image.new("RGB", (600, 380), color=(16, 85, 65))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_finance_cards_multiple_edit_image_upload_and_unlink(client: TestClient, auth_headers: dict) -> None:
    # Create first display card
    c1 = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={
            "nickname": "ULTRON Emerald",
            "issuer": "Paystack",
            "network": "VERVE",
            "card_type": "VIRTUAL",
            "scope": "BUSINESS",
            "is_preferred": True,
        },
    )
    assert c1.status_code == 201
    c1_data = c1.json()
    assert c1_data["connection_status"] == "DISPLAY_ONLY"
    assert c1_data["is_preferred"] is True

    # Create second card with tokenized provider ref (honestly AWAITING_PROVIDER_AUTH when provider not live)
    c2 = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={
            "nickname": "Treasury Reserve",
            "issuer": "Stripe",
            "network": "VISA",
            "card_type": "CORPORATE",
            "scope": "BUSINESS",
            "provider_key": "stripe",
            "provider_token_ref": "pm_test_safe_token_ref",
        },
    )
    assert c2.status_code == 201
    c2_data = c2.json()
    assert c2_data["connection_status"] == "AWAITING_PROVIDER_AUTH"
    assert c2_data["has_provider_token"] is True
    assert "pm_test_safe_token_ref" not in str(c2_data)

    # Upload and sanitize card photograph
    up = client.post(
        f"/api/v1/finance/cards/{c1_data['card_id']}/image",
        headers=auth_headers["owner"],
        files={"file": ("card.png", _make_sample_card_png(), "image/png")},
    )
    assert up.status_code == 200
    up_data = up.json()
    assert up_data["background_style"] == "custom-image"
    assert up_data["image_file_id"] is not None

    # Preview image is accessible via authenticated File Hub preview
    prev = client.get(up_data["image_preview_url"], headers=auth_headers["owner"])
    assert prev.status_code == 200
    assert prev.headers.get("content-type") == "image/png"

    # Edit second card and set as preferred
    patched = client.patch(
        f"/api/v1/finance/cards/{c2_data['card_id']}",
        headers=auth_headers["owner"],
        json={"nickname": "Treasury Primary", "is_preferred": True, "visual_effect": "metallic"},
    )
    assert patched.status_code == 200
    assert patched.json()["nickname"] == "Treasury Primary"
    assert patched.json()["is_preferred"] is True

    # List confirms multiple cards
    listed = client.get("/api/v1/finance/cards", headers=auth_headers["owner"])
    assert listed.status_code == 200
    assert listed.json()["total"] >= 2

    # Unlink first card
    deleted = client.delete(f"/api/v1/finance/cards/{c1_data['card_id']}", headers=auth_headers["owner"])
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "REMOVED"


def test_finance_cards_rejects_raw_pan_and_enforces_rbac(client: TestClient, auth_headers: dict) -> None:
    bad_pan = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={"nickname": "4111 2222 3333 4444", "issuer": "Test"},
    )
    assert bad_pan.status_code in (400, 422)

    viewer_res = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["viewer"],
        json={"nickname": "Viewer Card", "issuer": "Test"},
    )
    assert viewer_res.status_code == 403
