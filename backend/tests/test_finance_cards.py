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

    # Reject invalid Stripe token ref
    bad_tok = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={
            "nickname": "Invalid Stripe Token",
            "issuer": "Stripe",
            "provider_key": "stripe",
            "provider_token_ref": "bad",
        },
    )
    assert bad_tok.status_code in (400, 422)


def test_finance_cards_sanitized_preview_portrait_and_invalid_image(
    client: TestClient, auth_headers: dict
) -> None:
    created = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={"nickname": "Portrait Card", "issuer": "Custom"},
    )
    assert created.status_code == 201
    cid = created.json()["card_id"]

    # Portrait card image preview (unsaved) with full redaction mode
    portrait = Image.new("RGB", (400, 640), color=(20, 60, 80))
    buf = io.BytesIO()
    portrait.save(buf, format="PNG")
    prev = client.post(
        f"/api/v1/finance/cards/{cid}/image/preview",
        headers=auth_headers["owner"],
        files={"file": ("portrait.png", buf.getvalue(), "image/png")},
        data={"redaction_mode": "full"},
    )
    assert prev.status_code == 200
    assert prev.json()["saved"] is False
    assert prev.json()["redaction_mode"] == "full"
    assert prev.json()["preview_data_url"].startswith("data:image/png;base64,")

    # Confirm image_file_id is still None before explicit confirmation
    cards = client.get("/api/v1/finance/cards", headers=auth_headers["owner"]).json()["cards"]
    target = next(c for c in cards if c["card_id"] == cid)
    assert target["image_file_id"] is None

    # Corrupt/invalid image bytes are rejected and never stored
    bad_img = client.post(
        f"/api/v1/finance/cards/{cid}/image",
        headers=auth_headers["owner"],
        files={"file": ("bad.png", b"not-an-image", "image/png")},
    )
    assert bad_img.status_code in (400, 422)


def test_migration_registry_includes_005_and_006() -> None:
    from app.db.session import MIGRATION_REGISTRY

    versions = {v for v, _ in MIGRATION_REGISTRY}
    assert "005" in versions
    assert "006" in versions


def test_verify_card_provider_authorization(client, auth_headers, monkeypatch) -> None:
    from types import SimpleNamespace

    import httpx
    from app.core.config import get_settings
    from app.db.session import get_engine
    from app.services import finance_cards_service
    from sqlalchemy.orm import sessionmaker

    created = client.post(
        "/api/v1/finance/cards",
        headers=auth_headers["owner"],
        json={
            "nickname": "Verify Test Card",
            "issuer": "Stripe",
            "network": "VISA",
            "card_type": "CORPORATE",
            "scope": "BUSINESS",
            "provider_key": "stripe",
            "provider_token_ref": "pm_test_123",
        },
    )
    assert created.status_code == 201, created.text
    card = created.json()
    cid = card["card_id"]
    assert card["connection_status"] == "AWAITING_PROVIDER_AUTH"
    assert card["last_synced_at"] is None

    # Without live provider credentials, verify-provider returns 409 and keeps AWAITING_PROVIDER_AUTH
    res_409 = client.post(
        f"/api/v1/finance/cards/{cid}/verify-provider",
        headers=auth_headers["owner"],
    )
    assert res_409.status_code == 409, res_409.text

    fetched = client.get("/api/v1/finance/cards", headers=auth_headers["owner"])
    assert fetched.status_code == 200
    items = fetched.json()["cards"]
    fetched_card = next(item for item in items if item["card_id"] == cid)
    assert fetched_card["connection_status"] == "AWAITING_PROVIDER_AUTH"
    assert fetched_card["last_synced_at"] is None

    # With a valid tenant provider token and mocked HTTP 200, status becomes PROVIDER_LINKED
    from app.services import integration_manager

    monkeypatch.setattr(
        integration_manager,
        "resolve_provider_token",
        lambda *args, **kwargs: "sk_test_mocked",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"id": "pm_test_123"}))
    with httpx.Client(transport=transport) as mock_http:
        from sqlalchemy import text

        settings = get_settings()
        db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
        try:
            tenant_id = db.execute(
                text("SELECT tenant_id FROM finance_cards WHERE card_id = :cid"),
                {"cid": cid},
            ).scalar_one()
            principal = SimpleNamespace(
                user_id="owner-user",
                username="owner",
                tenant_id=tenant_id,
                role="owner",
                email="owner@ultron.test",
            )
            verified = finance_cards_service.verify_card_provider_authorization(
                db,
                principal=principal,
                card_id=cid,
                settings=settings,
                http_client=mock_http,
            )
            assert verified["connection_status"] == "PROVIDER_LINKED"
            assert verified["last_synced_at"] is not None
        finally:
            db.close()

