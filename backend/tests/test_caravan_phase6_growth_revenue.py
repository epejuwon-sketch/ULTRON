"""Tests for Caravan Phase 6 Growth, Revenue, Safe Payment Webhooks, CRM, NEON BI, ARGON Drafts, and Privacy."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_caravan_phase6_pricing_webhooks_bi_crm_growth_and_privacy(
    client: TestClient, auth_headers: dict
) -> None:
    # 1. Public pricing catalog
    prc = client.get("/api/v1/caravan/pricing")
    assert prc.status_code == 200
    assert prc.json()["live_payments_enabled"] is False
    assert len(prc.json()["plans"]) == 3

    # 2. Ensure account exists & upgrade subscription to PRO (sandbox)
    ov = client.get("/api/v1/caravan/overview", headers=auth_headers["owner"]).json()
    acc_id = ov["account"]["account_id"]
    sub = client.put(
        "/api/v1/caravan/subscription",
        headers=auth_headers["owner"],
        json={"plan_tier": "PRO", "enable_live_payments": False},
    )
    assert sub.status_code == 200

    # 3. Payment webhook: invalid signature rejected; live mode rejected; valid HMAC accepted & idempotent
    payload = {
        "account_id": acc_id,
        "provider": "sandbox",
        "provider_ref": "ref_phase6_001",
        "event_type": "CHARGE_SUCCEEDED",
        "amount": 19.0,
        "currency": "USD",
        "status": "SUCCEEDED",
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    secret = get_settings().vault_master_key.get_secret_value()
    good_sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    bad_sig_res = client.post(
        "/api/v1/caravan/payments/webhook",
        headers=auth_headers["owner"],
        json={**payload, "signature": "invalid-signature-000", "sandbox_mode": True},
    )
    assert bad_sig_res.status_code in {400, 403}

    live_try = client.post(
        "/api/v1/caravan/payments/webhook",
        headers=auth_headers["owner"],
        json={**payload, "signature": good_sig, "sandbox_mode": False},
    )
    assert live_try.status_code in {400, 403}

    ok1 = client.post(
        "/api/v1/caravan/payments/webhook",
        headers=auth_headers["owner"],
        json={**payload, "signature": good_sig, "sandbox_mode": True},
    )
    assert ok1.status_code == 200, ok1.text
    assert ok1.json()["idempotent_duplicate"] is False
    assert ok1.json()["signature_verified"] is True

    # Duplicate webhook replay is idempotent
    ok2 = client.post(
        "/api/v1/caravan/payments/webhook",
        headers=auth_headers["owner"],
        json={**payload, "signature": good_sig, "sandbox_mode": True},
    )
    assert ok2.status_code == 200
    assert ok2.json()["idempotent_duplicate"] is True

    # 4. Operating expense & Business Intelligence accuracy
    exp = client.post(
        "/api/v1/caravan/expenses",
        headers=auth_headers["owner"],
        json={"category": "HOSTING", "description": "Vercel & DB dev", "amount": 5.0, "currency": "USD"},
    )
    assert exp.status_code == 201

    bi = client.get("/api/v1/caravan/business-intelligence?period=monthly", headers=auth_headers["owner"])
    assert bi.status_code == 200, bi.text
    bbody = bi.json()
    assert bbody["business_command_centre"]["actual_collected_by_currency"]["USD"] == 19.0
    assert bbody["financial_intelligence"]["net_collected_usd"] == 19.0
    assert bbody["financial_intelligence"]["estimated_operating_margin_usd"] == 14.0
    assert "observed_facts" in bbody["neon_business_intelligence"]

    # 5. CRM RBAC: VIEWER gets 403, OWNER can list & add notes
    assert client.get("/api/v1/caravan/crm/customers", headers=auth_headers["viewer"]).status_code == 403
    crm = client.get("/api/v1/caravan/crm/customers", headers=auth_headers["owner"])
    assert crm.status_code == 200
    note = client.post(
        f"/api/v1/caravan/crm/customers/{acc_id}/notes",
        headers=auth_headers["owner"],
        json={"note": "Followed up on onboarding", "segment_tag": "NIGERIA_STARTUP"},
    )
    assert note.status_code == 201

    # 6. ARGON Growth Draft + AEGIS approval gate
    draft = client.post(
        "/api/v1/caravan/growth/drafts",
        headers=auth_headers["owner"],
        json={"draft_type": "CAMPAIGN", "title": "Lagos Founders Newsletter", "content": "Verified BOI & TEF updates."},
    )
    assert draft.status_code == 201
    draft_id = draft.json()["draft_id"]
    appr = client.post(f"/api/v1/caravan/growth/drafts/{draft_id}/request-approval", headers=auth_headers["owner"])
    assert appr.status_code == 200
    assert appr.json()["status"] in {"AWAITING_APPROVAL", "APPROVED"}

    # 7. Privacy consent & account deletion request
    prv = client.put(
        "/api/v1/caravan/privacy",
        headers=auth_headers["owner"],
        json={"analytics_consent": True, "marketing_consent": False, "deletion_requested": True, "deletion_reason": "Test"},
    )
    assert prv.status_code == 200
    assert prv.json()["analytics_consent"] is True
    assert prv.json()["deletion_requested"] is True
