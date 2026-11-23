"""Unified Integration Manager & OAuth 2.0 PKCE routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
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


# ---------------------------------------------------------------------------
# Universal Connections Centre 2.0
# ---------------------------------------------------------------------------
class RegisterUniversalConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="Custom websites and APIs", max_length=64)
    connection_method: str = Field(default="API_KEY", max_length=32)
    website_url: str = Field(default="", max_length=500)
    docs_url: str = Field(default="", max_length=500)
    api_base_url: str = Field(default="", max_length=500)
    required_headers: dict[str, str] = Field(default_factory=dict)
    required_scopes: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    credentials: dict[str, Any] = Field(default_factory=dict)
    webhook_secret: str = Field(default="", max_length=500)
    subscribed_events: list[str] = Field(default_factory=list)


class WebsiteInspectRequest(BaseModel):
    website_url: str = Field(min_length=4, max_length=500)


class ApproveConnectorRequest(BaseModel):
    scopes: list[str] | None = None


class RotateConnectorRequest(BaseModel):
    credentials: dict[str, Any] = Field(default_factory=dict)
    webhook_secret: str = Field(default="", max_length=500)


class ExecuteConnectorActionRequest(BaseModel):
    capability: str = Field(min_length=2, max_length=120)


@router.get("/universal/catalogue")
def api_universal_catalogue(
    query: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=64),
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import list_universal_catalogue

    return list_universal_catalogue(db, tenant_id=principal.tenant_id, settings=settings, query=query, category=category)


@router.post("/universal/connectors", status_code=status.HTTP_201_CREATED)
def api_register_universal_connector(
    body: RegisterUniversalConnectorRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import register_universal_connector

    return register_universal_connector(
        db,
        principal=principal,
        name=body.name,
        category=body.category,
        connection_method=body.connection_method,
        website_url=body.website_url,
        docs_url=body.docs_url,
        api_base_url=body.api_base_url,
        required_headers=body.required_headers,
        required_scopes=body.required_scopes,
        capabilities=body.capabilities,
        credentials=body.credentials,
        webhook_secret=body.webhook_secret,
        subscribed_events=body.subscribed_events,
        settings=settings,
    )


@router.post("/universal/website-inspect")
def api_inspect_website(
    body: WebsiteInspectRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.universal_connections_service import inspect_website_integration

    return inspect_website_integration(db, principal=principal, website_url=body.website_url)


@router.post("/universal/connectors/{connector_id}/test")
def api_test_universal_connector(
    connector_id: str,
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import test_universal_connector

    return test_universal_connector(db, principal=principal, connector_id=connector_id, settings=settings)


@router.post("/universal/connectors/{connector_id}/approve")
def api_approve_universal_connector(
    connector_id: str,
    body: ApproveConnectorRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.universal_connections_service import approve_connector_permissions

    return approve_connector_permissions(db, principal=principal, connector_id=connector_id, scopes=body.scopes)


@router.post("/universal/connectors/{connector_id}/rotate")
def api_rotate_universal_connector(
    connector_id: str,
    body: RotateConnectorRequest,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import rotate_connector_credentials

    return rotate_connector_credentials(
        db,
        principal=principal,
        connector_id=connector_id,
        credentials=body.credentials,
        webhook_secret=body.webhook_secret,
        settings=settings,
    )


@router.post("/universal/connectors/{connector_id}/revoke")
def api_revoke_universal_connector(
    connector_id: str,
    principal: Principal = Depends(require_perm("integrations:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import revoke_universal_connector

    return revoke_universal_connector(db, principal=principal, connector_id=connector_id, settings=settings)


@router.get("/universal/connectors/{connector_id}/deliveries")
def api_list_universal_deliveries(
    connector_id: str,
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.universal_connections_service import list_webhook_deliveries

    items = list_webhook_deliveries(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    return {"total": len(items), "deliveries": items}


@router.post("/universal/webhooks/{connector_id}")
async def api_receive_universal_webhook(
    connector_id: str,
    request: Request,
    x_ultron_signature: str | None = Header(default=None, alias="X-Ultron-Signature"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    x_event_type: str = Header(default="webhook.event", alias="X-Event-Type"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.universal_connections_service import receive_universal_webhook

    raw_body = await request.body()
    return receive_universal_webhook(
        db,
        connector_id=connector_id,
        raw_body=raw_body,
        signature_header=x_ultron_signature,
        idempotency_key=x_idempotency_key,
        event_type=x_event_type,
        settings=settings,
    )


@router.get("/universal/discover-authorized")
def api_discover_authorized_services(
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.universal_connections_service import discover_authorized_services_for_agents

    items = discover_authorized_services_for_agents(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "services": items}


@router.post("/universal/connectors/{connector_id}/authorize-action")
def api_authorize_connector_action(
    connector_id: str,
    body: ExecuteConnectorActionRequest,
    principal: Principal = Depends(require_perm("integrations:verify")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.universal_connections_service import execute_authorized_connector_action

    return execute_authorized_connector_action(
        db,
        principal=principal,
        connector_id=connector_id,
        capability=body.capability,
    )

