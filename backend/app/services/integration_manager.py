"""Central IntegrationManager: OAuth 2.0 + PKCE, AES-256-GCM credential storage, refresh, live verification, and revocation."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, IntegrationError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.security import decrypt_vault_secret, encrypt_vault_secret
from app.db.models import IntegrationConnectionRecord, OAuthStateRecord
from app.db.repositories import append_audit_log
from app.integrations.antigravity import inspect_antigravity_environment
from app.integrations.cloudflare import CloudflareClient
from app.integrations.gemini import GeminiClient
from app.integrations.github_client import GitHubEngineeringClient
from app.integrations.google_workspace import (
    GoogleCalendarAPI,
    GoogleCloudAPI,
    GoogleDocsAPI,
    GoogleDriveAPI,
    GoogleGmailAPI,
    GoogleSheetsAPI,
    GoogleSlidesAPI,
)
from app.integrations.oauth import (
    OAUTH_PROVIDERS,
    build_authorization_url,
    exchange_oauth_code,
    generate_pkce_pair,
    refresh_oauth_token,
    revoke_oauth_token,
)
from app.integrations.supabase import SupabaseClient
from app.integrations.vercel import VercelClient

SUPPORTED_MANAGED_PROVIDERS: dict[str, dict[str, Any]] = {
    "gemini": {"auth_types": ["API_KEY"], "capabilities": ["model_discovery", "generate", "stream", "function_calling", "embeddings", "multimodal"]},
    "supabase": {"auth_types": ["API_KEY"], "capabilities": ["postgres", "postgrest", "storage", "pgvector", "rls"]},
    "vercel": {"auth_types": ["API_KEY"], "capabilities": ["projects", "deployments", "build_logs", "domains", "env_metadata", "webhooks"]},
    "cloudflare": {"auth_types": ["API_KEY"], "capabilities": ["dns", "workers", "kv", "r2", "security_settings"]},
    "github": {"auth_types": ["OAUTH2", "API_KEY"], "capabilities": ["repos", "branches", "commits", "files", "pull_requests", "issues", "workflows", "releases"]},
    "google_drive": {"auth_types": ["OAUTH2"], "capabilities": ["search_files", "read_documents", "create_folders", "upload_files"]},
    "google_gmail": {"auth_types": ["OAUTH2"], "capabilities": ["search_messages", "read_threads", "drafts", "send_requires_approval", "labels"]},
    "google_calendar": {"auth_types": ["OAUTH2"], "capabilities": ["list_calendars", "search_events", "create_events", "update_events", "freebusy"]},
    "google_docs": {"auth_types": ["OAUTH2"], "capabilities": ["create_document", "read_document", "edit_document"]},
    "google_sheets": {"auth_types": ["OAUTH2"], "capabilities": ["create_spreadsheet", "read_values", "write_values"]},
    "google_slides": {"auth_types": ["OAUTH2"], "capabilities": ["create_presentation", "read_presentation", "add_slides"]},
    "google_cloud": {"auth_types": ["OAUTH2", "SERVICE_ACCOUNT"], "capabilities": ["list_projects", "list_enabled_services", "resource_inspection"]},
    "google_search": {"auth_types": ["API_KEY"], "capabilities": ["web_search", "citations"]},
}


def _cred_aad(tenant_id: str, provider: str) -> str:
    return f"ultron-integration::{tenant_id}::{provider}"


def _encrypt_credentials(payload: dict[str, Any], *, tenant_id: str, provider: str, settings: Settings) -> tuple[str, str]:
    return encrypt_vault_secret(
        json.dumps(payload),
        master_secret=settings.vault_master_key.get_secret_value(),
        aad=_cred_aad(tenant_id, provider),
    )


def _decrypt_credentials(record: IntegrationConnectionRecord, settings: Settings) -> dict[str, Any]:
    if not record.encrypted_credentials_b64 or not record.credentials_nonce_b64:
        return {}
    raw = decrypt_vault_secret(
        record.encrypted_credentials_b64,
        record.credentials_nonce_b64,
        master_secret=settings.vault_master_key.get_secret_value(),
        aad=_cred_aad(record.tenant_id, record.provider),
    )
    return json.loads(raw)


def _validate_provider(provider: str) -> str:
    p = provider.strip().lower()
    if p not in SUPPORTED_MANAGED_PROVIDERS:
        raise ValidationError(f"Unsupported integration provider '{provider}'.")
    return p


def connect_with_credentials(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    credentials: dict[str, Any],
    auth_type: str = "API_KEY",
    scopes: list[str] | None = None,
    account_label: str = "",
    expires_in_seconds: int | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Store AES-256-GCM encrypted provider credentials (status stays IMPLEMENTED_NOT_LIVE until live verification passes)."""
    p = _validate_provider(provider)
    if not credentials:
        raise ValidationError("credentials payload cannot be empty.")

    ct, nonce = _encrypt_credentials(credentials, tenant_id=principal.tenant_id, provider=p, settings=settings)
    now = datetime.now(timezone.utc)
    token_exp = now + timedelta(seconds=expires_in_seconds) if expires_in_seconds else None

    existing = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == p,
        )
    ).scalar_one_or_none()

    caps = SUPPORTED_MANAGED_PROVIDERS[p]["capabilities"]
    if existing is not None:
        existing.auth_type = auth_type.upper()
        existing.encrypted_credentials_b64 = ct
        existing.credentials_nonce_b64 = nonce
        existing.scopes_json = json.dumps(scopes or [])
        existing.capabilities_json = json.dumps(caps)
        existing.status = "IMPLEMENTED_NOT_LIVE"
        existing.account_label = account_label.strip()
        existing.token_expires_at = token_exp
        existing.last_error = None
        existing.disconnected_at = None
        existing.connected_by = principal.username
        existing.updated_at = now
        rec = existing
    else:
        rec = IntegrationConnectionRecord(
            connection_id=f"icn_{uuid.uuid4().hex[:16]}",
            tenant_id=principal.tenant_id,
            provider=p,
            auth_type=auth_type.upper(),
            encrypted_credentials_b64=ct,
            credentials_nonce_b64=nonce,
            scopes_json=json.dumps(scopes or []),
            capabilities_json=json.dumps(caps),
            status="IMPLEMENTED_NOT_LIVE",
            account_label=account_label.strip(),
            token_expires_at=token_exp,
            connected_by=principal.username,
        )
        db.add(rec)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="INTEGRATION_CONNECTED",
        resource=p,
        outcome=f"AUTH={auth_type.upper()}|AWAITING_LIVE_VERIFY",
    )
    db.commit()
    db.refresh(rec)
    return serialize_connection(rec)


def start_oauth_flow(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    scopes: list[str] | None = None,
    redirect_uri: str | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Initiate OAuth 2.0 + PKCE (S256) flow and persist a single-use CSRF state record."""
    p = _validate_provider(provider)
    if p not in OAUTH_PROVIDERS:
        raise ValidationError(f"Provider '{p}' does not support OAuth 2.0 flow.")

    verifier, challenge = generate_pkce_pair()
    state_token = f"ost_{secrets.token_urlsafe(32)}"
    auth_url, effective_scopes, effective_redirect = build_authorization_url(
        provider=p,
        state_token=state_token,
        code_challenge=challenge,
        scopes=scopes,
        redirect_uri=redirect_uri,
        settings=settings,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.add(
        OAuthStateRecord(
            state_token=state_token,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            provider=p,
            code_verifier=verifier,
            redirect_uri=effective_redirect,
            scopes_json=json.dumps(effective_scopes),
            consumed=False,
            expires_at=expires_at,
        )
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="OAUTH_FLOW_STARTED",
        resource=p,
        outcome=f"SCOPES={len(effective_scopes)}",
    )
    db.commit()
    return {
        "provider": p,
        "state": state_token,
        "authorization_url": auth_url,
        "scopes": effective_scopes,
        "expires_at": expires_at.isoformat(),
    }


def complete_oauth_callback(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    code: str,
    state: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate single-use OAuth state, exchange authorization code with PKCE verifier, and store encrypted tokens."""
    p = _validate_provider(provider)
    st = db.execute(
        select(OAuthStateRecord).where(
            OAuthStateRecord.state_token == state,
            OAuthStateRecord.tenant_id == principal.tenant_id,
            OAuthStateRecord.provider == p,
        )
    ).scalar_one_or_none()
    if st is None or st.consumed:
        raise ConflictError("Invalid or already consumed OAuth state token.")

    now = datetime.now(timezone.utc)
    exp = st.expires_at if st.expires_at.tzinfo else st.expires_at.replace(tzinfo=timezone.utc)
    if now >= exp:
        raise ConflictError("OAuth state token has expired.")

    token_data = exchange_oauth_code(
        provider=p,
        code=code,
        code_verifier=st.code_verifier,
        redirect_uri=st.redirect_uri,
        settings=settings,
        http_client=http_client,
    )
    st.consumed = True
    granted_scopes = (
        token_data.get("scope", "").split()
        if isinstance(token_data.get("scope"), str) and token_data.get("scope")
        else json.loads(st.scopes_json or "[]")
    )
    creds = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "token_type": token_data.get("token_type", "Bearer"),
    }
    return connect_with_credentials(
        db,
        principal=principal,
        provider=p,
        credentials=creds,
        auth_type="OAUTH2",
        scopes=granted_scopes,
        expires_in_seconds=int(token_data.get("expires_in", 3600)) if token_data.get("expires_in") else None,
        settings=settings,
    )


def refresh_connection_token(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Refresh an encrypted OAuth 2.0 connection using its stored refresh token."""
    p = _validate_provider(provider)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == p,
        )
    ).scalar_one_or_none()
    if rec is None or rec.disconnected_at is not None:
        raise NotFoundError(f"No active connection found for '{p}'.")

    creds = _decrypt_credentials(rec, settings)
    rt = creds.get("refresh_token", "").strip()
    if not rt:
        raise ConflictError(f"Connection '{p}' has no stored refresh_token.")

    refreshed = refresh_oauth_token(provider=p, refresh_token=rt, settings=settings, http_client=http_client)
    creds["access_token"] = refreshed["access_token"]
    if refreshed.get("refresh_token"):
        creds["refresh_token"] = refreshed["refresh_token"]

    ct, nonce = _encrypt_credentials(creds, tenant_id=principal.tenant_id, provider=p, settings=settings)
    now = datetime.now(timezone.utc)
    rec.encrypted_credentials_b64 = ct
    rec.credentials_nonce_b64 = nonce
    if refreshed.get("expires_in"):
        rec.token_expires_at = now + timedelta(seconds=int(refreshed["expires_in"]))
    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="INTEGRATION_TOKEN_REFRESHED",
        resource=p,
        outcome="SUCCESS",
    )
    db.commit()
    db.refresh(rec)
    return serialize_connection(rec)


def disconnect_connection(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Revoke upstream OAuth token where supported and zero out stored encrypted credentials."""
    p = _validate_provider(provider)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == p,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"No connection record found for '{p}'.")

    upstream_revoked = False
    if rec.auth_type == "OAUTH2" and rec.encrypted_credentials_b64:
        creds = _decrypt_credentials(rec, settings)
        token_to_revoke = creds.get("refresh_token") or creds.get("access_token") or ""
        upstream_revoked = revoke_oauth_token(provider=p, token=token_to_revoke, http_client=http_client)

    now = datetime.now(timezone.utc)
    rec.encrypted_credentials_b64 = ""
    rec.credentials_nonce_b64 = ""
    rec.status = "REQUIRES_CONFIGURATION"
    rec.disconnected_at = now
    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="INTEGRATION_DISCONNECTED",
        resource=p,
        outcome=f"UPSTREAM_REVOKED={upstream_revoked}",
    )
    db.commit()
    db.refresh(rec)
    out = serialize_connection(rec)
    out["upstream_revoked"] = upstream_revoked
    return out


def resolve_provider_token(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    settings: Settings,
) -> str | None:
    """Resolve decrypted token from tenant DB connection first, then server env fallback."""
    p = provider.strip().lower()
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tenant_id,
            IntegrationConnectionRecord.provider == p,
            IntegrationConnectionRecord.disconnected_at.is_(None),
        )
    ).scalar_one_or_none()
    if rec is not None and rec.encrypted_credentials_b64:
        creds = _decrypt_credentials(rec, settings)
        tok = creds.get("access_token") or creds.get("api_key") or creds.get("token") or ""
        if tok.strip():
            return tok.strip()

    env_map = {
        "gemini": settings.gemini_api_key,
        "github": settings.github_token,
        "vercel": settings.vercel_token,
        "cloudflare": settings.cloudflare_api_token,
        "supabase": settings.supabase_service_role_key or settings.supabase_anon_key,
        "google_drive": settings.google_drive_access_token,
        "google_gmail": settings.google_gmail_access_token,
        "google_calendar": settings.google_calendar_access_token,
        "google_docs": settings.google_docs_access_token,
        "google_sheets": settings.google_sheets_access_token,
        "google_slides": settings.google_slides_access_token,
        "google_cloud": settings.google_cloud_access_token,
        "google_search": settings.google_search_api_key,
    }
    secret = env_map.get(p)
    return secret.get_secret_value().strip() if secret and secret.get_secret_value().strip() else None


def verify_provider_live(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Run live verification for a specific managed provider and update DB connection status honestly."""
    p = _validate_provider(provider)
    token = resolve_provider_token(db, tenant_id=principal.tenant_id, provider=p, settings=settings)

    if p == "gemini":
        st = GeminiClient(settings, http_client=http_client, api_key_override=token).verify_live()
    elif p == "supabase":
        st = SupabaseClient(settings, http_client=http_client).verify_live()
    elif p == "vercel":
        st = VercelClient(settings, http_client=http_client, token_override=token).verify_live()
    elif p == "cloudflare":
        st = CloudflareClient(settings, http_client=http_client, token_override=token).verify_live()
    elif p == "github":
        st = GitHubEngineeringClient(settings, token_override=token, http_client=http_client).verify_live()
    elif p == "google_drive":
        st = GoogleDriveAPI(token, http_client=http_client).verify_live()
    elif p == "google_gmail":
        st = GoogleGmailAPI(token, http_client=http_client).verify_live()
    elif p == "google_calendar":
        st = GoogleCalendarAPI(token, http_client=http_client).verify_live()
    elif p == "google_docs":
        st = GoogleDocsAPI(token, http_client=http_client).verify_live()
    elif p == "google_sheets":
        st = GoogleSheetsAPI(token, http_client=http_client).verify_live()
    elif p == "google_slides":
        st = GoogleSlidesAPI(token, http_client=http_client).verify_live()
    elif p == "google_cloud":
        st = GoogleCloudAPI(token, http_client=http_client).verify_live()
    else:
        raise ValidationError(f"No live verifier registered for '{p}'.")

    now = datetime.now(timezone.utc)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == p,
        )
    ).scalar_one_or_none()
    if rec is not None:
        rec.status = "AVAILABLE" if st.live_verified else ("DEGRADED" if st.configured else "REQUIRES_CONFIGURATION")
        rec.last_verified_at = now if st.live_verified else rec.last_verified_at
        rec.last_error = None if st.live_verified else st.detail
        rec.updated_at = now
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="INTEGRATION_VERIFIED",
            resource=p,
            outcome=rec.status,
        )
        db.commit()

    return st.to_dict()


def list_connections(db: Session, *, tenant_id: str, settings: Settings) -> dict[str, Any]:
    """Return full tenant integration inventory combining stored connections + env configuration + Antigravity adapter."""
    rows = db.execute(
        select(IntegrationConnectionRecord)
        .where(IntegrationConnectionRecord.tenant_id == tenant_id)
        .order_by(IntegrationConnectionRecord.provider.asc())
    ).scalars().all()
    by_provider = {r.provider: serialize_connection(r) for r in rows}

    catalog: list[dict[str, Any]] = []
    for provider, meta in SUPPORTED_MANAGED_PROVIDERS.items():
        stored = by_provider.get(provider)
        env_tok = resolve_provider_token(db, tenant_id=tenant_id, provider=provider, settings=settings)
        if stored is not None:
            catalog.append(stored)
        else:
            catalog.append(
                {
                    "connection_id": None,
                    "provider": provider,
                    "auth_type": meta["auth_types"][0],
                    "supported_auth_types": meta["auth_types"],
                    "scopes": [],
                    "capabilities": meta["capabilities"],
                    "status": "IMPLEMENTED_NOT_LIVE" if env_tok else "REQUIRES_CONFIGURATION",
                    "configured_via_env": bool(env_tok),
                    "last_verified_at": None,
                    "last_error": None,
                }
            )

    return {
        "tenant_id": tenant_id,
        "total_managed_providers": len(catalog),
        "available_count": sum(1 for c in catalog if c["status"] == "AVAILABLE"),
        "connections": catalog,
        "antigravity_environment": inspect_antigravity_environment(run_live_auth_checks=False),
    }


def serialize_connection(r: IntegrationConnectionRecord) -> dict[str, Any]:
    """Serialize metadata only — NEVER returns encrypted or decrypted credentials."""
    return {
        "connection_id": r.connection_id,
        "tenant_id": r.tenant_id,
        "provider": r.provider,
        "auth_type": r.auth_type,
        "scopes": json.loads(r.scopes_json or "[]"),
        "capabilities": json.loads(r.capabilities_json or "[]"),
        "status": r.status,
        "account_label": r.account_label,
        "connected_by": r.connected_by,
        "token_expires_at": r.token_expires_at.isoformat() if r.token_expires_at else None,
        "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
        "last_error": r.last_error,
        "disconnected_at": r.disconnected_at.isoformat() if r.disconnected_at else None,
        "updated_at": r.updated_at.isoformat(),
    }
