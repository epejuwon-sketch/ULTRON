"""Tests for CARAVAN Phase 7: Production Infrastructure, Auth, Security Regressions, Workers & Launch Readiness."""

from __future__ import annotations

from pathlib import Path


def test_caravan_phase7_migrations_auth_security_idor_workers_and_reports(client, auth_headers):
    # 1. Migration registry & SQL files validation
    from app.db.session import MIGRATION_REGISTRY

    ids = [m[0] for m in MIGRATION_REGISTRY]
    assert "012" in ids and "013" in ids
    mig_dir = Path(__file__).resolve().parents[1] / "migrations" / "supabase"
    for _, fname in MIGRATION_REGISTRY:
        assert (mig_dir / fname).is_file(), f"Missing migration SQL: {fname}"

    # 2. Public customer registration + email verification + non-enumerating password reset
    reg_a = client.post(
        "/api/v1/auth/register",
        json={"username": "cust_a", "email": "cust_a@example.com", "password": "StrongPass123!"},
    )
    assert reg_a.status_code == 201
    assert reg_a.json()["role"] == "VIEWER"
    verif_tok = reg_a.json()["test_verification_token"]

    conf_v = client.post("/api/v1/auth/verify-email/confirm", json={"token": verif_tok})
    assert conf_v.status_code == 200
    assert conf_v.json()["status"] == "verified"

    # Non-enumerating password reset: unknown email and real email return identical status/message
    pr_unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"})
    pr_real = client.post("/api/v1/auth/password-reset/request", json={"email": "cust_a@example.com"})
    assert pr_unknown.status_code == 200 and pr_real.status_code == 200
    assert pr_unknown.json()["message"] == pr_real.json()["message"]
    assert "test_reset_token" not in pr_unknown.json()
    reset_tok = pr_real.json()["test_reset_token"]

    # Login Customer A before reset, then reset password and verify old session is revoked
    login_a = client.post("/api/v1/auth/login", json={"username": "cust_a", "password": "StrongPass123!"})
    assert login_a.status_code == 200
    old_headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    conf_r = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_tok, "new_password": "NewStrongPass456!"},
    )
    assert conf_r.status_code == 200
    assert conf_r.json()["revoked_sessions"] >= 1

    # Old token must now be rejected
    assert client.get("/api/v1/auth/me", headers=old_headers_a).status_code == 401

    # Re-login Customer A with new password and register/login Customer B in same tenant
    login_a2 = client.post("/api/v1/auth/login", json={"username": "cust_a", "password": "NewStrongPass456!"})
    assert login_a2.status_code == 200
    headers_a = {"Authorization": f"Bearer {login_a2.json()['access_token']}"}

    reg_b = client.post(
        "/api/v1/auth/register",
        json={"username": "cust_b", "email": "cust_b@example.com", "password": "StrongPass789!"},
    )
    assert reg_b.status_code == 201
    login_b = client.post("/api/v1/auth/login", json={"username": "cust_b", "password": "StrongPass789!"})
    assert login_b.status_code == 200
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # 3. Create & verify an opportunity as OWNER, plus a conflicting duplicate
    opp1 = client.post(
        "/api/v1/caravan/opportunities",
        headers=auth_headers["owner"],
        json={
            "title": "Lagos Innovation Grant",
            "provider_org": "LSETF",
            "funding_type": "GRANT",
            "source_url": "https://lsetf.ng/grant-1",
            "eligibility_requirements": "Lagos SMEs",
            "amount_display": "NGN 5,000,000",
            "currency": "NGN",
        },
    )
    assert opp1.status_code == 201
    opp1_id = opp1.json()["opportunity_id"]
    assert client.post(
        f"/api/v1/caravan/opportunities/{opp1_id}/verify",
        headers=auth_headers["owner"],
        json={"verification_status": "VERIFIED", "supporting_evidence": "Checked official portal."},
    ).status_code == 200

    # Seed a conflicting ingested opportunity directly (bypassing manual duplicate guard) to test conflict detection
    from app.core.config import get_settings
    from app.db.models import CaravanFundingOpportunityRecord
    from app.db.session import get_session_factory

    owner_tid = client.get("/api/v1/auth/me", headers=auth_headers["owner"]).json()["tenant_id"]
    db_sess = get_session_factory(get_settings())()
    try:
        db_sess.add(
            CaravanFundingOpportunityRecord(
                opportunity_id="copp_conflict_test_1",
                tenant_id=owner_tid,
                title="Lagos Innovation Grant",
                provider_org="LSETF",
                funding_type="GRANT",
                source_url="https://lsetf.ng/grant-2",
                eligibility_requirements="Lagos SMEs",
                geographic_restrictions="Nigeria",
                amount_display="NGN 10,000,000",
                currency="NGN",
                verification_status="PENDING_REVIEW",
                created_by="argon-test",
            )
        )
        db_sess.commit()
    finally:
        db_sess.close()

    conflicts = client.get("/api/v1/caravan/opportunities/conflicts", headers=auth_headers["owner"])
    assert conflicts.status_code == 200
    assert conflicts.json()["total"] >= 1

    # 4. IDOR Regression Tests: Customer B cannot modify Customer A's application or read Customer A's support ticket
    app_a = client.post(
        "/api/v1/caravan/applications",
        headers=headers_a,
        json={"opportunity_id": opp1_id, "notes": "Customer A private notes"},
    )
    assert app_a.status_code == 201
    app_a_id = app_a.json()["application_id"]

    idor_patch = client.patch(
        f"/api/v1/caravan/applications/{app_a_id}",
        headers=headers_b,
        json={"notes": "Tampered by B"},
    )
    assert idor_patch.status_code == 404

    tkt_a = client.post(
        "/api/v1/caravan/support/tickets",
        headers=headers_a,
        json={"subject": "Private billing issue", "category": "BILLING", "message": "Secret detail"},
    )
    assert tkt_a.status_code == 201
    tkts_b = client.get("/api/v1/caravan/support/tickets", headers=headers_b)
    assert tkts_b.status_code == 200
    assert all(t["ticket_id"] != tkt_a.json()["ticket_id"] for t in tkts_b.json()["tickets"])

    # 5. RBAC Regression Tests: VIEWER blocked from admin endpoints
    assert client.get("/api/v1/caravan/business-intelligence", headers=headers_a).status_code == 403
    assert client.get("/api/v1/caravan/growth/drafts", headers=headers_a).status_code == 403
    assert client.get("/api/v1/caravan/opportunities/reports", headers=headers_a).status_code == 403
    assert client.get("/api/v1/caravan/opportunities/conflicts", headers=headers_a).status_code == 403

    # 6. Customer Listing Report & Admin Resolution
    rep = client.post(
        f"/api/v1/caravan/opportunities/{opp1_id}/report",
        headers=headers_a,
        json={"reason": "INCORRECT_INFO", "details": "Amount updated on official site."},
    )
    assert rep.status_code == 201
    rep_id = rep.json()["report_id"]

    rep_list = client.get("/api/v1/caravan/opportunities/reports", headers=auth_headers["owner"])
    assert rep_list.status_code == 200
    assert any(r["report_id"] == rep_id for r in rep_list.json()["reports"])

    rep_res = client.patch(
        f"/api/v1/caravan/opportunities/reports/{rep_id}",
        headers=auth_headers["owner"],
        json={"status": "RESOLVED", "resolution_note": "Updated listing amount."},
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["status"] == "RESOLVED"

    # 7. Notification Preferences + WhatsApp Gate + Worker Poll + Monitoring Heartbeat
    wa_fail = client.put(
        "/api/v1/caravan/notifications/preferences",
        headers=headers_a,
        json={"whatsapp_enabled": True},
    )
    assert wa_fail.status_code == 422

    # Enqueue Caravan worker jobs and run poll
    assert client.post(
        "/api/v1/argon/jobs",
        headers=auth_headers["owner"],
        json={"job_type": "CARAVAN_NOTIFICATION_DISPATCH", "payload": {}},
    ).status_code in {200, 201}
    assert client.post(
        "/api/v1/argon/jobs",
        headers=auth_headers["owner"],
        json={"job_type": "CARAVAN_DEADLINE_SWEEP", "payload": {}},
    ).status_code in {200, 201}
    assert client.post(
        "/api/v1/argon/jobs",
        headers=auth_headers["owner"],
        json={"job_type": "CARAVAN_SUBSCRIPTION_LIFECYCLE", "payload": {}},
    ).status_code in {200, 201}

    poll = client.post("/api/v1/argon/jobs/process", headers=auth_headers["owner"])
    assert poll.status_code == 200
    jobs = client.get("/api/v1/argon/jobs", headers=auth_headers["owner"]).json()
    errs = [(j.get("job_type"), j.get("last_error") or j.get("error")) for j in (jobs if isinstance(jobs, list) else jobs.get("items", [])) if j.get("status") != "SUCCEEDED"]
    assert poll.json()["succeeded"] >= 3, [(j["job_type"], j["status"], j.get("last_error"), j.get("error_message"), j.get("error")) for j in jobs["jobs"]]

    mon = client.get("/api/v1/monitoring/overview", headers=auth_headers["owner"])
    assert mon.status_code == 200
    assert len(mon.json()["worker_heartbeats"]) >= 1
