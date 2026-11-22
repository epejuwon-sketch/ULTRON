"""Unified Integration Manager & OAuth 2.0 PKCE routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.integrations.antigravity import inspect_antigravity_environment
from app.routers.deps import require_perm
from app.services.integration_manager import (
    complete_oauth_callback,
    connect_with_credentials,
    disconnect_connection,
    list_connections,
    refresh_connection_token,
    start_oauth_flow,
    verify_provider_live,
)

router = APIRouter(prefix="/api/v1/integrations", tags=["Integration Manager & OAuth 2.0"])


class ConnectCredentialsRequest(BaseModel):
    credentials: dict[str, Any]
    auth_type: str = Field(default="API_KEY", max_length=32)
    scopes: list[str] = Field(default_factory=list)
    account_label: str = Field(default="", max_length=200)
    expires_in_seconds: int | None = Field(default=None, ge=60)


class OAuthStartRequest(BaseModel):
    scopes: list[str] | None = None
    redirect_uri: str | None = None


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=2)
    state: str = Field(min_length=8)


@router.get("/connections")
def api_list_connections(
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return list_connections(db, tenant_id=principal.tenant_id, settings=settings)


@router.get("/antigravity")
def api_antigravity_adapter(
    live: bool = Query(default=False),
    _principal: Principal = Depends(require_perm("integrations:verify")),
) -> dict:
    """Honest inspection of installed/connected official Antigravity plugin adapters."""
    return inspect_antigravity_environment(run_live_auth_checks=live)


@router.post("/{provider}/connect")
def api_connect_provider(
    provider: str,
    body: ConnectCredentialsRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return connect_with_credentials(
        db,
        principal=principal,
        provider=provider,
        credentials=body.credentials,
        auth_type=body.auth_type,
        scopes=body.scopes,
        account_label=body.account_label,
        expires_in_seconds=body.expires_in_seconds,
        settings=settings,
    )


@router.post("/oauth/{provider}/start")
def api_oauth_start(
    provider: str,
    body: OAuthStartRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return start_oauth_flow(
        db,
        principal=principal,
        provider=provider,
        scopes=body.scopes,
        redirect_uri=body.redirect_uri,
        settings=settings,
    )


@router.post("/oauth/{provider}/callback")
def api_oauth_callback(
    provider: str,
    body: OAuthCallbackRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return complete_oauth_callback(
        db,
        principal=principal,
        provider=provider,
        code=body.code,
        state=body.state,
        settings=settings,
    )


@router.post("/{provider}/refresh")
def api_refresh_provider(
    provider: str,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return refresh_connection_token(db, principal=principal, provider=provider, settings=settings)


@router.post("/{provider}/verify")
def api_verify_provider(
    provider: str,
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return verify_provider_live(db, principal=principal, provider=provider, settings=settings)


@router.post("/{provider}/disconnect")
def api_disconnect_provider(
    provider: str,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return disconnect_connection(db, principal=principal, provider=provider, settings=settings)
