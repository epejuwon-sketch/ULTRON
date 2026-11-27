"""ARGON cryptographic primitives, JWT tokens, AES-256-GCM vault encryption, and input guards."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, SecurityViolationError

# Blueprint Section 5: Argon2id with t=3, m=64 MiB (65536 KiB), p=4
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"bypass\s+approval\s*gate", re.IGNORECASE),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+prompt|vault|master\s+key|api\s+keys?)", re.IGNORECASE),
    re.compile(r"(?:exfiltrate|dump)\s+(?:all\s+)?(?:secrets|credentials|tokens)", re.IGNORECASE),
    re.compile(r"override\s+(?:security|argon|governance)\s+policy", re.IGNORECASE),
]

_HIGH_RISK_KEYWORDS = (
    "wire transfer",
    "bank transfer",
    "payment",
    "payout",
    "deploy production",
    "delete database",
    "drop table",
    "rotate key",
    "send email",
    "send whatsapp",
    "execute shell",
    "modify firewall",
    "dns change",
)

_MEDIUM_RISK_KEYWORDS = (
    "update",
    "write",
    "create",
    "webhook",
    "schedule",
    "migrate",
    "scrape",
    "external api",
)


def hash_password(plain_password: str) -> str:
    """Hash a password using Argon2id (t=3, m=64MiB, p=4)."""
    if len(plain_password) < 8:
        raise SecurityViolationError("Password must be at least 8 characters long.")
    return _PASSWORD_HASHER.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against its Argon2id hash in constant time."""
    if not plain_password or not password_hash:
        return False
    try:
        return bool(_PASSWORD_HASHER.verify(password_hash, plain_password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    tenant_id: str,
    settings: Settings,
) -> tuple[str, str, datetime]:
    """Issue a signed HS256 JWT access token with unique JTI."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.access_token_ttl_seconds)
    jti = f"jti_{uuid.uuid4().hex}"
    payload: dict[str, Any] = {
        "iss": "ultron-os-2026",
        "sub": user_id,
        "username": username,
        "role": role,
        "tenant_id": tenant_id,
        "jti": jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, jti, expires_at


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate an HS256 JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer="ultron-os-2026",
            options={"require": ["sub", "jti", "exp", "role", "tenant_id"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.", code="ACCESS_TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.", code="INVALID_ACCESS_TOKEN") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.", code="INVALID_TOKEN_TYPE")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Generate a high-entropy refresh token and its SHA-256 digest for storage."""
    raw = f"ultron_rt_{secrets.token_urlsafe(36)}"
    digest = hash_token(raw)
    return raw, digest


def hash_token(raw_token: str) -> str:
    """Return deterministic SHA-256 hex digest of an opaque token."""
    return hashlib.sha256(f"ultron-os-2026::{raw_token}".encode("utf-8")).hexdigest()


def verify_hmac_signature(payload: bytes, signature_hex: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature in constant time."""
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex.strip())


def _derive_vault_key(master_secret: str) -> bytes:
    """Derive a 256-bit AES-GCM key from the vault master secret via HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"ultron-os-2026-argon-vault-v1",
        info=b"aes-256-gcm-envelope",
    )
    return hkdf.derive(master_secret.encode("utf-8"))


def encrypt_vault_secret(plaintext: str, *, master_secret: str, aad: str) -> tuple[str, str]:
    """Encrypt a secret payload with AES-256-GCM and a unique 12-byte nonce + AAD."""
    key = _derive_vault_key(master_secret)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_vault_secret(ciphertext_b64: str, nonce_b64: str, *, master_secret: str, aad: str) -> str:
    """Decrypt an AES-256-GCM encrypted vault secret, verifying authentication tag and AAD."""
    key = _derive_vault_key(master_secret)
    aesgcm = AESGCM(key)
    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad.encode("utf-8"))
    except Exception as exc:
        raise SecurityViolationError("Vault decryption failed: integrity tag or AAD mismatch.") from exc
    return plaintext.decode("utf-8")


def detect_prompt_injection(text: str) -> list[str]:
    """Inspect user or agent text for prompt-injection or policy-bypass patterns."""
    matches: list[str] = []
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(text or ""):
            matches.append(pattern.pattern)
    return matches


def sanitize_prompt_input(text: str, *, reject_injection: bool = True) -> str:
    """Normalize control characters and optionally block prompt-injection attempts."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", (text or "").strip())
    if reject_injection:
        hits = detect_prompt_injection(cleaned)
        if hits:
            raise SecurityViolationError(
                "Input blocked by ARGON prompt-injection guard.",
                details={"matched_rules": len(hits)},
            )
    return cleaned


def validate_outbound_url(url: str) -> str:
    """Enforce SSRF protections: allow only public HTTP(S) destinations."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise SecurityViolationError("Only http and https URLs are allowed.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SecurityViolationError("URL must include a valid hostname.")
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"} or host.endswith(  # nosec B104
        (".local", ".internal")
    ):
        raise SecurityViolationError(f"Outbound access to internal host '{host}' is blocked by SSRF guard.")
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise SecurityViolationError(f"Outbound access to non-public IP '{host}' is blocked by SSRF guard.")
    except ValueError:
        # Hostname is a domain name, not an IP literal.
        pass
    return parsed.geturl()


def classify_risk_level(text: str, *, financial_amount_usd: float = 0.0, soft_limit_usd: float = 50.0) -> str:
    """Classify an operation into LOW, MEDIUM, or HIGH risk for ApprovalGate enforcement."""
    if financial_amount_usd > soft_limit_usd:
        return "HIGH"
    lowered = (text or "").lower()
    if any(keyword in lowered for keyword in _HIGH_RISK_KEYWORDS):
        return "HIGH"
    if financial_amount_usd > 0.0 or any(keyword in lowered for keyword in _MEDIUM_RISK_KEYWORDS):
        return "MEDIUM"
    return "LOW"
