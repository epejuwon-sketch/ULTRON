"""Tests for VAULT secret interception, AEGIS autonomous security, EVOLVE governance, and SENTINEL Passkeys."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_vault_early_secret_interception_and_pan_blocking(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # Create a JARVIS conversation and send a message containing an API key and a Luhn-valid test card + CVV
    conv = client.post(
        "/api/v1/neon/conversations",
        headers=auth_headers["owner"],
        json={"title": "Secret Guard Test", "agent_id": "AGT-01"},
    )
    assert conv.status_code == 201
    cid = conv.json()["conversation_id"]

    # Construct test secret tokens dynamically so scanners don't flag static strings in source
    fake_api_key = "AIza" + "SyTestKey0123456789abcdefghijklm"
    luhn_card = "4242" + " 4242 " + "4242 " + "4242"
    msg = client.post(
        f"/api/v1/neon/conversations/{cid}/messages",
        headers=auth_headers["owner"],
        json={"content": f"Use key {fake_api_key} and card {luhn_card} cvv 123 for setup"},
    )
    assert msg.status_code == 200
    body = msg.json()
    sanitized = body["sanitized_user_message"]
    assert fake_api_key not in sanitized
    assert "4242 4242 4242 4242" not in sanitized
    assert "{{VAULT_REF:AUTO_GOOGLE_API_KEY_" in sanitized
    assert "{{REDACTED_PAYMENT_CARD_BLOCKED}}" in sanitized
    assert body["secret_interception"]["payment_data_blocked"] is True
    assert len(body["secret_interception"]["secrets_vaulted"]) == 1

    # Verify secret was auto-vaulted in VAULT, while card PAN was NEVER vaulted
    vault_list = client.get("/api/v1/vault/secrets", headers=auth_headers["owner"]).json()
    names = [s["name"] for s in vault_list["secrets"]]
    assert any(n.startswith("AUTO_GOOGLE_API_KEY_") for n in names)

    # Verify memory endpoint also intercepts and redacts secrets before storage
    mem = client.post(
        "/api/v1/memory",
        headers=auth_headers["owner"],
        json={"content": f"Remember token ghp_{'A' * 36} for CI", "memory_type": "EPISODIC"},
    )
    assert mem.status_code == 201
    assert "ghp_" not in mem.json()["content"]
    assert "{{VAULT_REF:AUTO_GITHUB_TOKEN_" in mem.json()["content"]


def test_aegis_scan_url_inspection_code_scan_and_remediation(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    scan_resp = client.post(
        "/api/v1/aegis/scans",
        headers=auth_headers["owner"],
        json={"scan_type": "FULL"},
    )
    assert scan_resp.status_code == 201
    scan = scan_resp.json()["scan"]
    assert scan["status"] == "COMPLETED"
    assert 0 <= scan["risk_score"] <= 100
    assert any(c["check"] == "audit_hash_chain" and c["status"] == "PASS" for c in scan["checks_run"])
    assert any(c["check"] == "file_integrity_monitoring" for c in scan["checks_run"])

    posture = client.get("/api/v1/aegis/posture", headers=auth_headers["owner"]).json()
    assert posture["status"] == "ACTIVE"
    assert posture["fim_files_monitored"] >= 4

    # URL safety checks
    safe_url = client.post(
        "/api/v1/aegis/inspect-url",
        headers=auth_headers["owner"],
        json={"url": "https://example.com/docs"},
    ).json()
    assert safe_url["verdict"] == "SAFE"

    ssrf_url = client.post(
        "/api/v1/aegis/inspect-url",
        headers=auth_headers["owner"],
        json={"url": "http://169.254.169.254/latest/meta-data/"},
    ).json()
    assert ssrf_url["verdict"] == "BLOCKED"

    # Code scan blocks eval()
    bad_code = client.post(
        "/api/v1/aegis/scan-code",
        headers=auth_headers["owner"],
        json={"files": {"bad.py": "x = eval('1+1')\n"}},
    ).json()
    assert bad_code["passed"] is False
    assert bad_code["critical_or_high_count"] >= 1


def test_evolve_lifecycle_aegis_gate_approval_and_rollback(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    prop = client.post(
        "/api/v1/evolve/proposals",
        headers=auth_headers["owner"],
        json={
            "title": "Add CSV summary helper",
            "capability_gap": "Agents need reusable CSV normalization helper",
            "target_module": "backend/app/utils/csv_helper.py",
            "plan_steps": ["Implement helper", "Test AST", "AEGIS scan", "Approve"],
        },
    )
    assert prop.status_code == 201
    pid = prop.json()["proposal_id"]

    # Unsafe code blocked by AEGIS
    blocked = client.post(
        f"/api/v1/evolve/proposals/{pid}/verify",
        headers=auth_headers["owner"],
        json={
            "patch_files": {"csv_helper.py": "import os\nos.system('rm -rf /tmp/x')\n"},
            "patch_summary": "Unsafe candidate",
        },
    ).json()
    assert blocked["submitted_for_approval"] is False
    assert blocked["aegis_verification"]["passed"] is False

    # Clean code passes AEGIS and enters WAITING_FOR_APPROVAL
    verified = client.post(
        f"/api/v1/evolve/proposals/{pid}/verify",
        headers=auth_headers["owner"],
        json={
            "patch_files": {"csv_helper.py": "def normalize(s: str) -> str:\n    return s.strip()\n"},
            "patch_summary": "Clean pure helper function",
        },
    ).json()
    assert verified["submitted_for_approval"] is True
    approval_id = verified["approval"]["approval_id"]

    # Promote BEFORE approval must be blocked (409)
    premature = client.post(f"/api/v1/evolve/proposals/{pid}/promote", headers=auth_headers["owner"])
    assert premature.status_code == 409

    # Approve via ApprovalGate
    dec = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=auth_headers["owner"],
        json={"decision": "APPROVED", "note": "Verified clean"},
    )
    assert dec.status_code == 200

    # Promote succeeds
    promoted = client.post(f"/api/v1/evolve/proposals/{pid}/promote", headers=auth_headers["owner"])
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "PROMOTED"

    # Rollback works cleanly
    rb = client.post(
        f"/api/v1/evolve/proposals/{pid}/rollback",
        headers=auth_headers["owner"],
        json={"reason": "Testing rollback drill"},
    )
    assert rb.status_code == 200
    assert rb.json()["status"] == "ROLLED_BACK"


def test_sentinel_passkeys_reauth_and_recovery_codes(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    opts = client.post(
        "/api/v1/sentinel/passkeys/register/options",
        headers=auth_headers["owner"],
        json={"rp_id": "ultron.local"},
    )
    assert opts.status_code == 200
    ch_id = opts.json()["challenge_id"]
    assert opts.json()["options"]["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert opts.json()["biometric_storage_policy"] == "ZERO_BIOMETRIC_DATA_STORED_SERVER_SIDE"

    reg = client.post(
        "/api/v1/sentinel/passkeys/register/complete",
        headers=auth_headers["owner"],
        json={
            "challenge_id": ch_id,
            "credential_id": "cred_iphone_faceid_001",
            "public_key_b64": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEtestpublickeydata123456",
            "device_label": "iPhone 16 Pro (Face ID)",
        },
    )
    assert reg.status_code == 201
    assert reg.json()["credential_id"] == "cred_iphone_faceid_001"

    # Reauth flow
    reauth_opts = client.post(
        "/api/v1/sentinel/reauth/options",
        headers=auth_headers["owner"],
        json={"rp_id": "ultron.local"},
    ).json()
    reauth_done = client.post(
        "/api/v1/sentinel/reauth/complete",
        headers=auth_headers["owner"],
        json={
            "challenge_id": reauth_opts["challenge_id"],
            "credential_id": "cred_iphone_faceid_001",
            "assertion_proof": "signed_webauthn_assertion_payload_v1",
            "sign_count": 1,
        },
    )
    assert reauth_done.status_code == 200
    assert reauth_done.json()["verified"] is True
    assert reauth_done.json()["reauth_token"]

    # Recovery codes generation & single-use verification
    rc = client.post("/api/v1/sentinel/recovery-codes/generate", headers=auth_headers["owner"])
    assert rc.status_code == 201
    first_code = rc.json()["codes"][0]

    v1 = client.post(
        "/api/v1/sentinel/recovery-codes/verify",
        headers=auth_headers["owner"],
        json={"code": first_code},
    )
    assert v1.status_code == 200
    assert v1.json()["valid"] is True

    # Reusing the same recovery code must fail
    v2 = client.post(
        "/api/v1/sentinel/recovery-codes/verify",
        headers=auth_headers["owner"],
        json={"code": first_code},
    )
    assert v2.status_code == 401
