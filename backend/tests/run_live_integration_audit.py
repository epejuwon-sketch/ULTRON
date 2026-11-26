"""ULTRON x CARAVAN 10-Step Live End-to-End Synthetic Integration Acceptance Test."""

import sys
import json
import httpx
from fastapi.testclient import TestClient

from app.main import app as ultron_app
from app.core.config import get_settings

def run_acceptance_audit():
    print("=" * 80)
    print("STARTING ULTRON x CARAVAN 10-STEP LIVE INTEGRATION ACCEPTANCE AUDIT")
    print("=" * 80)

    client = TestClient(ultron_app)

    # 0. Bootstrap OWNER and create VIEWER account to obtain valid sessions
    bootstrap_res = client.post(
        "/api/v1/auth/bootstrap-owner",
        json={
            "username": "audit_owner_2026",
            "email": "audit_owner@ultron.local",
            "password": "StrongAuditPassword!2026",
            "tenant_id": "TENANT-ULTRON-AUDIT",
            "organization_name": "ULTRON Audit HQ",
        },
    )
    if bootstrap_res.status_code != 201:
        # If already bootstrapped, login directly
        pass

    owner_login = client.post(
        "/api/v1/auth/login",
        json={"username": "audit_owner_2026", "password": "StrongAuditPassword!2026"},
    )
    assert owner_login.status_code == 200, f"Owner login failed: {owner_login.text}"
    owner_token = owner_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Provision viewer
    client.post(
        "/api/v1/auth/users",
        headers=owner_headers,
        json={
            "username": "audit_viewer_2026",
            "email": "audit_viewer@ultron.local",
            "password": "StrongViewerPassword!2026",
            "role": "VIEWER",
        },
    )
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "audit_viewer_2026", "password": "StrongViewerPassword!2026"},
    )
    assert viewer_login.status_code == 200, f"Viewer login failed: {viewer_login.text}"
    viewer_token = viewer_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Step 1: ULTRON establishes an authenticated CARAVAN connection
    print("\n--- STEP 1: ULTRON Establishes Authenticated CARAVAN Connection ---")
    res1 = client.post("/api/v1/integrations/caravan/verify", headers=owner_headers)
    print(f"Status Code: {res1.status_code}")
    data1 = res1.json()
    print(f"Verified: {data1.get('live_verified')}")
    print(f"Capability State: {data1.get('capability_state')}")
    print(f"Detail: {data1.get('detail')}")
    print(f"Latency: {data1.get('latency_ms')}ms")
    assert res1.status_code == 200
    assert data1.get("live_verified") is True

    # Step 2: ULTRON retrieves CARAVAN's live health
    print("\n--- STEP 2: ULTRON Retrieves CARAVAN Live Health ---")
    res2 = client.get("/api/v1/caravan/live-status", headers=owner_headers)
    print(f"Status Code: {res2.status_code}")
    data2 = res2.json()
    print(f"Deployed URL: {data2.get('deployed_url')}")
    print(f"Deployment Status: {data2.get('deployment_status')}")
    print(f"Backend Health: {data2.get('backend_health')}")
    print(f"Database Status: {data2.get('database_status')}")
    print(f"Latency: {data2.get('health_latency_ms')}ms")
    assert res2.status_code == 200
    assert data2.get("deployment_status") == "READY"
    assert data2.get("backend_health") == "VERIFIED_LIVE"

    # Step 3: ULTRON retrieves funding opportunity statistics
    print("\n--- STEP 3: ULTRON Retrieves Funding Opportunity Statistics ---")
    res3 = client.get("/api/v1/caravan/command-centre?days=30", headers=owner_headers)
    print(f"Status Code: {res3.status_code}")
    data3 = res3.json()
    exec_ov = data3.get("executive_overview", {})
    standalone = data3.get("standalone_platform", {})
    print(f"Executive Overview Sources Total: {exec_ov.get('sources_total')}")
    print(f"Executive Overview Opportunities Total: {exec_ov.get('opportunities_total')}")
    print(f"Standalone Platform Deployed URL: {standalone.get('deployed_url')}")
    print(f"Standalone Deployment Status: {standalone.get('deployment_status')}")
    assert res3.status_code == 200

    # Step 4: ULTRON requests a discovery operation
    print("\n--- STEP 4: ULTRON Requests a Discovery Operation ---")
    res4 = client.post("/api/v1/caravan/remote/discovery", headers=owner_headers)
    print(f"Status Code: {res4.status_code}")
    data4 = res4.json()
    print(f"Job Status: {data4.get('status')}")
    print(f"Job Type: {data4.get('job')}")
    assert res4.status_code == 200

    # Step 5 & 6: CARAVAN executes authorized operation & ULTRON receives actual result
    print("\n--- STEP 5 & 6: CARAVAN Executes Authorized Discovery & Returns Real Result ---")
    summary4 = data4.get("summary", {})
    print(f"Cycle ID: {summary4.get('cycle_id')}")
    print(f"Monitored Sources: {summary4.get('sources_monitored_count')}")
    print(f"Candidates Evaluated: {summary4.get('total_candidates')}")
    print(f"Duplicates Skipped: {summary4.get('duplicate_skipped_count')}")
    assert data4.get("status") == "COMPLETED"
    assert summary4.get("sources_monitored_count") == 27

    # Step 7 & 8: ULTRON requests lifecycle monitoring & receives monitoring results
    print("\n--- STEP 7 & 8: ULTRON Requests Lifecycle Monitoring & Receives Results ---")
    with httpx.Client(timeout=10.0) as http_client:
        cron_res = http_client.post("https://caravan-juwon2.vercel.app/api/v1/cron/monitoring")
    print(f"Monitoring Status Code: {cron_res.status_code}")
    cron_data = cron_res.json()
    print(f"Monitoring Result: {json.dumps(cron_data, indent=2)}")
    assert cron_res.status_code == 200
    assert cron_data.get("status") == "COMPLETED"
    assert cron_data.get("job") == "CONTINUOUS_LIFECYCLE_MONITORING"

    # Step 9: Restricted operations are rejected or require approval
    print("\n--- STEP 9: Restricted Operations Are Rejected or Require Approval ---")
    # 9a. Unauthorized VIEWER role attempting write action
    res9a = client.post("/api/v1/caravan/remote/discovery", headers=viewer_headers)
    print(f"VIEWER Forbidden Check (expected 403): {res9a.status_code}")
    assert res9a.status_code == 403

    # 9b. AEGIS approval gate for sensitive action category (SPEND_MONEY)
    res9b = client.post(
        "/api/v1/caravan/bridge/action",
        headers=owner_headers,
        json={"action_category": "SPEND_MONEY", "summary": "Caravan marketing ad campaign spend $500"},
    )
    print(f"AEGIS Approval Gate Check (expected 200 with requires_owner_approval=True): {res9b.status_code}")
    data9b = res9b.json()
    print(f"Authorized immediately: {data9b.get('authorized')}")
    print(f"Requires Owner Approval: {data9b.get('requires_owner_approval')}")
    print(f"Approval Status: {data9b.get('approval', {}).get('status')}")
    assert data9b.get("authorized") is False
    assert data9b.get("requires_owner_approval") is True
    assert data9b.get("approval", {}).get("status") == "PENDING"

    # 9c. Invalid S2S Bridge Key rejected on CARAVAN bridge
    with httpx.Client(timeout=5.0) as http_client:
        bad_bridge_res = http_client.get(
            "https://caravan-juwon2.vercel.app/api/v1/bridge/telemetry",
            headers={"X-Ultron-Bridge-Key": "invalid_fake_key_12345"},
        )
    print(f"Invalid Bridge Key Rejection (expected 401): {bad_bridge_res.status_code}")
    assert bad_bridge_res.status_code == 401

    # Step 10: Both systems retain independent authentication and data isolation
    print("\n--- STEP 10: Independent Authentication & Data Isolation ---")
    # Verify ULTRON token cannot authenticate directly against CARAVAN
    with httpx.Client(timeout=5.0) as http_client:
        cross_auth_res = http_client.get(
            "https://caravan-juwon2.vercel.app/api/v1/auth/me",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    print(f"Cross-system Token Isolation (ULTRON token on CARAVAN auth/me, expected 401): {cross_auth_res.status_code}")
    assert cross_auth_res.status_code == 401

    print("\n" + "=" * 80)
    print("SUCCESS: ALL 10 STEPS OF THE LIVE END-TO-END INTEGRATION TEST PASSED!")
    print("=" * 80)

if __name__ == "__main__":
    run_acceptance_audit()
