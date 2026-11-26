"""ULTRON Universal Connections Centre 2.0 — Extensible Connector Registry, SSRF Guard, Webhooks & Governance."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    SecurityViolationError,
    ValidationError,
)
from app.core.permissions import Principal
from app.core.security import decrypt_vault_secret, encrypt_vault_secret
from app.db.models import (
    ConnectorScopeGrantRecord,
    IntegrationConnectionRecord,
    UniversalConnectorRecord,
    WebhookDeliveryRecord,
)
from app.db.repositories import append_audit_log
from app.services.integration_manager import (
    SUPPORTED_MANAGED_PROVIDERS,
    connect_with_credentials,
    disconnect_connection,
    list_connections,
)

UNIVERSAL_LIFECYCLE_STATES = frozenset({
    "DISCOVERED",
    "NOT_CONFIGURED",
    "CONFIGURATION_REQUIRED",
    "AWAITING_AUTHORIZATION",
    "AUTHENTICATED",
    "CONNECTED",
    "LIVE_VERIFIED",
    "DEGRADED",
    "EXPIRED",
    "REVOKED",
    "FAILED",
})

UNIVERSAL_CATEGORIES = [
    "Communication",
    "Email and calendars",
    "Social media",
    "Marketing",
    "Payments",
    "Banking",
    "Cloud storage",
    "Development tools",
    "Analytics",
    "CRM",
    "Productivity",
    "Business operations",
    "AI providers",
    "Custom websites and APIs",
]

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})


def validate_public_https_url(url: str, *, require_https: bool = False) -> str:
    """Validate URL format and block SSRF targets (loopback, private, link-local, metadata IPs)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if require_https and scheme != "https":
        raise SecurityViolationError("Only HTTPS URLs are permitted for this operation.")
    if scheme not in {"https", "http"}:
        raise SecurityViolationError(f"Disallowed URL scheme '{scheme}'. Only HTTP(S) is allowed.")
    host = (parsed.hostname or "").strip().lower()
    if not host or host in _BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost")):
        raise SecurityViolationError("Access to internal or local hostnames is blocked (SSRF protection).")

    # Check direct IP literal
    try:
        ip_obj = ipaddress.ip_address(host)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
            raise SecurityViolationError("Access to private, loopback, or link-local IP ranges is blocked (SSRF protection).")
    except ValueError:
        # Hostname: resolve DNS if possible and verify no private/link-local IP
        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos:
                addr = info[4][0]
                resolved_ip = ipaddress.ip_address(addr)
                if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local or resolved_ip.is_reserved:
                    raise SecurityViolationError("Target hostname resolves to a blocked internal IP range (SSRF protection).")
        except socket.gaierror:
            # Allow unresolvable synthetic hostnames in offline/sandbox tests while still blocking private literals
            pass

    return raw


def _slugify_provider(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug[:60] or f"custom_{uuid.uuid4().hex[:8]}"


def _webhook_aad(tenant_id: str, connector_id: str) -> str:
    return f"ultron-universal-webhook::{tenant_id}::{connector_id}"


def list_universal_catalogue(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
    query: str = "",
    category: str = "",
) -> dict[str, Any]:
    managed = list_connections(db, tenant_id=tenant_id, settings=settings)
    managed_by_key = {c["provider"]: c for c in managed.get("connections", [])}

    custom_rows = db.execute(
        select(UniversalConnectorRecord)
        .where(UniversalConnectorRecord.tenant_id == tenant_id)
        .order_by(UniversalConnectorRecord.updated_at.desc())
    ).scalars().all()

    items: list[dict[str, Any]] = []
    for key, meta in SUPPORTED_MANAGED_PROVIDERS.items():
        rec = managed_by_key.get(key)
        items.append({
            "connector_id": rec["connection_id"] if rec else f"builtin_{key}",
            "provider_key": key,
            "name": key.replace("_", " ").title(),
            "category": "AI providers" if key == "gemini" else ("Payments" if key == "flutterwave" else ("Banking" if key == "uba_verve" else "Development tools")),
            "connection_method": meta["auth_types"][0] if meta.get("auth_types") else "API_KEY",
            "lifecycle_state": rec["lifecycle_stage"] if rec else "NOT_CONFIGURED",
            "capabilities": meta.get("capabilities", []),
            "source": "BUILTIN_MANAGED",
            "last_verified_at": rec.get("last_verified_at") if rec else None,
        })

    for cr in custom_rows:
        items.append(_serialize_universal_connector(cr))

    q = query.strip().lower()
    cat = category.strip().lower()
    filtered = [
        it
        for it in items
        if (not q or q in it["name"].lower() or q in it["provider_key"].lower() or q in it["category"].lower())
        and (not cat or it["category"].lower() == cat)
    ]
    return {
        "total": len(filtered),
        "categories": UNIVERSAL_CATEGORIES,
        "lifecycle_states": sorted(UNIVERSAL_LIFECYCLE_STATES),
        "connectors": filtered,
    }


_ALLOWED_STDIO_COMMANDS = frozenset({"npx", "uvx", "node", "python", "python3", "docker"})
_STDIO_BAD_CHARS_RE = re.compile(r"[;|&`$<>\\\r\n\x00]")


def _validate_stdio_mcp_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if not cfg or not isinstance(cfg, dict):
        raise ValidationError("mcp_config with command and args is required for MCP_STDIO.")
    cmd = str(cfg.get("command") or "").strip()
    if cmd not in _ALLOWED_STDIO_COMMANDS:
        raise SecurityViolationError(
            f"MCP_STDIO command '{cmd}' is not in the safe allowlist ({', '.join(sorted(_ALLOWED_STDIO_COMMANDS))})."
        )
    args = cfg.get("args") or []
    if not isinstance(args, list):
        raise ValidationError("mcp_config.args must be a list of strings.")
    clean_args = []
    for a in args:
        s = str(a)
        if _STDIO_BAD_CHARS_RE.search(s):
            raise SecurityViolationError("MCP_STDIO args contain disallowed shell metacharacters.")
        clean_args.append(s)
    return {"command": cmd, "args": clean_args, "transport": "stdio"}


def register_universal_connector(
    db: Session,
    *,
    principal: Principal,
    name: str,
    category: str = "Custom websites and APIs",
    connection_method: str = "API_KEY",
    website_url: str = "",
    docs_url: str = "",
    api_base_url: str = "",
    required_headers: dict[str, str] | None = None,
    required_scopes: list[str] | None = None,
    capabilities: list[str] | None = None,
    credentials: dict[str, Any] | None = None,
    webhook_secret: str = "",
    subscribed_events: list[str] | None = None,
    mcp_config: dict[str, Any] | None = None,
    settings: Settings,
) -> dict[str, Any]:
    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise ValidationError("Service name is required.")
    method = connection_method.strip().upper()
    if method not in {"API_KEY", "OAUTH2", "WEBSITE", "WEBHOOK", "MCP_STDIO", "MCP_STREAMABLE_HTTP", "GOOGLE_ADC"}:
        raise ValidationError(
            "connection_method must be API_KEY, OAUTH2, WEBSITE, WEBHOOK, MCP_STDIO, MCP_STREAMABLE_HTTP, or GOOGLE_ADC."
        )

    safe_web = validate_public_https_url(website_url) if website_url else ""
    safe_docs = validate_public_https_url(docs_url) if docs_url else ""
    safe_api = validate_public_https_url(api_base_url) if api_base_url else ""

    validated_mcp: dict[str, Any] = {}
    if method == "MCP_STDIO":
        validated_mcp = _validate_stdio_mcp_config(mcp_config)
    elif method == "MCP_STREAMABLE_HTTP":
        if not safe_api:
            raise ValidationError("api_base_url is required for MCP_STREAMABLE_HTTP.")
        validated_mcp = {"endpoint": safe_api, "transport": "streamable_http"}

    provider_key = _slugify_provider(clean_name)
    connector_id = f"ucon_{uuid.uuid4().hex[:14]}"
    now = datetime.now(timezone.utc)

    # Determine honest initial lifecycle state (NEVER mark LIVE_VERIFIED merely because credentials were entered)
    if method == "API_KEY":
        has_secret = bool(credentials and any(str(v).strip() for v in credentials.values()))
        state = "AUTHENTICATED" if has_secret else "CONFIGURATION_REQUIRED"
    elif method == "OAUTH2":
        state = "AWAITING_AUTHORIZATION"
    elif method == "WEBSITE":
        state = "DISCOVERED" if safe_web else "NOT_CONFIGURED"
    elif method == "WEBHOOK":
        state = "CONNECTED" if webhook_secret.strip() else "CONFIGURATION_REQUIRED"
    elif method in {"MCP_STDIO", "MCP_STREAMABLE_HTTP"}:
        state = "CONFIGURATION_REQUIRED" if (method == "MCP_STREAMABLE_HTTP" and not safe_api) else "DISCOVERED"
    else:  # GOOGLE_ADC
        state = "AUTHENTICATED" if probe_google_adc()["adc_available"] else "CONFIGURATION_REQUIRED"

    enc_wh_b64 = None
    wh_nonce_b64 = None
    if webhook_secret.strip():
        enc_wh_b64, wh_nonce_b64 = encrypt_vault_secret(
            webhook_secret.strip(),
            master_secret=settings.vault_master_key.get_secret_value(),
            aad=_webhook_aad(principal.tenant_id, connector_id),
        )

    webhook_path = f"/api/v1/integrations/universal/webhooks/{connector_id}" if method == "WEBHOOK" else ""

    rec = UniversalConnectorRecord(
        connector_id=connector_id,
        tenant_id=principal.tenant_id,
        provider_key=provider_key,
        name=clean_name,
        category=(category or "Custom websites and APIs").strip()[:64],
        connection_method=method,
        lifecycle_state=state,
        website_url=safe_web,
        docs_url=safe_docs,
        api_base_url=safe_api,
        required_headers_json=json.dumps(required_headers or {}),
        required_scopes_json=json.dumps(required_scopes or []),
        capabilities_json=json.dumps(capabilities or []),
        discovered_auth_methods_json=json.dumps([method]),
        webhook_endpoint_path=webhook_path,
        encrypted_webhook_secret_b64=enc_wh_b64,
        webhook_secret_nonce_b64=wh_nonce_b64,
        subscribed_events_json=json.dumps(subscribed_events or []),
        mcp_config_json=json.dumps(validated_mcp),
        created_by=principal.username,
    )
    db.add(rec)

    # Store API_KEY credentials encrypted in VAULT via IntegrationConnectionRecord if provided
    if method == "API_KEY" and credentials:
        enc_creds, nonce = encrypt_vault_secret(
            json.dumps(credentials),
            master_secret=settings.vault_master_key.get_secret_value(),
            aad=f"ultron-integration::{principal.tenant_id}::{provider_key}",
        )
        ic = db.execute(
            select(IntegrationConnectionRecord).where(
                IntegrationConnectionRecord.tenant_id == principal.tenant_id,
                IntegrationConnectionRecord.provider == provider_key,
            )
        ).scalar_one_or_none()
        if ic is None:
            ic = IntegrationConnectionRecord(
                connection_id=f"con_{uuid.uuid4().hex[:14]}",
                tenant_id=principal.tenant_id,
                provider=provider_key,
                auth_type="API_KEY",
                status="AUTHENTICATED",
                scopes_json=json.dumps(required_scopes or []),
                encrypted_credentials_b64=enc_creds,
                credentials_nonce_b64=nonce,
                connected_by=principal.username,
            )
            db.add(ic)
        else:
            ic.encrypted_credentials_b64 = enc_creds
            ic.credentials_nonce_b64 = nonce
            ic.status = "AUTHENTICATED"
            ic.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_CONNECTOR_CREATED",
        resource=f"{connector_id}:{provider_key}",
        outcome=f"method={method}|state={state}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def inspect_website_integration(
    db: Session,
    *,
    principal: Principal,
    website_url: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Inspect a public website URL for official API docs & auth methods without treating URL as auth."""
    safe_url = validate_public_https_url(website_url)
    parsed = urlparse(safe_url)
    host = parsed.hostname or "service"
    name = host.replace("www.", "").split(".")[0].title()

    detected_methods: list[str] = []
    detected_docs: str = ""
    fetch_note = "Public inspection only — URL alone never grants authentication or private access."

    client = http_client or httpx.Client(timeout=6.0, follow_redirects=False)
    should_close = http_client is None
    try:
        resp = client.get(safe_url, headers={"User-Agent": "ULTRON-Universal-Inspector/2.0"})
        body = (resp.text or "")[:65536].lower()
        if "oauth" in body or "authorize" in body:
            detected_methods.append("OAUTH2")
        if "api key" in body or "x-api-key" in body or "bearer" in body:
            detected_methods.append("API_KEY")
        if "webhook" in body or "signing secret" in body:
            detected_methods.append("WEBHOOK")
        m_doc = re.search(r'href=["\'](https?://[^"\']*(?:docs|developer|api)[^"\']*)["\']', resp.text or "", re.I)
        if m_doc:
            try:
                detected_docs = validate_public_https_url(m_doc.group(1))
            except SecurityViolationError:
                detected_docs = ""
    except Exception as exc:
        fetch_note = f"Public fetch did not complete ({type(exc).__name__}); manual configuration required."
    finally:
        if should_close:
            client.close()

    if not detected_methods:
        detected_methods = ["API_KEY", "WEBHOOK"]

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_WEBSITE_INSPECTED",
        resource=safe_url[:160],
        outcome=f"methods={','.join(detected_methods)}",
    )
    db.commit()

    return {
        "name": name,
        "website_url": safe_url,
        "docs_url": detected_docs or safe_url,
        "detected_auth_methods": detected_methods,
        "lifecycle_state": "DISCOVERED",
        "authenticated": False,
        "note": fetch_note,
    }


def test_universal_connector(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    if rec.lifecycle_state == "REVOKED":
        raise ConflictError("Connector has been REVOKED and cannot be tested until re-authorized.")

    if not rec.api_base_url:
        rec.lifecycle_state = "CONFIGURATION_REQUIRED"
        rec.last_error = "No api_base_url configured for live probe."
        rec.updated_at = datetime.now(timezone.utc)
        db.commit()
        return _serialize_universal_connector(rec)

    safe_url = validate_public_https_url(rec.api_base_url)
    headers = {"Accept": "application/json", **json.loads(rec.required_headers_json or "{}")}

    # Inject VAULT credentials server-side only (never returned to caller)
    ic = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == rec.provider_key,
        )
    ).scalar_one_or_none()
    if ic and ic.encrypted_credentials_b64 and ic.credentials_nonce_b64:
        creds = json.loads(
            decrypt_vault_secret(
                ic.encrypted_credentials_b64,
                ic.credentials_nonce_b64,
                master_secret=settings.vault_master_key.get_secret_value(),
                aad=f"ultron-integration::{principal.tenant_id}::{rec.provider_key}",
            )
        )
        token = creds.get("api_key") or creds.get("access_token") or ""
        if token:
            headers.setdefault("Authorization", f"Bearer {token}")

    client = http_client or httpx.Client(timeout=8.0, follow_redirects=False)
    should_close = http_client is None
    now = datetime.now(timezone.utc)
    try:
        resp = client.get(safe_url, headers=headers)
        if 200 <= resp.status_code < 300:
            rec.lifecycle_state = "LIVE_VERIFIED"
            rec.last_verified_at = now
            rec.last_error = None
        elif resp.status_code in (401, 403):
            rec.lifecycle_state = "FAILED"
            rec.last_error = f"Authentication rejected (HTTP {resp.status_code})."
        else:
            rec.lifecycle_state = "DEGRADED"
            rec.last_error = f"Endpoint returned HTTP {resp.status_code}."
    except Exception as exc:
        rec.lifecycle_state = "DEGRADED"
        rec.last_error = f"Connection test error: {type(exc).__name__}"
    finally:
        if should_close:
            client.close()

    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_CONNECTOR_TESTED",
        resource=rec.connector_id,
        outcome=rec.lifecycle_state,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def approve_connector_permissions(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    if rec.lifecycle_state == "REVOKED":
        raise ConflictError("Cannot approve permissions for a REVOKED connector.")
    if scopes is not None:
        rec.required_scopes_json = json.dumps(scopes)
    rec.approved_by = principal.username
    if rec.lifecycle_state in {"AWAITING_AUTHORIZATION", "AUTHENTICATED", "DISCOVERED"}:
        rec.lifecycle_state = "CONNECTED"
    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_CONNECTOR_APPROVED",
        resource=rec.connector_id,
        outcome=f"approved_by={principal.username}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def rotate_connector_credentials(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    credentials: dict[str, Any] | None = None,
    webhook_secret: str = "",
    settings: Settings,
) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    now = datetime.now(timezone.utc)
    if webhook_secret.strip():
        enc_wh, nonce = encrypt_vault_secret(
            webhook_secret.strip(),
            master_secret=settings.vault_master_key.get_secret_value(),
            aad=_webhook_aad(principal.tenant_id, rec.connector_id),
        )
        rec.encrypted_webhook_secret_b64 = enc_wh
        rec.webhook_secret_nonce_b64 = nonce
    if credentials:
        connect_with_credentials(
            db,
            principal=principal,
            provider=rec.provider_key,
            credentials=credentials,
            auth_type="API_KEY",
            settings=settings,
        ) if rec.provider_key in SUPPORTED_MANAGED_PROVIDERS else None
        enc_c, c_nonce = encrypt_vault_secret(
            json.dumps(credentials),
            master_secret=settings.vault_master_key.get_secret_value(),
            aad=f"ultron-integration::{principal.tenant_id}::{rec.provider_key}",
        )
        ic = db.execute(
            select(IntegrationConnectionRecord).where(
                IntegrationConnectionRecord.tenant_id == principal.tenant_id,
                IntegrationConnectionRecord.provider == rec.provider_key,
            )
        ).scalar_one_or_none()
        if ic is not None:
            ic.encrypted_credentials_b64 = enc_c
            ic.credentials_nonce_b64 = c_nonce
            ic.updated_at = now

    rec.lifecycle_state = "AUTHENTICATED"
    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_CONNECTOR_ROTATED",
        resource=rec.connector_id,
        outcome="ROTATED",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def revoke_universal_connector(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    settings: Settings,
) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    rec.lifecycle_state = "REVOKED"
    rec.encrypted_webhook_secret_b64 = None
    rec.webhook_secret_nonce_b64 = None
    rec.approved_by = None
    rec.updated_at = datetime.now(timezone.utc)

    if rec.provider_key in SUPPORTED_MANAGED_PROVIDERS:
        try:
            disconnect_connection(db, principal=principal, provider=rec.provider_key, settings=settings)
        except Exception:
            pass

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_CONNECTOR_REVOKED",
        resource=rec.connector_id,
        outcome="REVOKED",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def receive_universal_webhook(
    db: Session,
    *,
    connector_id: str,
    raw_body: bytes,
    signature_header: str | None,
    idempotency_key: str | None,
    event_type: str = "webhook.event",
    settings: Settings,
) -> dict[str, Any]:
    rec = db.execute(
        select(UniversalConnectorRecord).where(UniversalConnectorRecord.connector_id == connector_id)
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Connector '{connector_id}' not found.")
    if rec.lifecycle_state == "REVOKED":
        raise ConflictError("Connector is REVOKED; webhook rejected.")
    if not rec.encrypted_webhook_secret_b64 or not rec.webhook_secret_nonce_b64:
        raise ConflictError("Webhook signing secret is not configured.")

    secret = decrypt_vault_secret(
        rec.encrypted_webhook_secret_b64,
        rec.webhook_secret_nonce_b64,
        master_secret=settings.vault_master_key.get_secret_value(),
        aad=_webhook_aad(rec.tenant_id, rec.connector_id),
    )
    expected_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = (signature_header or "").strip().removeprefix("sha256=")
    sig_ok = bool(provided) and hmac.compare_digest(provided, expected_hex)

    idem = (idempotency_key or "").strip() or hashlib.sha256(raw_body).hexdigest()[:32]
    if not sig_ok:
        deliv = WebhookDeliveryRecord(
            delivery_id=f"whd_{uuid.uuid4().hex[:14]}",
            tenant_id=rec.tenant_id,
            connector_id=rec.connector_id,
            event_type=event_type[:120],
            idempotency_key=idem[:160],
            signature_valid=False,
            status="REJECTED",
            payload_summary="Invalid HMAC-SHA256 signature.",
        )
        db.add(deliv)
        append_audit_log(
            db,
            tenant_id=rec.tenant_id,
            actor="universal_webhook",
            action="UNIVERSAL_WEBHOOK_REJECTED",
            resource=rec.connector_id,
            outcome="INVALID_SIGNATURE",
        )
        db.commit()
        raise AuthenticationError("Invalid webhook signature.")

    existing = db.execute(
        select(WebhookDeliveryRecord).where(
            WebhookDeliveryRecord.tenant_id == rec.tenant_id,
            WebhookDeliveryRecord.connector_id == rec.connector_id,
            WebhookDeliveryRecord.idempotency_key == idem[:160],
            WebhookDeliveryRecord.signature_valid.is_(True),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"status": "DUPLICATE_REPLAY", "delivery_id": existing.delivery_id, "idempotency_key": idem}

    deliv = WebhookDeliveryRecord(
        delivery_id=f"whd_{uuid.uuid4().hex[:14]}",
        tenant_id=rec.tenant_id,
        connector_id=rec.connector_id,
        event_type=event_type[:120],
        idempotency_key=idem[:160],
        signature_valid=True,
        status="ACCEPTED",
        payload_summary=f"bytes={len(raw_body)}",
    )
    db.add(deliv)
    rec.lifecycle_state = "LIVE_VERIFIED"
    rec.last_verified_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=rec.tenant_id,
        actor="universal_webhook",
        action="UNIVERSAL_WEBHOOK_ACCEPTED",
        resource=rec.connector_id,
        outcome=f"event={event_type}|idem={idem}",
    )
    db.commit()
    return {"status": "ACCEPTED", "delivery_id": deliv.delivery_id, "idempotency_key": idem}


def list_webhook_deliveries(db: Session, *, tenant_id: str, connector_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(WebhookDeliveryRecord)
        .where(
            WebhookDeliveryRecord.tenant_id == tenant_id,
            WebhookDeliveryRecord.connector_id == connector_id,
        )
        .order_by(WebhookDeliveryRecord.received_at.desc())
    ).scalars().all()
    return [
        {
            "delivery_id": r.delivery_id,
            "connector_id": r.connector_id,
            "event_type": r.event_type,
            "idempotency_key": r.idempotency_key,
            "signature_valid": r.signature_valid,
            "status": r.status,
            "payload_summary": r.payload_summary,
            "received_at": r.received_at.isoformat(),
        }
        for r in rows
    ]


def discover_authorized_services_for_agents(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    """Used by NEON/ARGON to discover only connected & explicitly approved services."""
    rows = db.execute(
        select(UniversalConnectorRecord).where(
            UniversalConnectorRecord.tenant_id == tenant_id,
            UniversalConnectorRecord.lifecycle_state.in_(["AUTHENTICATED", "CONNECTED", "LIVE_VERIFIED"]),
            UniversalConnectorRecord.approved_by.is_not(None),
        )
    ).scalars().all()
    return [_serialize_universal_connector(r) for r in rows]


def execute_authorized_connector_action(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    capability: str,
    project_id: str = "*",
    agent_id: str = "*",
) -> dict[str, Any]:
    """Enforce user, project, agent, and action-level capability approval before ARGON executes on a connector."""
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    if rec.lifecycle_state in {"REVOKED", "EXPIRED", "FAILED", "NOT_CONFIGURED", "CONFIGURATION_REQUIRED"}:
        raise ConflictError(f"Connector '{rec.name}' is in state '{rec.lifecycle_state}' and cannot execute actions.")
    if not rec.approved_by:
        return {
            "authorized": False,
            "status": "APPROVAL_REQUIRED",
            "connector_id": rec.connector_id,
            "capability": capability,
            "message": f"Explicit user approval is required before ARGON may use '{rec.name}'.",
        }

    # Check per-user, per-project, per-agent scope grants if any have been configured for this connector
    all_grants = db.execute(
        select(ConnectorScopeGrantRecord).where(
            ConnectorScopeGrantRecord.tenant_id == principal.tenant_id,
            ConnectorScopeGrantRecord.connector_id == rec.connector_id,
        )
    ).scalars().all()
    if all_grants:
        matched = False
        for g in all_grants:
            if g.status != "ACTIVE":
                continue
            u_ok = g.user_id in {principal.user_id, "*"}
            p_ok = g.project_id in {project_id, "*"}
            a_ok = g.agent_id in {agent_id, "*"}
            tools = json.loads(g.allowed_tools_json or "[]")
            t_ok = (not tools) or (capability in tools) or ("*" in tools)
            if u_ok and p_ok and a_ok and t_ok:
                matched = True
                break
        if not matched:
            return {
                "authorized": False,
                "status": "SCOPE_GRANT_REQUIRED",
                "connector_id": rec.connector_id,
                "capability": capability,
                "project_id": project_id,
                "agent_id": agent_id,
                "message": f"No active scope grant authorizes user '{principal.user_id}', project '{project_id}', agent '{agent_id}' for '{capability}'.",
            }

    caps = json.loads(rec.capabilities_json or "[]")
    if caps and capability not in caps:
        return {
            "authorized": False,
            "status": "CAPABILITY_NOT_PERMITTED",
            "connector_id": rec.connector_id,
            "capability": capability,
            "message": f"Capability '{capability}' is not permitted on '{rec.name}'.",
        }
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ARGON_CONNECTOR_ACTION_AUTHORIZED",
        resource=f"{rec.connector_id}:{capability}",
        outcome=f"AUTHORIZED|project={project_id}|agent={agent_id}",
    )
    db.commit()
    return {
        "authorized": True,
        "status": "AUTHORIZED",
        "connector_id": rec.connector_id,
        "provider_key": rec.provider_key,
        "capability": capability,
        "project_id": project_id,
        "agent_id": agent_id,
    }


def probe_google_adc() -> dict[str, Any]:
    """Safely inspect Google Application Default Credentials availability without exposing secrets."""
    cred_file = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if cred_file and os.path.isfile(cred_file):
        return {"adc_available": True, "source": "GOOGLE_APPLICATION_CREDENTIALS", "detail": "ADC JSON file path configured."}
    try:
        import google.auth  # type: ignore

        creds, project = google.auth.default()
        if creds is not None:
            return {"adc_available": True, "source": "google.auth.default", "project_id": project or ""}
    except Exception:
        pass
    return {"adc_available": False, "source": "none", "detail": "No Google Application Default Credentials detected in environment."}


def probe_mcp_streamable_http(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Discover tools from a remote Streamable HTTP MCP server via JSON-RPC 2.0 initialize + tools/list."""
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    if rec.connection_method != "MCP_STREAMABLE_HTTP":
        raise ValidationError("Connector is not configured as MCP_STREAMABLE_HTTP.")
    if rec.lifecycle_state == "REVOKED":
        raise ConflictError("Cannot probe a REVOKED MCP connector.")

    endpoint = validate_public_https_url(rec.api_base_url)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **json.loads(rec.required_headers_json or "{}"),
    }

    ic = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == principal.tenant_id,
            IntegrationConnectionRecord.provider == rec.provider_key,
        )
    ).scalar_one_or_none()
    if ic and ic.encrypted_credentials_b64 and ic.credentials_nonce_b64:
        creds = json.loads(
            decrypt_vault_secret(
                ic.encrypted_credentials_b64,
                ic.credentials_nonce_b64,
                master_secret=settings.vault_master_key.get_secret_value(),
                aad=f"ultron-integration::{principal.tenant_id}::{rec.provider_key}",
            )
        )
        tok = creds.get("api_key") or creds.get("access_token") or ""
        if tok:
            headers.setdefault("Authorization", f"Bearer {tok}")

    client = http_client or httpx.Client(timeout=10.0, follow_redirects=False)
    should_close = http_client is None
    now = datetime.now(timezone.utc)
    discovered_tools: list[dict[str, Any]] = []
    try:
        init_resp = client.post(
            endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "ULTRON-OS", "version": "2026.4"}},
            },
        )
        if init_resp.status_code not in (200, 202):
            rec.lifecycle_state = "FAILED" if init_resp.status_code in (401, 403) else "DEGRADED"
            rec.last_error = f"MCP initialize returned HTTP {init_resp.status_code}."
            rec.updated_at = now
            db.commit()
            return _serialize_universal_connector(rec)

        tools_resp = client.post(
            endpoint,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        if tools_resp.status_code == 200:
            body_text = tools_resp.text or ""
            if "data:" in body_text and "text/event-stream" in (tools_resp.headers.get("content-type") or ""):
                for line in body_text.splitlines():
                    if line.startswith("data:"):
                        parsed = json.loads(line.removeprefix("data:").strip())
                        if isinstance(parsed, dict) and "result" in parsed:
                            discovered_tools = parsed["result"].get("tools", [])
                            break
            else:
                discovered_tools = (tools_resp.json().get("result") or {}).get("tools", [])

            rec.mcp_tools_json = json.dumps(discovered_tools)
            tool_names = [t.get("name") for t in discovered_tools if isinstance(t, dict) and t.get("name")]
            if tool_names:
                rec.capabilities_json = json.dumps(tool_names)
            rec.lifecycle_state = "LIVE_VERIFIED"
            rec.last_verified_at = now
            rec.last_error = None
        else:
            rec.lifecycle_state = "DEGRADED"
            rec.last_error = f"MCP tools/list returned HTTP {tools_resp.status_code}."
    except Exception as exc:
        rec.lifecycle_state = "DEGRADED"
        rec.last_error = f"MCP probe error: {type(exc).__name__}"
    finally:
        if should_close:
            client.close()

    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UNIVERSAL_MCP_PROBED",
        resource=rec.connector_id,
        outcome=f"state={rec.lifecycle_state}|tools={len(discovered_tools)}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_universal_connector(rec)


def grant_connector_scope(
    db: Session,
    *,
    principal: Principal,
    connector_id: str,
    user_id: str = "*",
    project_id: str = "*",
    agent_id: str = "*",
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=principal.tenant_id, connector_id=connector_id)
    if rec.lifecycle_state == "REVOKED":
        raise ConflictError("Cannot grant scopes on a REVOKED connector.")
    grant = ConnectorScopeGrantRecord(
        grant_id=f"csg_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        connector_id=rec.connector_id,
        user_id=(user_id or "*").strip()[:64],
        project_id=(project_id or "*").strip()[:64],
        agent_id=(agent_id or "*").strip()[:64],
        allowed_tools_json=json.dumps(allowed_tools or []),
        status="ACTIVE",
        granted_by=principal.username,
    )
    db.add(grant)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CONNECTOR_SCOPE_GRANTED",
        resource=rec.connector_id,
        outcome=f"user={grant.user_id}|project={grant.project_id}|agent={grant.agent_id}",
    )
    db.commit()
    db.refresh(grant)
    return _serialize_scope_grant(grant)


def list_connector_scopes(db: Session, *, tenant_id: str, connector_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ConnectorScopeGrantRecord)
        .where(
            ConnectorScopeGrantRecord.tenant_id == tenant_id,
            ConnectorScopeGrantRecord.connector_id == connector_id,
        )
        .order_by(ConnectorScopeGrantRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_scope_grant(r) for r in rows]


def revoke_connector_scope(db: Session, *, principal: Principal, grant_id: str) -> dict[str, Any]:
    grant = db.execute(
        select(ConnectorScopeGrantRecord).where(
            ConnectorScopeGrantRecord.tenant_id == principal.tenant_id,
            ConnectorScopeGrantRecord.grant_id == grant_id,
        )
    ).scalar_one_or_none()
    if grant is None:
        raise NotFoundError(f"Scope grant '{grant_id}' not found.")
    grant.status = "REVOKED"
    grant.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CONNECTOR_SCOPE_REVOKED",
        resource=grant.connector_id,
        outcome=grant_id,
    )
    db.commit()
    db.refresh(grant)
    return _serialize_scope_grant(grant)


def diagnose_universal_connector(db: Session, *, tenant_id: str, connector_id: str) -> dict[str, Any]:
    rec = _get_connector(db, tenant_id=tenant_id, connector_id=connector_id)
    scopes = list_connector_scopes(db, tenant_id=tenant_id, connector_id=connector_id)
    active_scopes = [s for s in scopes if s["status"] == "ACTIVE"]
    return {
        "connector_id": rec.connector_id,
        "name": rec.name,
        "connection_method": rec.connection_method,
        "lifecycle_state": rec.lifecycle_state,
        "ssrf_validated": bool(rec.api_base_url or rec.website_url),
        "approved_by": rec.approved_by,
        "active_scope_grants": len(active_scopes),
        "mcp_tools_discovered": len(json.loads(rec.mcp_tools_json or "[]")),
        "google_adc": probe_google_adc() if rec.connection_method == "GOOGLE_ADC" else None,
        "last_verified_at": rec.last_verified_at.isoformat() if rec.last_verified_at else None,
        "last_error": rec.last_error,
    }


def _get_connector(db: Session, *, tenant_id: str, connector_id: str) -> UniversalConnectorRecord:
    rec = db.execute(
        select(UniversalConnectorRecord).where(
            UniversalConnectorRecord.tenant_id == tenant_id,
            UniversalConnectorRecord.connector_id == connector_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Universal connector '{connector_id}' not found.")
    return rec


def _serialize_scope_grant(g: ConnectorScopeGrantRecord) -> dict[str, Any]:
    return {
        "grant_id": g.grant_id,
        "connector_id": g.connector_id,
        "user_id": g.user_id,
        "project_id": g.project_id,
        "agent_id": g.agent_id,
        "allowed_tools": json.loads(g.allowed_tools_json or "[]"),
        "status": g.status,
        "granted_by": g.granted_by,
        "created_at": g.created_at.isoformat(),
    }


def _serialize_universal_connector(r: UniversalConnectorRecord) -> dict[str, Any]:
    return {
        "connector_id": r.connector_id,
        "provider_key": r.provider_key,
        "name": r.name,
        "category": r.category,
        "connection_method": r.connection_method,
        "lifecycle_state": r.lifecycle_state,
        "website_url": r.website_url,
        "docs_url": r.docs_url,
        "api_base_url": r.api_base_url,
        "required_scopes": json.loads(r.required_scopes_json or "[]"),
        "capabilities": json.loads(r.capabilities_json or "[]"),
        "discovered_auth_methods": json.loads(r.discovered_auth_methods_json or "[]"),
        "webhook_endpoint_path": r.webhook_endpoint_path,
        "has_webhook_secret": bool(r.encrypted_webhook_secret_b64),
        "subscribed_events": json.loads(r.subscribed_events_json or "[]"),
        "mcp_config": json.loads(r.mcp_config_json or "{}"),
        "mcp_tools": json.loads(r.mcp_tools_json or "[]"),
        "approved_by": r.approved_by,
        "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
        "last_error": r.last_error,
        "source": "CUSTOM_UNIVERSAL",
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
