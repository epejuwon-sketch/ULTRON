"""ARGON AES-256-GCM envelope-encrypted secret vault service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.core.security import decrypt_vault_secret, encrypt_vault_secret
from app.db.models import VaultSecretRecord
from app.db.repositories import append_audit_log


def _aad(tenant_id: str, name: str) -> str:
    return f"ultron-vault::{tenant_id}::{name}"


def store_secret(
    db: Session,
    *,
    principal: Principal,
    name: str,
    value: str,
    provider: str,
    settings: Settings,
) -> dict[str, Any]:
    """Encrypt and upsert a tenant-scoped secret with AES-256-GCM + AAD binding."""
    clean_name = name.strip().upper()
    ciphertext_b64, nonce_b64 = encrypt_vault_secret(
        value,
        master_secret=settings.vault_master_key.get_secret_value(),
        aad=_aad(principal.tenant_id, clean_name),
    )
    existing = db.execute(
        select(VaultSecretRecord).where(
            VaultSecretRecord.tenant_id == principal.tenant_id,
            VaultSecretRecord.name == clean_name,
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.ciphertext_b64 = ciphertext_b64
        existing.nonce_b64 = nonce_b64
        existing.provider = provider.strip().lower()
        existing.version += 1
        existing.updated_at = now
        record = existing
        action = "VAULT_SECRET_ROTATED"
    else:
        record = VaultSecretRecord(
            secret_id=f"sec_{uuid.uuid4().hex[:16]}",
            tenant_id=principal.tenant_id,
            name=clean_name,
            provider=provider.strip().lower(),
            ciphertext_b64=ciphertext_b64,
            nonce_b64=nonce_b64,
            version=1,
            created_by=principal.username,
        )
        db.add(record)
        action = "VAULT_SECRET_STORED"

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=action,
        resource=clean_name,
        outcome=f"VERSION_{record.version}",
    )
    db.commit()
    db.refresh(record)
    return {
        "secret_id": record.secret_id,
        "name": record.name,
        "provider": record.provider,
        "version": record.version,
        "created_by": record.created_by,
        "updated_at": record.updated_at.isoformat(),
    }


def list_secrets_metadata(db: Session, *, principal: Principal) -> list[dict[str, Any]]:
    """Return metadata only — never returns raw or encrypted secret material."""
    rows = db.execute(
        select(VaultSecretRecord)
        .where(VaultSecretRecord.tenant_id == principal.tenant_id)
        .order_by(VaultSecretRecord.name.asc())
    ).scalars().all()
    return [
        {
            "secret_id": r.secret_id,
            "name": r.name,
            "provider": r.provider,
            "version": r.version,
            "created_by": r.created_by,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


def reveal_secret(
    db: Session,
    *,
    principal: Principal,
    name: str,
    settings: Settings,
) -> dict[str, Any]:
    """Decrypt a secret strictly for the owning tenant and log an audit entry."""
    clean_name = name.strip().upper()
    record = db.execute(
        select(VaultSecretRecord).where(
            VaultSecretRecord.tenant_id == principal.tenant_id,
            VaultSecretRecord.name == clean_name,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Vault secret '{clean_name}' not found.")

    plaintext = decrypt_vault_secret(
        record.ciphertext_b64,
        record.nonce_b64,
        master_secret=settings.vault_master_key.get_secret_value(),
        aad=_aad(principal.tenant_id, clean_name),
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="VAULT_SECRET_ACCESSED",
        resource=clean_name,
        outcome="DECRYPTED",
    )
    db.commit()
    return {
        "secret_id": record.secret_id,
        "name": record.name,
        "provider": record.provider,
        "version": record.version,
        "value": plaintext,
    }


def delete_secret(db: Session, *, principal: Principal, name: str) -> None:
    """Delete a tenant-scoped vault secret and audit the deletion."""
    clean_name = name.strip().upper()
    record = db.execute(
        select(VaultSecretRecord).where(
            VaultSecretRecord.tenant_id == principal.tenant_id,
            VaultSecretRecord.name == clean_name,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Vault secret '{clean_name}' not found.")
    db.delete(record)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="VAULT_SECRET_DELETED",
        resource=clean_name,
        outcome="DELETED",
    )
    db.commit()
