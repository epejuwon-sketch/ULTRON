"""Sandbox & security tests for UBA Verve Direct and Flutterwave Hosted Checkout integrations."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient


def test_uba_verve_lifecycle_capabilities_approvals_and_failures(
    client: TestClient,
    auth_headers: dict,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.db.session import get_engine
    from app.services import uba_verve_adapter
    from sqlalchemy.orm import sessionmaker

    # 1. Default state is UNCONFIGURED; only CARD_DISPLAY is enabled
    st = client.get("/api/v1/finance/uba-verve/status", headers=auth_headers["owner"])
    assert st.status_code == 200
    body = st.json()
    assert body["lifecycle_state"] == "UNCONFIGURED"
    assert body["capabilities"]["CARD_DISPLAY"]["enabled"] is True
    assert body["capabilities"]["CARD_PAYMENT"]["enabled"] is False
    assert body["capabilities"]["ACCOUNT_BALANCE"]["enabled"] is False
    assert body["developer_zone"]["personal_debit_card_grants_api_access"] is False

    # Balance enquiry fails when UNCONFIGURED
    bal_unconf = client.post(
        "/api/v1/finance/uba-verve/balance",
        headers=auth_headers["owner"],
        json={"account_ref": "acct_uba_001", "use_sandbox_mock": True},
    )
    assert bal_unconf.status_code == 409

    # 2. Configure fake sandbox env vars (no real secrets)
    monkeypatch.setenv("UBA_API_BASE_URL", "https://sandbox.uba.example.invalid/api")
    monkeypatch.setenv("UBA_CLIENT_ID", "sandbox-client-placeholder")
    monkeypatch.setenv("UBA_CLIENT_SECRET", "sandbox-secret-placeholder")
    monkeypatch.setenv("UBA_API_KEY", "sandbox-apikey-placeholder")
    monkeypatch.setenv("UBA_ENVIRONMENT", "sandbox")
    get_settings.cache_clear()

    # Sandbox mock auth succeeds
    auth_res = client.post(
        "/api/v1/finance/uba-verve/verify",
        headers=auth_headers["owner"],
        json={"use_sandbox_mock": True},
    )
    assert auth_res.status_code == 200
    assert auth_res.json()["lifecycle_state"] == "AUTHENTICATED"
    assert auth_res.json()["sandbox_mock"] is True

    # Sandbox balance & transactions succeed
    bal = client.post(
        "/api/v1/finance/uba-verve/balance",
        headers=auth_headers["owner"],
        json={"account_ref": "acct_uba_001", "use_sandbox_mock": True},
    )
    assert bal.status_code == 200
    assert bal.json()["currency"] == "NGN"
    assert bal.json()["sandbox_mock"] is True

    txs = client.post(
        "/api/v1/finance/uba-verve/transactions",
        headers=auth_headers["owner"],
        json={"account_ref": "acct_uba_001", "use_sandbox_mock": True},
    )
    assert txs.status_code == 200
    assert len(txs.json()["transactions"]) >= 1

    # 3. Financial action always requires explicit AEGIS approval and never auto-executes
    act = client.post(
        "/api/v1/finance/uba-verve/action",
        headers=auth_headers["owner"],
        json={
            "capability": "CARD_PAYMENT",
            "card_id": "crd_uba_test_01",
            "amount_ngn": 25000.0,
            "counterparty": "Merchant Sandbox",
        },
    )
    assert act.status_code == 200
    assert act.json()["executed"] is False
    assert act.json()["approval_required"] is True
    assert act.json()["approval"]["status"] == "PENDING"

    # 4. Adapter HTTP failure modes: rejected credentials (401), timeout, unavailable (503), and 200 live probe
    settings = get_settings()
    db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
    try:
        from sqlalchemy import text

        tid = db.execute(text("SELECT tenant_id FROM tenants LIMIT 1")).scalar_one()
        principal = SimpleNamespace(user_id="owner-1", username="owner", tenant_id=tid, role="OWNER")

        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401))) as c401:
            r401 = uba_verve_adapter.verify_uba_verve_connection(db, principal=principal, settings=settings, http_client=c401)
            assert r401["lifecycle_state"] == "UNAVAILABLE"

        def _timeout(_req):
            raise httpx.ReadTimeout("timed out")

        with httpx.Client(transport=httpx.MockTransport(_timeout)) as c_to:
            r_to = uba_verve_adapter.verify_uba_verve_connection(db, principal=principal, settings=settings, http_client=c_to)
            assert r_to["lifecycle_state"] == "UNAVAILABLE"
            assert "timed out" in r_to["detail"].lower()

        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503))) as c503:
            r503 = uba_verve_adapter.verify_uba_verve_connection(db, principal=principal, settings=settings, http_client=c503)
            assert r503["lifecycle_state"] == "UNAVAILABLE"

        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"access_token": "sbx"}))) as c200:
            r200 = uba_verve_adapter.verify_uba_verve_connection(db, principal=principal, settings=settings, http_client=c200)
            assert r200["lifecycle_state"] == "LIVE_VERIFIED"
    finally:
        db.close()

    # 5. Revoked consent blocks subsequent balance enquiries
    rev = client.post("/api/v1/finance/uba-verve/revoke", headers=auth_headers["owner"])
    assert rev.status_code == 200
    assert rev.json()["lifecycle_state"] == "REVOKED"

    after_rev = client.post(
        "/api/v1/finance/uba-verve/balance",
        headers=auth_headers["owner"],
        json={"account_ref": "acct_uba_001", "use_sandbox_mock": True},
    )
    assert after_rev.status_code == 409


def test_flutterwave_sandbox_checkout_verification_webhook_and_idempotency(
    client: TestClient,
    auth_headers: dict,
    monkeypatch,
) -> None:
    from app.core.config import get_settings
    from app.db.session import get_engine
    from app.services import flutterwave_service
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("FLW_PUBLIC_KEY", "FLWPUBK_TEST-placeholder")
    monkeypatch.setenv("FLW_SECRET_KEY", "FLWSECK_TEST-placeholder")
    monkeypatch.setenv("FLW_ENCRYPTION_KEY", "FLWSECK_TEST-enc-placeholder")
    monkeypatch.setenv("FLW_SECRET_HASH", "ultron-flw-test-webhook-hash")
    monkeypatch.setenv("FLW_ENVIRONMENT", "test")
    get_settings.cache_clear()

    # 1. Status reflects test environment and NGN/Verve support with live payments disabled
    st = client.get("/api/v1/finance/flutterwave/status", headers=auth_headers["owner"])
    assert st.status_code == 200
    assert st.json()["environment"] == "test"
    assert st.json()["live_payments_enabled"] is False
    assert st.json()["verve_supported"] is True

    # 2. Initiate NGN Hosted Checkout with idempotency_key
    c1 = client.post(
        "/api/v1/finance/flutterwave/checkout",
        headers=auth_headers["owner"],
        json={
            "amount": 15000.0,
            "currency": "NGN",
            "customer_email": "customer@ultron.test",
            "customer_name": "Ada Lovelace",
            "idempotency_key": "idem_flw_001",
            "use_sandbox_mock": True,
        },
    )
    assert c1.status_code == 201, c1.text
    p1 = c1.json()
    assert p1["status"] == "INITIATED"
    assert p1["currency"] == "NGN"
    assert p1["idempotent_replay"] is False
    tx_ref = p1["tx_ref"]

    # Idempotent replay returns same payment without duplicating
    c2 = client.post(
        "/api/v1/finance/flutterwave/checkout",
        headers=auth_headers["owner"],
        json={
            "amount": 15000.0,
            "currency": "NGN",
            "customer_email": "customer@ultron.test",
            "idempotency_key": "idem_flw_001",
            "use_sandbox_mock": True,
        },
    )
    assert c2.status_code == 201
    assert c2.json()["tx_ref"] == tx_ref
    assert c2.json()["idempotent_replay"] is True

    # 3. Amount/currency mismatch is rejected by server-side verification
    settings = get_settings()
    db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
    try:
        from types import SimpleNamespace

        from sqlalchemy import text

        tid = db.execute(text("SELECT tenant_id FROM tenants LIMIT 1")).scalar_one()
        principal = SimpleNamespace(user_id="owner-1", username="owner", tenant_id=tid, role="OWNER")

        mismatch = flutterwave_service.verify_flutterwave_transaction(
            db,
            principal=principal,
            tx_ref=tx_ref,
            transaction_id="99001",
            settings=settings,
            mock_verify_payload={"id": 99001, "tx_ref": tx_ref, "status": "successful", "currency": "NGN", "amount": 500.0},
        )
        assert mismatch["status"] == "AMOUNT_OR_CURRENCY_MISMATCH"
    finally:
        db.close()

    # 4. Webhook rejects missing/invalid verif-hash (401)
    bad_wh = client.post(
        "/api/v1/finance/flutterwave/webhook",
        headers={"verif-hash": "wrong-hash"},
        json={"event": "charge.completed", "data": {"id": 99002, "tx_ref": tx_ref}},
    )
    assert bad_wh.status_code == 401

    # 5. Valid verif-hash triggers server-side /transactions/{id}/verify and marks SUCCESSFUL
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"id": 99002, "tx_ref": tx_ref, "status": "successful", "currency": "NGN", "amount": 15000.0},
            },
        )
    )
    with httpx.Client(transport=transport) as mock_http:
        db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
        try:
            verified = flutterwave_service.handle_flutterwave_webhook(
                db,
                verif_hash="ultron-flw-test-webhook-hash",
                payload={"event": "charge.completed", "data": {"id": 99002, "tx_ref": tx_ref}},
                settings=settings,
                http_client=mock_http,
            )
            assert verified["status"] == "SUCCESSFUL"
        finally:
            db.close()

    # 6. Cancelled callback marks a new checkout as CANCELLED
    c3 = client.post(
        "/api/v1/finance/flutterwave/checkout",
        headers=auth_headers["owner"],
        json={
            "amount": 5000.0,
            "currency": "NGN",
            "customer_email": "customer@ultron.test",
            "idempotency_key": "idem_flw_002",
            "use_sandbox_mock": True,
        },
    )
    assert c3.status_code == 201
    tx_ref_2 = c3.json()["tx_ref"]
    cb = client.get(
        f"/api/v1/finance/flutterwave/callback?tx_ref={tx_ref_2}&status=cancelled",
        headers=auth_headers["owner"],
    )
    assert cb.status_code == 200
    assert cb.json()["status"] == "CANCELLED"

    # 7. Live environment is blocked in ULTRON sandbox mode
    monkeypatch.setenv("FLW_ENVIRONMENT", "live")
    get_settings.cache_clear()
    live_blocked = client.post(
        "/api/v1/finance/flutterwave/checkout",
        headers=auth_headers["owner"],
        json={
            "amount": 5000.0,
            "currency": "NGN",
            "customer_email": "customer@ultron.test",
            "use_sandbox_mock": True,
        },
    )
    assert live_blocked.status_code == 409
