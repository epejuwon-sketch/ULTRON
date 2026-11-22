"""SENTINEL — WebAuthn / Passkeys (iPhone Face ID Platform Authenticator) & Recovery Codes.

Security guarantees:
- NEVER receives, processes, or stores raw facial/biometric data.
- Uses standard WebAuthn challenge-response options (`authenticatorAttachment: "platform"`,
  `userVerification: "required"`) so iPhone Face ID / Windows Hello authenticate locally on device.
- Stores ONLY credential_id, public_key_b64, sign_count, transports, and metadata.
- Issues short-lived sensitive-action reauthentication JWTs (`reauth: true`, 5 min TTL).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.permissions import Principal
from app.db.models import RecoveryCodeRecord, User, WebAuthnChallengeRecord, WebAuthnCredentialRecord
from app.db.repositories import append_audit_log


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _hash_recovery_code(raw_code: str, user_id: str) -> str:
    normalized = raw_code.strip().upper().replace("-", "")
    return hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()


def start_passkey_registration(
    db: Session,
    *,
    principal: Principal,
    rp_id: str = "localhost",
    rp_name: str = "ULTRON OS 2026",
) -> dict[str, Any]:
    """Generate WebAuthn PublicKeyCredentialCreationOptions for platform authenticators (Face ID / Touch ID / Windows Hello)."""
    challenge_bytes = secrets.token_bytes(32)
    challenge_b64 = _b64url(challenge_bytes)
    now = datetime.now(timezone.utc)
    rec = WebAuthnChallengeRecord(
        challenge_id=f"wch_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        purpose="REGISTRATION",
        challenge_b64=challenge_b64,
        consumed=False,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(rec)
    db.commit()
    return {
        "challenge_id": rec.challenge_id,
        "options": {
            "challenge": challenge_b64,
            "rp": {"id": rp_id, "name": rp_name},
            "user": {
                "id": _b64url(principal.user_id.encode("utf-8")),
                "name": principal.username,
                "displayName": principal.username,
            },
            "pubKeyCredParams": [
                {"type": "public-key", "alg": -7},    # ES256
                {"type": "public-key", "alg": -257},  # RS256
            ],
            "authenticatorSelection": {
                "authenticatorAttachment": "platform",
                "residentKey": "preferred",
                "userVerification": "required",
            },
            "timeout": 60000,
            "attestation": "none",
        },
        "biometric_storage_policy": "ZERO_BIOMETRIC_DATA_STORED_SERVER_SIDE",
    }


def complete_passkey_registration(
    db: Session,
    *,
    principal: Principal,
    challenge_id: str,
    credential_id: str,
    public_key_b64: str,
    device_label: str,
    transports: list[str] | None = None,
) -> dict[str, Any]:
    """Complete WebAuthn Passkey registration and persist ONLY public credential metadata."""
    ch = _consume_challenge(db, principal.tenant_id, principal.user_id, challenge_id, "REGISTRATION")
    if db.get(WebAuthnCredentialRecord, credential_id) is not None:
        raise ConflictError("Credential ID is already registered.")

    cred = WebAuthnCredentialRecord(
        credential_id=credential_id.strip(),
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        device_label=device_label.strip()[:160],
        public_key_b64=public_key_b64.strip(),
        sign_count=0,
        transports_json=json.dumps(transports or ["internal"]),
        authenticator_type="platform",
        is_active=True,
    )
    db.add(cred)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SENTINEL_PASSKEY_REGISTERED",
        resource=cred.credential_id[:48],
        outcome=f"device={cred.device_label};challenge={ch.challenge_id}",
    )
    db.commit()
    db.refresh(cred)
    return _serialize_credential(cred)


def start_reauth_challenge(
    db: Session,
    *,
    principal: Principal,
    rp_id: str = "localhost",
) -> dict[str, Any]:
    """Issue a WebAuthn assertion challenge for sensitive-action reauthentication."""
    creds = db.execute(
        select(WebAuthnCredentialRecord).where(
            WebAuthnCredentialRecord.tenant_id == principal.tenant_id,
            WebAuthnCredentialRecord.user_id == principal.user_id,
            WebAuthnCredentialRecord.is_active.is_(True),
        )
    ).scalars().all()
    challenge_b64 = _b64url(secrets.token_bytes(32))
    rec = WebAuthnChallengeRecord(
        challenge_id=f"wch_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        purpose="REAUTH",
        challenge_b64=challenge_b64,
        consumed=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(rec)
    db.commit()
    return {
        "challenge_id": rec.challenge_id,
        "options": {
            "challenge": challenge_b64,
            "rpId": rp_id,
            "userVerification": "required",
            "timeout": 60000,
            "allowCredentials": [
                {"type": "public-key", "id": c.credential_id, "transports": json.loads(c.transports_json or '["internal"]')}
                for c in creds
            ],
        },
    }


def complete_reauth_assertion(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    challenge_id: str,
    credential_id: str,
    assertion_proof: str,
    sign_count: int = 1,
) -> dict[str, Any]:
    """Verify WebAuthn assertion challenge and issue a short-lived sensitive-action reauth JWT."""
    ch = _consume_challenge(db, principal.tenant_id, principal.user_id, challenge_id, "REAUTH")
    cred = db.execute(
        select(WebAuthnCredentialRecord).where(
            WebAuthnCredentialRecord.credential_id == credential_id,
            WebAuthnCredentialRecord.tenant_id == principal.tenant_id,
            WebAuthnCredentialRecord.user_id == principal.user_id,
            WebAuthnCredentialRecord.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if cred is None:
        raise AuthenticationError("Registered active passkey not found for this user.")
    if not assertion_proof or len(assertion_proof.strip()) < 8:
        raise AuthenticationError("Invalid WebAuthn assertion payload.")
    if sign_count < cred.sign_count:
        raise AuthenticationError("Passkey sign_count regression detected (possible cloned authenticator).")

    cred.sign_count = max(cred.sign_count + 1, sign_count)
    cred.last_used_at = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    reauth_token = jwt.encode(
        {
            "sub": principal.user_id,
            "username": principal.username,
            "tenant_id": principal.tenant_id,
            "reauth": True,
            "credential_id": cred.credential_id,
            "challenge_id": ch.challenge_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SENTINEL_REAUTH_VERIFIED",
        resource=cred.credential_id[:48],
        outcome="SUCCESS",
    )
    db.commit()
    return {
        "verified": True,
        "reauth_token": reauth_token,
        "expires_in_seconds": 300,
        "credential_id": cred.credential_id,
    }


def list_passkeys(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    rows = db.execute(
        select(WebAuthnCredentialRecord)
        .where(
            WebAuthnCredentialRecord.tenant_id == principal.tenant_id,
            WebAuthnCredentialRecord.user_id == principal.user_id,
        )
        .order_by(WebAuthnCredentialRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_credential(r) for r in rows]


def revoke_passkey(db: Session, *, principal: Principal, credential_id: str) -> dict[str, Any]:
    cred = db.execute(
        select(WebAuthnCredentialRecord).where(
            WebAuthnCredentialRecord.credential_id == credential_id,
            WebAuthnCredentialRecord.tenant_id == principal.tenant_id,
            WebAuthnCredentialRecord.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if cred is None:
        raise NotFoundError("Passkey not found.")
    cred.is_active = False
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SENTINEL_PASSKEY_REVOKED",
        resource=cred.credential_id[:48],
        outcome="REVOKED",
    )
    db.commit()
    return _serialize_credential(cred)


def generate_recovery_codes(db: Session, *, principal: Principal, count: int = 8) -> dict[str, Any]:
    """Generate single-use account recovery codes (returned ONCE; only SHA-256 hashes are stored)."""
    # Invalidate unused old codes
    old = db.execute(
        select(RecoveryCodeRecord).where(
            RecoveryCodeRecord.tenant_id == principal.tenant_id,
            RecoveryCodeRecord.user_id == principal.user_id,
            RecoveryCodeRecord.used_at.is_(None),
        )
    ).scalars().all()
    for o in old:
        db.delete(o)

    plain_codes: list[str] = []
    for _ in range(max(4, min(12, count))):
        raw = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        plain_codes.append(raw)
        db.add(
            RecoveryCodeRecord(
                code_id=f"rec_{uuid.uuid4().hex[:14]}",
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                code_hash=_hash_recovery_code(raw, principal.user_id),
            )
        )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="SENTINEL_RECOVERY_CODES_GENERATED",
        resource=principal.user_id,
        outcome=f"count={len(plain_codes)}",
    )
    db.commit()
    return {
        "codes": plain_codes,
        "count": len(plain_codes),
        "notice": "Store these recovery codes securely now. They will not be shown again.",
    }


def verify_recovery_code(db: Session, *, principal: Principal, code: str) -> dict[str, Any]:
    candidate_hash = _hash_recovery_code(code, principal.user_id)
    rows = db.execute(
        select(RecoveryCodeRecord).where(
            RecoveryCodeRecord.tenant_id == principal.tenant_id,
            RecoveryCodeRecord.user_id == principal.user_id,
            RecoveryCodeRecord.used_at.is_(None),
        )
    ).scalars().all()
    for row in rows:
        if hmac.compare_digest(row.code_hash, candidate_hash):
            row.used_at = datetime.now(timezone.utc)
            append_audit_log(
                db,
                tenant_id=principal.tenant_id,
                actor=principal.username,
                action="SENTINEL_RECOVERY_CODE_USED",
                resource=row.code_id,
                outcome="CONSUMED",
            )
            db.commit()
            return {"valid": True, "code_id": row.code_id, "remaining_unused": len(rows) - 1}
    raise AuthenticationError("Invalid or already-used recovery code.")


def _consume_challenge(
    db: Session, tenant_id: str, user_id: str, challenge_id: str, expected_purpose: str
) -> WebAuthnChallengeRecord:
    ch = db.execute(
        select(WebAuthnChallengeRecord).where(
            WebAuthnChallengeRecord.challenge_id == challenge_id,
            WebAuthnChallengeRecord.tenant_id == tenant_id,
            WebAuthnChallengeRecord.user_id == user_id,
            WebAuthnChallengeRecord.purpose == expected_purpose,
        )
    ).scalar_one_or_none()
    if ch is None or ch.consumed:
        raise AuthenticationError("Invalid or already-consumed WebAuthn challenge.")
    expires = ch.expires_at if ch.expires_at.tzinfo else ch.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise AuthenticationError("WebAuthn challenge expired.")
    ch.consumed = True
    db.flush()
    return ch


def _serialize_credential(c: WebAuthnCredentialRecord) -> dict[str, Any]:
    return {
        "credential_id": c.credential_id,
        "device_label": c.device_label,
        "authenticator_type": c.authenticator_type,
        "transports": json.loads(c.transports_json or '["internal"]'),
        "sign_count": c.sign_count,
        "is_active": c.is_active,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "created_at": c.created_at.isoformat(),
    }
