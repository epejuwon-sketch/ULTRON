"""Tests for ORBIT Location, ATLAS Orders & World Intelligence, FINANCE Payment Methods & Scope, and TURBO Benchmarks."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_orbit_authorized_location_geofence_and_pause_revoke(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # Pair an iPhone PWA device with location permission granted
    pair_init = client.post(
        "/api/v1/devices/pair/init",
        headers=auth_headers["owner"],
        json={"target_platform": "ios", "requested_permissions": {"location": True, "notifications": True}},
    ).json()
    paired = client.post(
        "/api/v1/devices/pair/complete",
        json={
            "pairing_code": pair_init["pairing_code"],
            "device_name": "Founder iPhone",
            "platform": "ios",
            "os_version": "iOS 19",
        },
    ).json()
    device_id = paired["device_id"]
    device_token = paired["device_token"]

    # Create geofence alert around Victoria Island, Lagos
    alert = client.post(
        f"/api/v1/devices/{device_id}/location/alerts",
        headers=auth_headers["owner"],
        json={
            "name": "Lagos HQ",
            "center_lat": 6.4281,
            "center_lng": 3.4219,
            "radius_meters": 500,
            "trigger_on": "ENTER",
        },
    )
    assert alert.status_code == 201
    alert_id = alert.json()["alert_id"]

    # Report location inside geofence
    rep = client.post(
        f"/api/v1/devices/{device_id}/location",
        headers={"X-Device-Token": device_token},
        json={"latitude": 6.4282, "longitude": 3.4220, "accuracy_meters": 15, "city": "Lagos", "country": "Nigeria"},
    )
    assert rep.status_code == 201
    assert alert_id in rep.json()["triggered_alerts"]

    # Pause location tracking -> subsequent update must be rejected (403)
    pause = client.post(
        f"/api/v1/devices/{device_id}/location/control",
        headers=auth_headers["owner"],
        json={"action": "PAUSE"},
    )
    assert pause.status_code == 200
    assert pause.json()["location_paused"] is True

    blocked = client.post(
        f"/api/v1/devices/{device_id}/location",
        headers={"X-Device-Token": device_token},
        json={"latitude": 6.43, "longitude": 3.42},
    )
    assert blocked.status_code == 403


def test_atlas_orders_9_statuses_and_intelligence_briefing(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    created = client.post(
        "/api/v1/atlas/orders",
        headers=auth_headers["owner"],
        json={
            "vendor": "Apple Store",
            "item_summary": "USB-C Thunderbolt Dock",
            "amount_usd": 199.0,
            "currency": "USD",
            "carrier": "DHL",
            "tracking_number": "DHL-99281726",
        },
    )
    assert created.status_code == 201
    body = created.json()
    order_id = body["order"]["order_id"]
    assert body["order"]["status"] == "PLACED"
    assert body["approval"] is not None

    for st in ("PROCESSING", "SHIPPED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"):
        upd = client.patch(
            f"/api/v1/atlas/orders/{order_id}/tracking",
            headers=auth_headers["owner"],
            json={"status": st, "tracking_source": "CARRIER_WEBHOOK", "note": f"Moved to {st}"},
        )
        assert upd.status_code == 200
        assert upd.json()["status"] == st

    # Invalid status rejected
    bad = client.patch(
        f"/api/v1/atlas/orders/{order_id}/tracking",
        headers=auth_headers["owner"],
        json={"status": "TELEPORTED"},
    )
    assert bad.status_code == 422

    # Intelligence topics & briefing
    topics = client.get("/api/v1/atlas/intelligence/topics", headers=auth_headers["owner"]).json()
    assert topics["total"] >= 8

    brf = client.post(
        "/api/v1/atlas/briefings/generate",
        headers=auth_headers["owner"],
        json={"include_live_fetch": False},
    )
    assert brf.status_code == 201
    assert len(brf.json()["sections"]) >= 8


def test_finance_tokenized_payment_methods_pan_rejection_scope_and_forecast(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # Add Verve card token (masked last4 only)
    pm1 = client.post(
        "/api/v1/finance/payment-methods",
        headers=auth_headers["owner"],
        json={
            "provider": "paystack",
            "provider_token_ref": "AUTH_paystack_tok_98234",
            "brand": "VERVE",
            "last4": "4321",
            "exp_month": 11,
            "exp_year": 2028,
            "cardholder_label": "Personal Verve Card",
            "currency": "NGN",
            "scope": "PERSONAL",
            "is_preferred": True,
        },
    )
    assert pm1.status_code == 201
    assert pm1.json()["masked_number"] == "**** **** **** 4321"
    assert pm1.json()["brand"] == "VERVE"

    # Attempt to sneak a raw Luhn card PAN in provider_token_ref -> MUST reject (422)
    raw_pan_attempt = client.post(
        "/api/v1/finance/payment-methods",
        headers=auth_headers["owner"],
        json={
            "provider": "stripe",
            "provider_token_ref": "4242424242424242",
            "brand": "VISA",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2029,
            "scope": "BUSINESS",
        },
    )
    assert raw_pan_attempt.status_code == 422

    # Personal vs Business transaction separation
    client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["owner"],
        json={"entry_type": "EXPENSE", "category": "groceries", "amount_usd": 45.0, "description": "Groceries", "scope": "PERSONAL"},
    )
    client.post(
        "/api/v1/finance/transactions",
        headers=auth_headers["owner"],
        json={"entry_type": "REVENUE", "category": "saas", "amount_usd": 1200.0, "description": "Caravan Sub", "scope": "BUSINESS"},
    )

    biz_summary = client.get("/api/v1/finance/reports/summary?scope=BUSINESS", headers=auth_headers["owner"]).json()
    assert biz_summary["scope_filter"] == "BUSINESS"
    assert biz_summary["total_revenue_usd"] >= 1200.0

    forecast = client.get("/api/v1/finance/forecast?months=3", headers=auth_headers["owner"]).json()
    assert forecast["basis"] == "RECORDED_LEDGER_DATA_ONLY"
    assert len(forecast["projections"]) == 3


def test_turbo_benchmarks_and_cache(client: TestClient, auth_headers: dict[str, dict[str, str]]) -> None:
    bench = client.post("/api/v1/turbo/benchmarks?iterations=10", headers=auth_headers["owner"])
    assert bench.status_code == 200
    body = bench.json()
    assert body["measured"] is True
    assert body["benchmarks_avg_ms"]["db_select_1_ms"] >= 0
    assert body["benchmarks_avg_ms"]["vault_aes256gcm_roundtrip_ms"] >= 0

    flush = client.post("/api/v1/turbo/cache/flush", headers=auth_headers["owner"])
    assert flush.status_code == 200
