"""ARGON AES-256-GCM Secret Vault endpoints (OWNER/ADMIN only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import StoreSecretRequest
from app.services.vault_service import (
    delete_secret,
    list_secrets_metadata,
    reveal_secret,
    store_secret,
)

router = APIRouter(prefix="/api/v1/vault", tags=["ARGON Cryptographic Vault"])


@router.post("/secrets", status_code=status.HTTP_201_CREATED)
def api_store_secret(
    body: StoreSecretRequest,
    principal: Principal = Depends(require_perm("vault:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return store_secret(
        db,
        principal=principal,
        name=body.name,
        value=body.value,
        provider=body.provider,
        settings=settings,
    )


@router.get("/secrets")
def api_list_secrets(
    principal: Principal = Depends(require_perm("vault:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_secrets_metadata(db, principal=principal)
    return {"total": len(items), "secrets": items}


@router.get("/secrets/{name}/reveal")
def api_reveal_secret(
    name: str,
    principal: Principal = Depends(require_perm("vault:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return reveal_secret(db, principal=principal, name=name, settings=settings)


@router.delete("/secrets/{name}")
def api_delete_secret(
    name: str,
    principal: Principal = Depends(require_perm("vault:write")),
    db: Session = Depends(get_db),
) -> dict:
    delete_secret(db, principal=principal, name=name)
    return {"deleted": True, "name": name.strip().upper()}
