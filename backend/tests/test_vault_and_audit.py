"""Tests for ARGON AES-256-GCM secret vault and SHA-256 hash-chained audit ledger."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.exceptions import SecurityViolationError
from app.core.security import decrypt_vault_secret, encrypt_vault_secret
from app.db.models import AuditLogRecord
from app.db.session import get_session_factory


def test_vault_encryption_metadata_isolation_and_rotation(client: TestClient, auth_headers: dict) -> None:
    # OPERATOR cannot access vault
    assert client.get("/api/v1/vault/secrets", headers=auth_headers["operator"]).status_code == 403

    # OWNER stores secret
    stored = client.post(
        "/api/v1/vault/secrets",
        headers=auth_headers["owner"],
        json={"name": "STRIPE_LIVE_KEY", "value": "sk_test_ultron_secret_v1", "provider": "stripe"},
    )
    assert stored.status_code == 201
    assert stored.json()["version"] == 1
    assert "value" not in stored.json()

    # Listing returns metadata only (never raw value or ciphertext)
    listed = client.get("/api/v1/vault/secrets", headers=auth_headers["owner"]).json()
    assert listed["total"] == 1
    assert "sk_test_ultron_secret_v1" not in str(listed)

    # Rotate secret -> version increments
    rotated = client.post(
        "/api/v1/vault/secrets",
        headers=auth_headers["owner"],
        json={"name": "STRIPE_LIVE_KEY", "value": "sk_test_ultron_secret_v2", "provider": "stripe"},
    )
    assert rotated.status_code == 201
    assert rotated.json()["version"] == 2

    # Reveal decrypts current version
    revealed = client.get("/api/v1/vault/secrets/STRIPE_LIVE_KEY/reveal", headers=auth_headers["owner"])
    assert revealed.status_code == 200
    assert revealed.json()["value"] == "sk_test_ultron_secret_v2"

    # Delete secret
    assert client.delete("/api/v1/vault/secrets/STRIPE_LIVE_KEY", headers=auth_headers["owner"]).status_code == 200
    assert client.get("/api/v1/vault/secrets/STRIPE_LIVE_KEY/reveal", headers=auth_headers["owner"]).status_code == 404


def test_aes_gcm_aad_prevents_cross_tenant_ciphertext_swap() -> None:
    ct, nonce = encrypt_vault_secret("super-secret", master_secret="master-key-123456789012345678901234", aad="tenant-A::KEY")
    assert decrypt_vault_secret(ct, nonce, master_secret="master-key-123456789012345678901234", aad="tenant-A::KEY") == "super-secret"
    try:
        decrypt_vault_secret(ct, nonce, master_secret="master-key-123456789012345678901234", aad="tenant-B::KEY")
        raise AssertionError("Expected SecurityViolationError on AAD mismatch")
    except SecurityViolationError:
        pass


def test_audit_log_hash_chain_and_tamper_detection(client: TestClient, auth_headers: dict) -> None:
    logs = client.get("/api/v1/audit/logs", headers=auth_headers["owner"])
    assert logs.status_code == 200
    assert logs.json()["total"] >= 3

    verified = client.get("/api/v1/audit/verify", headers=auth_headers["owner"])
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["checked_entries"] >= 3

    # Simulate direct DB tampering and confirm verifier catches broken chain
    with get_session_factory()() as db:
        first = db.execute(select(AuditLogRecord).order_by(AuditLogRecord.seq.asc()).limit(1)).scalar_one()
        first.entry_hash = "f" * 64
        db.commit()

    tampered = client.get("/api/v1/audit/verify", headers=auth_headers["owner"])
    assert tampered.status_code == 200
    assert tampered.json()["valid"] is False
    assert tampered.json()["broken_seq"] is not None
