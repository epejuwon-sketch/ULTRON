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
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal, Role
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
    validate_oauth_redirect_uri,
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
    "uba_verve": {
        "auth_types": ["OAUTH2_CLIENT_CREDENTIALS", "API_KEY"],
        "capabilities": [
            "CARD_DISPLAY",
            "CARD_PAYMENT",
            "ACCOUNT_BALANCE",
            "ACCOUNT_TRANSACTIONS",
            "CARD_AUTHORIZATION",
        ],
    },
    "flutterwave": {
        "auth_types": ["API_KEY"],
        "capabilities": [
            "hosted_checkout",
            "ngn_verve_checkout",
            "webhook_verif_hash",
            "transaction_verify",
        ],
    },
    "caravan": {
        "auth_types": ["API_KEY"],
        "capabilities": [
            "funding_research",
            "eligibility_assessment",
            "bi_analytics",
            "neon_intelligence",
            "argon_orchestration",
        ],
    },
    "openai": {"auth_types": ["API_KEY"], "capabilities": ["models", "chat_completions", "embeddings"]},
    "anthropic": {"auth_types": ["API_KEY"], "capabilities": ["models", "messages"]},
    "ollama": {"auth_types": ["API_KEY"], "capabilities": ["local_models", "inference"]},
    "gitlab": {"auth_types": ["PAT", "API_KEY"], "capabilities": ["repos", "merge_requests", "issues", "pipelines"]},
    "bitbucket": {"auth_types": ["PAT", "API_KEY"], "capabilities": ["repos", "pull_requests", "commits"]},
    "whatsapp": {"auth_types": ["API_KEY"], "capabilities": ["send_message_requires_approval", "webhook_receive"]},
    "email_smtp": {"auth_types": ["API_KEY"], "capabilities": ["drafts", "send_requires_approval"]},
    "telegram": {"auth_types": ["API_KEY"], "capabilities": ["bot_updates", "send_message_requires_approval"]},
    "slack": {"auth_types": ["API_KEY", "OAUTH2"], "capabilities": ["channels", "post_message_requires_approval"]},
    "discord": {"auth_types": ["API_KEY"], "capabilities": ["guilds", "send_message_requires_approval"]},
    "notion": {"auth_types": ["API_KEY"], "capabilities": ["search", "pages", "databases"]},
    "linear": {"auth_types": ["API_KEY"], "capabilities": ["issues", "projects", "cycles"]},
    "trello": {"auth_types": ["API_KEY"], "capabilities": ["boards", "lists", "cards"]},
    "asana": {"auth_types": ["PAT", "API_KEY"], "capabilities": ["workspaces", "projects", "tasks"]},
    "jira": {"auth_types": ["API_KEY"], "capabilities": ["projects", "issues", "search"]},
    "postgresql": {"auth_types": ["API_KEY"], "capabilities": ["sql_query", "rls", "migrations"]},
    "redis": {"auth_types": ["API_KEY"], "capabilities": ["rate_limiting", "cache"]},
    "stripe": {"auth_types": ["API_KEY"], "capabilities": ["balance_read", "checkout_requires_approval"]},
    "paystack": {"auth_types": ["API_KEY"], "capabilities": ["banks_read", "checkout_requires_approval"]},
    "spotify": {"auth_types": ["API_KEY", "OAUTH2"], "capabilities": ["profile_read", "playback_control"]},
    "image_gen": {"auth_types": ["API_KEY"], "capabilities": ["image_generation"]},
    "webhooks": {"auth_types": ["WEBHOOK"], "capabilities": ["hmac_sha256", "delivery_logs"]},
    "rest_apis": {"auth_types": ["API_KEY"], "capabilities": ["ssrf_guarded_http"]},
    "mcp": {"auth_types": ["API_KEY"], "capabilities": ["stdio_allowlisted", "streamable_http"]},
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


def _oauth_app_provider_key(family: str) -> str:
    fam = family.strip().lower()
    if fam not in {"google", "github"}:
        raise ValidationError(f"Unsupported OAuth app family '{family}'.")
    return f"_oauth_app_{fam}"


def _load_vault_oauth_app_credentials(
    db: Session,
    *,
    tenant_id: str,
    family: str,
    settings: Settings,
) -> tuple[str, str, str] | None:
    pkey = _oauth_app_provider_key(family)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tenant_id,
            IntegrationConnectionRecord.provider == pkey,
        )
    ).scalar_one_or_none()
    if rec is None or rec.disconnected_at is not None or not rec.encrypted_credentials_b64:
        return None
    data = _decrypt_credentials(rec, settings)
    cid = str(data.get("client_id") or "").strip()
    csec = str(data.get("client_secret") or "").strip()
    ruri = str(data.get("redirect_uri") or "").strip()
    if not cid or not csec:
        return None
    return cid, csec, ruri


def configure_oauth_app_credentials(
    db: Session,
    *,
    principal: Principal,
    family: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    settings: Settings,
) -> dict[str, Any]:
    """Administrator-only setup of OAuth Client ID and Client Secret encrypted in VAULT."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may configure OAuth client credentials.")
    pkey = _oauth_app_provider_key(family)
    fam = family.strip().lower()
    cid = (client_id or "").strip()
    csec = (client_secret or "").strip()
    placeholders = {"undefined", "null", "changeme", "your_client_id", "your_client_secret"}
    if (
        len(cid) < 8
        or len(csec) < 8
        or any(ch.isspace() for ch in cid)
        or any(ch.isspace() for ch in csec)
        or cid.lower() in placeholders
        or csec.lower() in placeholders
    ):
        if fam == "google":
            raise ValidationError(
                "Both GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required (minimum 8 characters, no whitespace)."
            )
        raise ValidationError("Valid OAuth Client ID and Client Secret are required (minimum 8 characters, no whitespace).")
    clean_redirect = validate_oauth_redirect_uri(redirect_uri)

    payload = {"client_id": cid, "client_secret": csec, "redirect_uri": clean_redirect}
    ct, nonce = _encrypt_credentials(payload, tenant_id=principal.tenant_id, provider=pkey, settings=settings)
    now = datetime.now(timezone.utc)
    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == pkey,
        )
    ).scalar_one_or_none()
    masked_id = f"...{cid[-6:]}" if len(cid) > 6 else "***"
    if rec is None:
        rec = IntegrationConnectionRecord(
            connection_id=f"oapp_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            provider=pkey,
            auth_type="OAUTH_APP",
            encrypted_credentials_b64=ct,
            credentials_nonce_b64=nonce,
            scopes_json="[]",
            capabilities_json="[]",
            status="CONFIGURED",
            account_label=masked_id,
            connected_by=principal.username,
        )
        db.add(rec)
    else:
        rec.encrypted_credentials_b64 = ct
        rec.credentials_nonce_b64 = nonce
        rec.status = "CONFIGURED"
        rec.account_label = masked_id
        rec.disconnected_at = None
        rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="OAUTH_APP_CONFIGURED",
        resource=fam,
        outcome=f"VAULT_ENCRYPTED|CLIENT_ID={masked_id}",
    )
    db.commit()
    return {
        "family": fam,
        "configured": True,
        "source": "vault",
        "client_id_masked": masked_id,
        "redirect_uri": clean_redirect,
    }


def _oauth_family_requirements(family: str) -> dict[str, Any]:
    if family == "google":
        return {
            "authorized_redirect_path": "/oauth/callback",
            "required_env_vars": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"],
            "required_google_apis": [
                "Google Drive API",
                "Gmail API",
                "Google Calendar API",
                "Google Docs API",
                "Google Sheets API",
                "Google Slides API",
                "Cloud Resource Manager API",
            ],
            "applies_to_providers": [
                "google_drive",
                "google_gmail",
                "google_calendar",
                "google_docs",
                "google_sheets",
                "google_slides",
                "google_cloud",
            ],
        }
    return {
        "authorized_redirect_path": "/oauth/callback",
        "required_env_vars": ["GITHUB_OAUTH_CLIENT_ID", "GITHUB_OAUTH_CLIENT_SECRET"],
        "applies_to_providers": ["github"],
    }


def get_oauth_app_status(
    db: Session,
    *,
    tenant_id: str,
    family: str,
    settings: Settings,
) -> dict[str, Any]:
    fam = family.strip().lower()
    if fam not in {"google", "github"}:
        raise ValidationError(f"Unsupported OAuth app family '{family}'.")
    reqs = _oauth_family_requirements(fam)
    google_sec = settings.google_oauth_client_secret.get_secret_value().strip() if settings.google_oauth_client_secret else ""
    if fam == "google" and settings.google_oauth_client_id.strip() and google_sec:
        cid = settings.google_oauth_client_id.strip()
        return {
            "family": fam,
            "configured": True,
            "source": "env",
            "client_id_masked": f"...{cid[-6:]}" if len(cid) > 6 else "***",
            "redirect_uri": settings.google_oauth_redirect_uri,
            "requirements": reqs,
        }
    github_sec = settings.github_oauth_client_secret.get_secret_value().strip() if settings.github_oauth_client_secret else ""
    if fam == "github" and settings.github_oauth_client_id.strip() and github_sec:
        cid = settings.github_oauth_client_id.strip()
        return {
            "family": fam,
            "configured": True,
            "source": "env",
            "client_id_masked": f"...{cid[-6:]}" if len(cid) > 6 else "***",
            "redirect_uri": settings.github_oauth_redirect_uri,
            "requirements": reqs,
        }
    vault = _load_vault_oauth_app_credentials(db, tenant_id=tenant_id, family=fam, settings=settings)
    if vault:
        cid, _csec, ruri = vault
        return {
            "family": fam,
            "configured": True,
            "source": "vault",
            "client_id_masked": f"...{cid[-6:]}" if len(cid) > 6 else "***",
            "redirect_uri": ruri,
            "requirements": reqs,
        }
    return {
        "family": fam,
        "configured": False,
        "source": "none",
        "client_id_masked": None,
        "redirect_uri": None,
        "requirements": reqs,
    }


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
    spec = OAUTH_PROVIDERS.get(p)
    if spec is None:
        raise ValidationError(f"Provider '{p}' does not support OAuth 2.0 flow.")

    vault_creds = _load_vault_oauth_app_credentials(db, tenant_id=principal.tenant_id, family=spec.family, settings=settings)
    verifier, challenge = generate_pkce_pair()
    state_token = f"ost_{secrets.token_urlsafe(32)}"
    auth_url, effective_scopes, effective_redirect = build_authorization_url(
        provider=p,
        state_token=state_token,
        code_challenge=challenge,
        scopes=scopes,
        redirect_uri=redirect_uri,
        settings=settings,
        vault_creds=vault_creds,
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
    redirect_uri: str | None = None,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate single-use OAuth state, exchange authorization code with PKCE verifier, and store encrypted tokens."""
    p = _validate_provider(provider)
    st = db.execute(
        select(OAuthStateRecord).where(
            OAuthStateRecord.state_token == state,
            OAuthStateRecord.tenant_id == principal.tenant_id,
            OAuthStateRecord.user_id == principal.user_id,
            OAuthStateRecord.provider == p,
        )
    ).scalar_one_or_none()
    if st is None or st.consumed:
        raise ConflictError("Invalid or already consumed OAuth state token.")

    if redirect_uri is not None and redirect_uri.strip() != st.redirect_uri:
        raise ConflictError("OAuth redirect_uri does not match the authorization session.")

    now = datetime.now(timezone.utc)
    exp = st.expires_at if st.expires_at.tzinfo else st.expires_at.replace(tzinfo=timezone.utc)
    if now >= exp:
        raise ConflictError("OAuth state token has expired.")

    spec = OAUTH_PROVIDERS[p]
    vault_creds = _load_vault_oauth_app_credentials(db, tenant_id=principal.tenant_id, family=spec.family, settings=settings)
    token_data = exchange_oauth_code(
        provider=p,
        code=code,
        code_verifier=st.code_verifier,
        redirect_uri=st.redirect_uri,
        settings=settings,
        vault_creds=vault_creds,
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
    account_label = _fetch_oauth_account_identity(
        provider=p,
        access_token=creds["access_token"],
        http_client=http_client,
    )
    saved = connect_with_credentials(
        db,
        principal=principal,
        provider=p,
        credentials=creds,
        auth_type="OAUTH2",
        scopes=granted_scopes,
        account_label=account_label,
        expires_in_seconds=int(token_data.get("expires_in", 3600)) if token_data.get("expires_in") else None,
        settings=settings,
    )
    try:
        verified = verify_provider_live(
            db,
            principal=principal,
            provider=p,
            settings=settings,
            http_client=http_client,
        )
        return verified
    except Exception:
        return saved


def _fetch_oauth_account_identity(
    *,
    provider: str,
    access_token: str,
    http_client: httpx.Client | None = None,
) -> str:
    """Best-effort retrieval of authorized account email/username; never fails OAuth callback."""
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None or not access_token:
        return ""
    close_client = http_client is None
    client = http_client or httpx.Client(timeout=6.0)
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        if spec.family == "google":
            resp = client.get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("email") or data.get("name") or "")[:200]
        elif spec.family == "github":
            resp = client.get("https://api.github.com/user", headers={**headers, "Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("login") or data.get("email") or "")[:200]
    except Exception:
        return ""
    finally:
        if close_client:
            client.close()
    return ""


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

    spec = OAUTH_PROVIDERS.get(p)
    vault_creds = (
        _load_vault_oauth_app_credentials(db, tenant_id=principal.tenant_id, family=spec.family, settings=settings)
        if spec
        else None
    )
    refreshed = refresh_oauth_token(
        provider=p,
        refresh_token=rt,
        settings=settings,
        vault_creds=vault_creds,
        http_client=http_client,
    )
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
        from app.integrations.ecosystem_adapters import verify_ecosystem_provider

        rec_creds = db.execute(
            select(IntegrationConnectionRecord).where(
                IntegrationConnectionRecord.tenant_id == principal.tenant_id,
                IntegrationConnectionRecord.provider == p,
                IntegrationConnectionRecord.disconnected_at.is_(None),
            )
        ).scalar_one_or_none()
        creds_dict = _decrypt_credentials(rec_creds, settings) if rec_creds is not None else {}
        st = verify_ecosystem_provider(
            provider=p,
            creds=creds_dict,
            env_token=token,
            settings=settings,
            http_client=http_client,
        )

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


def _compute_lifecycle_stage(
    *,
    status: str,
    has_connection: bool,
    configured_via_env: bool,
    token_expired: bool,
) -> str:
    if token_expired:
        return "EXPIRED"
    st = (status or "").upper()
    if st == "AVAILABLE":
        return "LIVE_VERIFIED"
    if has_connection and st in {"IMPLEMENTED_NOT_LIVE", "DEGRADED", "AUTHENTICATED"}:
        return "AUTHENTICATED"
    if configured_via_env or st == "DEGRADED":
        return "CONFIGURED"
    return "SUPPORTED"


def list_connections(db: Session, *, tenant_id: str, settings: Settings) -> dict[str, Any]:
    """Return full tenant integration inventory combining stored connections + env configuration + Antigravity adapter."""
    rows = db.execute(
        select(IntegrationConnectionRecord)
        .where(IntegrationConnectionRecord.tenant_id == tenant_id)
        .order_by(IntegrationConnectionRecord.provider.asc())
    ).scalars().all()
    by_provider = {r.provider: serialize_connection(r) for r in rows}

    google_app_status = get_oauth_app_status(db, tenant_id=tenant_id, family="google", settings=settings)
    github_app_status = get_oauth_app_status(db, tenant_id=tenant_id, family="github", settings=settings)
    google_oauth_ready = bool(google_app_status["configured"])
    github_oauth_ready = bool(github_app_status["configured"])

    catalog: list[dict[str, Any]] = []
    for provider, meta in SUPPORTED_MANAGED_PROVIDERS.items():
        stored = by_provider.get(provider)
        env_tok = resolve_provider_token(db, tenant_id=tenant_id, provider=provider, settings=settings)
        oauth_spec = OAUTH_PROVIDERS.get(provider)
        oauth_ready = (
            google_oauth_ready
            if (oauth_spec and oauth_spec.family == "google")
            else github_oauth_ready
            if (oauth_spec and oauth_spec.family == "github")
            else False
        )
        if stored is not None:
            stored["configured_via_env"] = bool(env_tok)
            stored["oauth_client_configured"] = oauth_ready
            if stored.get("lifecycle_stage") == "SUPPORTED" and (env_tok or oauth_ready):
                stored["lifecycle_stage"] = "CONFIGURED"
            catalog.append(stored)
        else:
            is_configured = bool(env_tok or oauth_ready)
            catalog.append(
                {
                    "connection_id": None,
                    "provider": provider,
                    "auth_type": meta["auth_types"][0],
                    "supported_auth_types": meta["auth_types"],
                    "scopes": [],
                    "capabilities": meta["capabilities"],
                    "status": "IMPLEMENTED_NOT_LIVE" if env_tok else "REQUIRES_CONFIGURATION",
                    "lifecycle_stage": "CONFIGURED" if is_configured else "SUPPORTED",
                    "configured_via_env": bool(env_tok),
                    "oauth_client_configured": oauth_ready,
                    "token_expired": False,
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
    now = datetime.now(timezone.utc)
    exp = r.token_expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    token_expired = bool(exp is not None and now >= exp and r.disconnected_at is None)
    has_active_creds = bool(r.encrypted_credentials_b64 and r.disconnected_at is None)
    lifecycle_stage = _compute_lifecycle_stage(
        status=r.status,
        has_connection=has_active_creds,
        configured_via_env=False,
        token_expired=token_expired,
    )
    return {
        "connection_id": r.connection_id,
        "tenant_id": r.tenant_id,
        "provider": r.provider,
        "auth_type": r.auth_type,
        "scopes": json.loads(r.scopes_json or "[]"),
        "capabilities": json.loads(r.capabilities_json or "[]"),
        "status": r.status,
        "lifecycle_stage": lifecycle_stage,
        "token_expired": token_expired,
        "account_label": r.account_label,
        "connected_by": r.connected_by,
        "token_expires_at": r.token_expires_at.isoformat() if r.token_expires_at else None,
        "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
        "last_error": r.last_error,
        "disconnected_at": r.disconnected_at.isoformat() if r.disconnected_at else None,
        "updated_at": r.updated_at.isoformat(),
    }


def get_caravan_readiness_gate(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Evaluate Caravan core infrastructure readiness and screen-sharing policy from real backend state."""
    listing = list_connections(db, tenant_id=tenant_id, settings=settings)
    by_provider = {c["provider"]: c for c in listing["connections"]}

    def _gate_entry(provider: str) -> dict[str, Any]:
        c = by_provider.get(provider) or {}
        stage = c.get("lifecycle_stage") or "SUPPORTED"
        authenticated = stage in {"AUTHENTICATED", "CONNECTED", "LIVE_VERIFIED"}
        live_verified = stage == "LIVE_VERIFIED"
        return {
            "provider": provider,
            "lifecycle_stage": stage,
            "configured": bool(c.get("configured_via_env") or c.get("oauth_client_configured") or c.get("connection_id")),
            "authenticated": authenticated,
            "live_verified": live_verified,
            "oauth_client_configured": bool(c.get("oauth_client_configured")),
            "last_verified_at": c.get("last_verified_at"),
            "last_error": c.get("last_error"),
        }

    core = {
        "github": _gate_entry("github"),
        "supabase": _gate_entry("supabase"),
        "vercel": _gate_entry("vercel"),
        "cloudflare": _gate_entry("cloudflare"),
    }
    vault_ok = bool(settings.vault_master_key and len(settings.vault_master_key.get_secret_value().strip()) >= 16)
    argon_ok = True  # ARGON tool execution gate enforces Integrations 2.0 + AEGIS policy checks

    blockers: list[str] = []
    for req_p in ("github", "supabase", "vercel"):
        info = core[req_p]
        if not info["authenticated"]:
            blockers.append(f"{req_p}: not authenticated ({info['lifecycle_stage']})")
        elif not info["live_verified"]:
            blockers.append(f"{req_p}: authenticated but not live verified")
    if not vault_ok:
        blockers.append("vault: master encryption key not configured")

    return {
        "tenant_id": tenant_id,
        "core_infrastructure_ready": len(blockers) == 0,
        "core_providers": core,
        "vault": {"encryption": "AES-256-GCM", "ready": vault_ok},
        "argon": {"permission_gate": "universal_connections_2.0", "ready": argon_ok},
        "outstanding_blockers": blockers,
        "screen_sharing_readiness": {
            "supported": True,
            "consent_required": True,
            "sensitive_field_masking": True,
            "oauth_consent_handoff": "browser_redirect_with_pkce_state",
            "never_expose": ["client_secret", "api_key", "refresh_token", "card_pin", "cvv", "otp"],
        },
    }

