"""VAULT Earliest-Boundary Secret Interception & Payment Data Guard.

Detects secrets (API keys, tokens, passwords, private keys, JWTs) and raw payment
card PANs/CVVs BEFORE text is stored in chat history, memory, logs, or sent to
Gemini / external LLM providers.

- Detected API keys/passwords/tokens are automatically encrypted in the tenant's
  VAULT (AES-256-GCM) and replaced inline with a safe placeholder token
  `{{VAULT_REF:<name>}}`.
- Raw payment card numbers (13-19 digits passing Luhn) and CVVs are IMMEDIATELY
  scrubbed and NEVER stored in VAULT, chat logs, memory, or database tables.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Principal
from app.services.vault_service import store_secret

# High-confidence secret patterns
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z\-_]{24,}\b")),
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[0-9A-Za-z\-_]{20,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{28,}\b")),
    ("GITHUB_PAT", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{30,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{18,}\b")),
    ("JWT_TOKEN", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----")),
    (
        "CREDENTIAL_ASSIGNMENT",
        re.compile(
            r"(?i)\b(?:password|passwd|api_key|apikey|secret_key|access_token|refresh_token|service_role_key)\s*[:=]\s*['\"]?([A-Za-z0-9!@#$%^&*_\-+=/.]{8,128})['\"]?"
        ),
    ),
]

# Payment PAN candidate (13 to 19 digits, allowing spaces or hyphens)
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_CVV_RE = re.compile(r"(?i)\b(?:cvv|cvc|security\s+code|card\s+code)\s*[:=#]?\s*(\d{3,4})\b")


def _luhn_valid(digits: str) -> bool:
    if not (13 <= len(digits) <= 19) or not digits.isdigit():
        return False
    total = 0
    reverse_digits = digits[::-1]
    for idx, ch in enumerate(reverse_digits):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def contains_raw_payment_card_or_cvv(text: str) -> bool:
    """Return True if text contains a Luhn-valid raw PAN or an explicit CVV value."""
    if _CVV_RE.search(text):
        return True
    for match in _CARD_CANDIDATE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if _luhn_valid(digits):
            return True
    return False


@dataclass
class SecretInterceptionResult:
    sanitized_text: str
    secrets_vaulted: list[str] = field(default_factory=list)
    payment_data_blocked: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def redaction_count(self) -> int:
        return len(self.secrets_vaulted) + (1 if self.payment_data_blocked else 0)


def intercept_and_redact_secrets(
    text: str,
    *,
    db: Session | None = None,
    principal: Principal | None = None,
    settings: Settings | None = None,
    source_context: str = "chat",
    auto_vault: bool = True,
) -> SecretInterceptionResult:
    """Intercept secrets and raw card/CVV data at the earliest input boundary.

    - Payment card numbers (Luhn-valid) and CVVs are scrubbed immediately and NEVER vaulted.
    - API keys, tokens, and inline passwords are encrypted in VAULT (when db/principal/settings
      are supplied and auto_vault=True) and replaced with `{{VAULT_REF:<secret_name>}}`.
    """
    if not text:
        return SecretInterceptionResult(sanitized_text=text)

    sanitized = text
    vaulted_refs: list[str] = []
    warnings: list[str] = []
    payment_blocked = False

    # 1. Immediately scrub raw payment card numbers (NEVER store PAN in VAULT or DB)
    def _scrub_card(match: re.Match[str]) -> str:
        nonlocal payment_blocked
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if _luhn_valid(digits):
            payment_blocked = True
            return "{{REDACTED_PAYMENT_CARD_BLOCKED}}"
        return raw

    sanitized = _CARD_CANDIDATE_RE.sub(_scrub_card, sanitized)

    if _CVV_RE.search(sanitized):
        payment_blocked = True
        sanitized = _CVV_RE.sub("cvv={{REDACTED_CVV_BLOCKED}}", sanitized)

    if payment_blocked:
        warnings.append(
            "Raw payment card number or CVV detected and immediately scrubbed. "
            "ULTRON never stores raw PAN/CVV; use tokenized payment methods via /api/v1/finance/payment-methods."
        )

    # 2. Intercept API keys, tokens, private keys, and inline credentials
    for label, pattern in SECRET_PATTERNS:
        matches = list(pattern.finditer(sanitized))
        if not matches:
            continue
        # Replace from right to left to keep indices intact
        for match in reversed(matches):
            if label == "CREDENTIAL_ASSIGNMENT":
                secret_val = match.group(1)
                start, end = match.start(1), match.end(1)
            else:
                secret_val = match.group(0)
                start, end = match.start(0), match.end(0)

            # Skip already-redacted placeholders
            if secret_val.startswith("{{VAULT_REF:") or secret_val.startswith("{{REDACTED"):
                continue

            vault_name = f"AUTO_{label}_{uuid.uuid4().hex[:8].upper()}"
            if auto_vault and db is not None and principal is not None and settings is not None:
                try:
                    store_secret(
                        db,
                        principal=principal,
                        name=vault_name,
                        value=secret_val,
                        provider=f"auto_{source_context[:32]}",
                        settings=settings,
                    )
                except Exception:
                    # Even if vault persistence fails, NEVER leak the raw secret forward
                    vault_name = f"REDACTED_{label}"
            else:
                vault_name = f"REDACTED_{label}"

            placeholder = f"{{{{VAULT_REF:{vault_name}}}}}"
            sanitized = sanitized[:start] + placeholder + sanitized[end:]
            vaulted_refs.append(vault_name)

    if vaulted_refs:
        warnings.append(
            f"Intercepted and encrypted {len(vaulted_refs)} secret(s) into VAULT before AI/memory routing."
        )

    return SecretInterceptionResult(
        sanitized_text=sanitized,
        secrets_vaulted=vaulted_refs,
        payment_data_blocked=payment_blocked,
        warnings=warnings,
    )
