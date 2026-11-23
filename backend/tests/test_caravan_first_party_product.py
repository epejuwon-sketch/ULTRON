"""Tests for Caravan First-Party Product Module: discovery, verification, NEON eligibility, applications, subscriptions, and tenant isolation."""

from __future__ import annotations


def test_caravan_first_party_product_lifecycle_and_governance(client, auth_headers):
    # 1. Existing bridge & overview work
    ov = client.get("/api/v1/caravan/overview", headers=auth_headers["owner"])
    assert ov.status_code == 200, ov.text
    assert ov.json()["product"] == "CARAVAN"
    assert ov.json()["governance"]["live_payments_enabled"] is False
    assert ov.json()["governance"]["zero_fabricated_opportunities"] is True

    # 2. SSRF-blocked source URL rejected
    ssrf_opp = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "title": "Internal Metadata Trap",
            "provider_org": "Bad Org",
            "funding_type": "GRANT",
            "source_url": "http://169.254.169.254/latest/meta-data",
            "eligibility_requirements": "None",
        },
    )
    assert ssrf_opp.status_code in (400, 403, 422)

    # 3. VIEWER cannot create opportunities (RBAC)
    viewer_create = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["viewer"],
        json={
            "title": "Viewer Attempt",
            "provider_org": "Test Foundation",
            "funding_type": "GRANT",
            "source_url": "https://example.org/grants/1",
            "eligibility_requirements": "Registered startups in Nigeria",
        },
    )
    assert viewer_create.status_code == 403

    # 4. Register funding source & real opportunity (starts UNVERIFIED)
    src = client.post(
        "/api/v1/caravan/sources",
        headers=auth_headers["owner"],
        json={
            "name": "Tony Elumelu Foundation Portal",
            "source_type": "PUBLIC_PORTAL",
            "base_url": "https://www.tonyelumelufoundation.org",
        },
    )
    assert src.status_code == 201, src.text
    source_id = src.json()["source_id"]

    opp = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "source_id": source_id,
            "title": "TEF Entrepreneurship Programme",
            "provider_org": "Tony Elumelu Foundation",
            "funding_type": "GRANT",
            "source_url": "https://www.tonyelumelufoundation.org/programme",
            "eligibility_requirements": "Early-stage African startup in Technology or Agriculture",
            "geographic_restrictions": "Africa / Nigeria",
            "amount_display": "$5,000 non-refundable seed capital",
            "currency": "USD",
        },
    )
    assert opp.status_code == 201, opp.text
    opp_data = opp.json()
    assert opp_data["verification_status"] == "UNVERIFIED"
    opp_id = opp_data["opportunity_id"]

    # 5. Verification requires supporting_evidence
    bad_verify = client.post(
        f"/api/v1/caravan/opportunities/{opp_id}/verify",
        headers=auth_headers["owner"],
        json={"verification_status": "VERIFIED", "supporting_evidence": ""},
    )
    assert bad_verify.status_code in (400, 422)

    good_verify = client.post(
        f"/api/v1/caravan/opportunities/{opp_id}/verify",
        headers=auth_headers["owner"],
        json={
            "verification_status": "VERIFIED",
            "supporting_evidence": "Confirmed official 2026 programme guidelines at source_url.",
        },
    )
    assert good_verify.status_code == 200
    assert good_verify.json()["verification_status"] == "VERIFIED"
    assert good_verify.json()["last_verified_at"] is not None

    # 6. Customer onboarding + NEON eligibility assessment + recommendations
    acct = client.put(
        "/api/v1/caravan/account",
        headers=auth_headers["owner"],
        json={
            "organization_name": "Kora Labs Ltd",
            "entity_type": "STARTUP",
            "country": "Nigeria",
            "sector": "Technology",
            "stage": "SEED",
            "onboarding_completed": True,
        },
    )
    assert acct.status_code == 200
    assert acct.json()["onboarding_completed"] is True

    assess = client.post(
        "/api/v1/caravan/assessments",
        headers=auth_headers["owner"],
        json={"opportunity_id": opp_id},
    )
    assert assess.status_code == 201
    assert assess.json()["verdict"] == "ELIGIBLE"
    assert assess.json()["score"] >= 75

    recs = client.get("/api/v1/caravan/recommendations", headers=auth_headers["owner"])
    assert recs.status_code == 200
    assert any(r["opportunity_id"] == opp_id for r in recs.json()["recommendations"])

    # 7. Save opportunity, create application, and verify AEGIS approval gate on submission
    saved = client.post(
        "/api/v1/caravan/saved",
        headers=auth_headers["owner"],
        json={"opportunity_id": opp_id, "notes": "Top priority Q1"},
    )
    assert saved.status_code == 201

    app_create = client.post(
        "/api/v1/caravan/applications",
        headers=auth_headers["owner"],
        json={"opportunity_id": opp_id, "notes": "Drafting pitch"},
    )
    assert app_create.status_code == 201
    app_id = app_create.json()["application_id"]

    submit_req = client.patch(
        f"/api/v1/caravan/applications/{app_id}",
        headers=auth_headers["owner"],
        json={"status": "SUBMITTED", "progress_pct": 100},
    )
    assert submit_req.status_code == 200
    assert submit_req.json()["status"] in {"AWAITING_APPROVAL", "SUBMITTED"}

    # 8. Subscription entitlements: live payments strictly blocked
    live_pay_attempt = client.put(
        "/api/v1/caravan/subscription",
        headers=auth_headers["owner"],
        json={"plan_tier": "PRO", "enable_live_payments": True},
    )
    assert live_pay_attempt.status_code in (400, 403)

    sub_ok = client.put(
        "/api/v1/caravan/subscription",
        headers=auth_headers["owner"],
        json={"plan_tier": "PRO", "enable_live_payments": False},
    )
    assert sub_ok.status_code == 200
    assert sub_ok.json()["plan_tier"] == "PRO"
    assert sub_ok.json()["live_payments_enabled"] is False

    # 9. Support tickets & notifications
    tkt = client.post(
        "/api/v1/caravan/support/tickets",
        headers=auth_headers["owner"],
        json={"subject": "Need review of pitch deck", "message": "Please check eligibility notes."},
    )
    assert tkt.status_code == 201

    notifs = client.get("/api/v1/caravan/notifications", headers=auth_headers["owner"])
    assert notifs.status_code == 200
    assert notifs.json()["total"] >= 1


def test_caravan_tenant_isolation(client, auth_headers):
    # Create an opportunity in default tenant
    opp = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "title": "Tenant A Confidential Grant",
            "provider_org": "Tenant A Org",
            "funding_type": "GRANT",
            "source_url": "https://example.org/tenant-a-grant",
            "eligibility_requirements": "Tenant A only",
        },
    )
    assert opp.status_code == 201
    opp_id = opp.json()["opportunity_id"]

    # Register a separate tenant & owner
    boot2 = client.post(
        "/api/v1/auth/bootstrap-owner",
        json={"tenant_id": "tenant-b", "username": "owner_b", "password": "OwnerBPassword123!"},
    )
    if boot2.status_code not in (200, 201):
        # In single-tenant bootstrap mode, verify tenant_id isolation at service layer directly
        from app.core.config import get_settings
        from app.core.exceptions import NotFoundError
        from app.db.session import get_engine
        from app.services.caravan_product_service import get_funding_opportunity, list_funding_opportunities
        from sqlalchemy.orm import sessionmaker

        settings = get_settings()
        db = sessionmaker(bind=get_engine(settings), autocommit=False, autoflush=False, expire_on_commit=False)()
        try:
            assert list_funding_opportunities(db, tenant_id="other-tenant") == []
            try:
                get_funding_opportunity(db, tenant_id="other-tenant", opportunity_id=opp_id)
                assert False, "Cross-tenant opportunity read should fail"
            except NotFoundError:
                pass
        finally:
            db.close()
        return

    login2 = client.post(
        "/api/v1/auth/login",
        json={"tenant_id": "tenant-b", "username": "owner_b", "password": "OwnerBPassword123!"},
    )
    headers_b = {"Authorization": f"Bearer {login2.json()['access_token']}"}
    assert client.get(f"/api/v1/caravan/opportunities/{opp_id}", headers=headers_b).status_code == 404


def test_caravan_argon_source_verification_probe(client, auth_headers, monkeypatch):
    import httpx

    src = client.post(
        "/api/v1/caravan/sources",
        headers=auth_headers["owner"],
        json={
            "name": "Nigeria Startup Portal",
            "source_type": "PUBLIC_PORTAL",
            "base_url": "https://startupbill.ng/",
        },
    )
    assert src.status_code == 201, src.text
    src_id = src.json()["source_id"]

    class _FakeResp:
        status_code = 200

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            return _FakeResp()

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    probe = client.post(f"/api/v1/caravan/sources/{src_id}/verify", headers=auth_headers["owner"])
    assert probe.status_code == 200, probe.text
    body = probe.json()
    assert body["reachable"] is True
    assert body["http_status"] == 200
    assert body["status"] == "ACTIVE"
    assert body["argon_workflow"] == "SSRF_GUARDED_SOURCE_PROBE"

