"""First-party UBA Verve Direct Integration Adapter (Developer Zone Sandbox & Capability Governance).

Never requests, stores, or logs full card PAN, CVV, PIN, or OTP.
Credentials are resolved strictly server-side from encrypted tenant VAULT or Settings.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import contains_raw_payment_card_or_cvv
from app.db.models import IntegrationConnectionRecord
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval

UBA_PROVIDER_KEY = "uba_verve"

UBA_LIFECYCLE_STATES = frozenset({
    "UNCONFIGURED",
    "SANDBOX_CONFIGURED",
    "AUTHENTICATED",
    "LIVE_VERIFIED",
    "REVOKED",
    "UNAVAILABLE",
})

UBA_CAPABILITIES: dict[str, dict[str, Any]] = {
    "CARD_DISPLAY": {
        "capability": "CARD_DISPLAY",
        "description": "Display-only UBA Verve card visual representation (non-transactional).",
        "requires_uba_approval": False,
        "requires_aegis_approval": False,
    },
    "CARD_PAYMENT": {
        "capability": "CARD_PAYMENT",
        "description": "Card payment execution — requires authorized UBA merchant/acquiring interface (U-Collect / Merchant Acquiring) and AEGIS approval.",
        "requires_uba_approval": True,
        "requires_aegis_approval": True,
    },
    "ACCOUNT_BALANCE": {
        "capability": "ACCOUNT_BALANCE",
        "description": "Account balance enquiry — requires approved UBA Developer Zone Balance Enquiry API (CBN PSSP/MMO license + UBA corporate account).",
        "requires_uba_approval": True,
        "requires_aegis_approval": False,
    },
    "ACCOUNT_TRANSACTIONS": {
        "capability": "ACCOUNT_TRANSACTIONS",
        "description": "Account statement/transaction history — requires approved UBA Developer Zone Statement API (CBN PSSP/MMO license + UBA corporate account).",
        "requires_uba_approval": True,
        "requires_aegis_approval": False,
    },
    "CARD_AUTHORIZATION": {
        "capability": "CARD_AUTHORIZATION",
        "description": "Issuer-supported card authorization flow — requires official UBA issuer authorization onboarding and AEGIS approval.",
        "requires_uba_approval": True,
        "requires_aegis_approval": True,
    },
}

UBA_DEVELOPER_ZONE_REQUIREMENTS = {
    "portal_url": "https://www.ubagroup.com/nigeria/about-us/initiatives/developer-zone/",
    "documented_apis": ["Direct Debit", "Transfer", "Statement", "Balance Enquiry", "ATM Locator"],
    "eligibility_requirements": [
        "PSSP License from CBN or Mobile Money License",
        "Corporate Account with UBA",
        "Data Policy compliance",
        "Collateral (required for Direct Debit)",
        "Separate Merchant Acquiring / U-Collect onboarding for card payment acceptance",
    ],
    "personal_debit_card_grants_api_access": False,
}

_SENSITIVE_CARD_FIELD_RE = re.compile(r"\b(cvv|cvc|pin|otp|card_number|pan)\b", re.IGNORECASE)


def _assert_no_sensitive_card_input(*values: str) -> None:
    for v in values:
        if not v:
            continue
        if contains_raw_payment_card_or_cvv(v):
            raise ValidationError("Raw payment card numbers, CVV, PIN, or OTP are strictly prohibited.")


def _get_uba_connection_record(db: Session, *, tenant_id: str) -> IntegrationConnectionRecord | None:
    return db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tenant_id,
            IntegrationConnectionRecord.provider == UBA_PROVIDER_KEY,
        )
    ).scalar_one_or_none()


def _resolve_uba_server_credentials(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
) -> dict[str, str]:
    """Resolve UBA credentials strictly server-side from tenant VAULT or Settings."""
    from app.services.integration_manager import _decrypt_credentials

    rec = _get_uba_connection_record(db, tenant_id=tenant_id)
    if rec is not None and rec.status == "REVOKED":
        return {"_revoked": "true"}

    creds: dict[str, Any] = {}
    if rec is not None:
        try:
            creds = _decrypt_credentials(rec, settings)
        except Exception:
            creds = {}

    base_url = str(creds.get("uba_api_base_url") or settings.uba_api_base_url or "").strip().rstrip("/")
    client_id = str(creds.get("uba_client_id") or settings.uba_client_id or "").strip()
    client_secret = str(
        creds.get("uba_client_secret")
        or (settings.uba_client_secret.get_secret_value() if settings.uba_client_secret else "")
        or ""
    ).strip()
    api_key = str(
        creds.get("uba_api_key")
        or (settings.uba_api_key.get_secret_value() if settings.uba_api_key else "")
        or ""
    ).strip()
    env = str(creds.get("uba_environment") or settings.uba_environment or "sandbox").strip().lower()

    return {
        "base_url": base_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "api_key": api_key,
        "environment": env if env in {"sandbox", "production"} else "sandbox",
    }


def _compute_lifecycle_state(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
) -> tuple[str, dict[str, str]]:
    rec = _get_uba_connection_record(db, tenant_id=tenant_id)
    if rec is not None and rec.status == "REVOKED":
        return "REVOKED", {"environment": settings.uba_environment}

    creds = _resolve_uba_server_credentials(db, tenant_id=tenant_id, settings=settings)
    has_creds = bool(creds.get("base_url") and creds.get("client_id") and (creds.get("client_secret") or creds.get("api_key")))

    if not has_creds:
        return "UNCONFIGURED", creds

    if rec is not None and rec.status in UBA_LIFECYCLE_STATES:
        return rec.status, creds

    return ("SANDBOX_CONFIGURED" if creds.get("environment") == "sandbox" else "UNAVAILABLE"), creds


def get_uba_verve_status(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
) -> dict[str, Any]:
    state, creds = _compute_lifecycle_state(db, tenant_id=principal.tenant_id, settings=settings)
    live_active = state == "LIVE_VERIFIED"
    sandbox_auth = state in {"AUTHENTICATED", "LIVE_VERIFIED"}

    capabilities = {
        "CARD_DISPLAY": {
            **UBA_CAPABILITIES["CARD_DISPLAY"],
            "enabled": True,
            "mode": "DISPLAY_ONLY",
        },
        "CARD_PAYMENT": {
            **UBA_CAPABILITIES["CARD_PAYMENT"],
            "enabled": live_active,
            "mode": "LIVE" if live_active else "REQUIRES_UBA_MERCHANT_AND_AEGIS_APPROVAL",
        },
        "ACCOUNT_BALANCE": {
            **UBA_CAPABILITIES["ACCOUNT_BALANCE"],
            "enabled": sandbox_auth,
            "mode": "LIVE" if live_active else ("SANDBOX_MOCK" if sandbox_auth else "LOCKED"),
        },
        "ACCOUNT_TRANSACTIONS": {
            **UBA_CAPABILITIES["ACCOUNT_TRANSACTIONS"],
            "enabled": sandbox_auth,
            "mode": "LIVE" if live_active else ("SANDBOX_MOCK" if sandbox_auth else "LOCKED"),
        },
        "CARD_AUTHORIZATION": {
            **UBA_CAPABILITIES["CARD_AUTHORIZATION"],
            "enabled": live_active,
            "mode": "LIVE" if live_active else "REQUIRES_UBA_ISSUER_AND_AEGIS_APPROVAL",
        },
    }

    return {
        "provider": UBA_PROVIDER_KEY,
        "display_name": "UBA Verve Direct",
        "environment": creds.get("environment", settings.uba_environment),
        "lifecycle_state": state,
        "has_base_url": bool(creds.get("base_url")),
        "has_client_id": bool(creds.get("client_id")),
        "has_client_secret": bool(creds.get("client_secret")),
        "has_api_key": bool(creds.get("api_key")),
        "capabilities": capabilities,
        "developer_zone": UBA_DEVELOPER_ZONE_REQUIREMENTS,
    }


def _upsert_uba_state(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    status: str,
    last_error: str | None = None,
) -> IntegrationConnectionRecord:
    rec = _get_uba_connection_record(db, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)
    if rec is None:
        rec = IntegrationConnectionRecord(
            connection_id=f"con_{uuid.uuid4().hex[:14]}",
            tenant_id=tenant_id,
            provider=UBA_PROVIDER_KEY,
            auth_type="OAUTH2_CLIENT_CREDENTIALS",
            status=status,
            scopes_json=json.dumps(list(UBA_CAPABILITIES.keys())),
            last_verified_at=now if status in {"AUTHENTICATED", "LIVE_VERIFIED"} else None,
            last_error=last_error,
            connected_by=user_id,
        )
        db.add(rec)
    else:
        rec.status = status
        rec.last_error = last_error
        if status in {"AUTHENTICATED", "LIVE_VERIFIED"}:
            rec.last_verified_at = now
        rec.updated_at = now
    return rec


def verify_uba_verve_connection(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    http_client: httpx.Client | None = None,
    use_sandbox_mock: bool = False,
) -> dict[str, Any]:
    state, creds = _compute_lifecycle_state(db, tenant_id=principal.tenant_id, settings=settings)

    if state == "REVOKED":
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome="REVOKED",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "REVOKED", "detail": "UBA consent has been revoked."}

    if state == "UNCONFIGURED":
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome="UNCONFIGURED",
        )
        db.commit()
        return {
            "provider": UBA_PROVIDER_KEY,
            "lifecycle_state": "UNCONFIGURED",
            "detail": "UBA_API_BASE_URL, UBA_CLIENT_ID, and UBA_CLIENT_SECRET/UBA_API_KEY are not configured.",
        }

    if use_sandbox_mock and creds.get("environment") == "sandbox":
        _upsert_uba_state(db, tenant_id=principal.tenant_id, user_id=principal.user_id, status="AUTHENTICATED", last_error=None)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome="AUTHENTICATED_SANDBOX_MOCK",
        )
        db.commit()
        return {
            "provider": UBA_PROVIDER_KEY,
            "lifecycle_state": "AUTHENTICATED",
            "sandbox_mock": True,
            "detail": "Authenticated against UBA Sandbox mock adapter (not live UBA production).",
        }

    client = http_client or httpx.Client(timeout=8.0)
    should_close = http_client is None
    token_url = f"{creds['base_url']}/token"
    try:
        resp = client.post(
            token_url,
            data={"grant_type": "client_credentials"},
            auth=(creds["client_id"], creds["client_secret"]),
            headers={"X-API-Key": creds["api_key"]} if creds.get("api_key") else {},
        )
        if resp.status_code == 200:
            _upsert_uba_state(db, tenant_id=principal.tenant_id, user_id=principal.user_id, status="LIVE_VERIFIED", last_error=None)
            append_audit_log(
                db,
                tenant_id=principal.tenant_id,
                actor=principal.username,
                action="UBA_VERVE_CONNECTION_CHECK",
                resource=UBA_PROVIDER_KEY,
                outcome="LIVE_VERIFIED",
            )
            db.commit()
            return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "LIVE_VERIFIED", "sandbox_mock": False, "detail": "Live UBA token endpoint verified."}

        err_msg = f"UBA rejected credentials or endpoint returned HTTP {resp.status_code}."
        _upsert_uba_state(db, tenant_id=principal.tenant_id, user_id=principal.user_id, status="UNAVAILABLE", last_error=err_msg)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome=f"UNAVAILABLE|http_{resp.status_code}",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "UNAVAILABLE", "detail": err_msg}
    except httpx.TimeoutException:
        err_msg = "UBA API request timed out."
        _upsert_uba_state(db, tenant_id=principal.tenant_id, user_id=principal.user_id, status="UNAVAILABLE", last_error=err_msg)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome="UNAVAILABLE|timeout",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "UNAVAILABLE", "detail": err_msg}
    except Exception as exc:
        err_msg = f"UBA API endpoint unavailable: {type(exc).__name__}"
        _upsert_uba_state(db, tenant_id=principal.tenant_id, user_id=principal.user_id, status="UNAVAILABLE", last_error=err_msg)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_CONNECTION_CHECK",
            resource=UBA_PROVIDER_KEY,
            outcome=f"UNAVAILABLE|{type(exc).__name__}",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "UNAVAILABLE", "detail": err_msg}
    finally:
        if should_close:
            client.close()


def _require_uba_query_ready(db: Session, *, tenant_id: str, settings: Settings) -> tuple[str, dict[str, str]]:
    state, creds = _compute_lifecycle_state(db, tenant_id=tenant_id, settings=settings)
    if state == "REVOKED":
        raise ConflictError("UBA Verve consent has been revoked for this tenant.")
    if state == "UNCONFIGURED":
        raise ConflictError("UBA Verve integration is UNCONFIGURED. Configure UBA sandbox credentials first.")
    if state == "UNAVAILABLE":
        raise ConflictError("UBA Verve endpoint is currently UNAVAILABLE.")
    return state, creds


def query_uba_account_balance(
    db: Session,
    *,
    principal: Principal,
    account_ref: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
    use_sandbox_mock: bool = False,
) -> dict[str, Any]:
    _assert_no_sensitive_card_input(account_ref)
    state, creds = _require_uba_query_ready(db, tenant_id=principal.tenant_id, settings=settings)

    if use_sandbox_mock and creds.get("environment") == "sandbox":
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_BALANCE_ENQUIRY",
            resource=account_ref[:32],
            outcome="SANDBOX_MOCK_OK",
        )
        db.commit()
        return {
            "provider": UBA_PROVIDER_KEY,
            "capability": "ACCOUNT_BALANCE",
            "lifecycle_state": state,
            "sandbox_mock": True,
            "account_ref": account_ref,
            "currency": "NGN",
            "available_balance": 250000.00,
            "ledger_balance": 250000.00,
        }

    client = http_client or httpx.Client(timeout=8.0)
    should_close = http_client is None
    try:
        resp = client.get(
            f"{creds['base_url']}/accounts/{account_ref}/balance",
            headers={"X-API-Key": creds["api_key"]} if creds.get("api_key") else {},
        )
        if resp.status_code != 200:
            raise ConflictError(f"UBA Balance Enquiry unavailable (HTTP {resp.status_code}).")
        payload = resp.json()
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_BALANCE_ENQUIRY",
            resource=account_ref[:32],
            outcome="LIVE_OK",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "capability": "ACCOUNT_BALANCE", "lifecycle_state": "LIVE_VERIFIED", "sandbox_mock": False, **payload}
    except httpx.TimeoutException as exc:
        raise ConflictError("UBA Balance Enquiry timed out.") from exc
    finally:
        if should_close:
            client.close()


def query_uba_account_transactions(
    db: Session,
    *,
    principal: Principal,
    account_ref: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
    use_sandbox_mock: bool = False,
) -> dict[str, Any]:
    _assert_no_sensitive_card_input(account_ref)
    state, creds = _require_uba_query_ready(db, tenant_id=principal.tenant_id, settings=settings)

    if use_sandbox_mock and creds.get("environment") == "sandbox":
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_STATEMENT_ENQUIRY",
            resource=account_ref[:32],
            outcome="SANDBOX_MOCK_OK",
        )
        db.commit()
        return {
            "provider": UBA_PROVIDER_KEY,
            "capability": "ACCOUNT_TRANSACTIONS",
            "lifecycle_state": state,
            "sandbox_mock": True,
            "account_ref": account_ref,
            "transactions": [
                {"tx_ref": "UBA-SBX-001", "type": "DEBIT", "amount": 15000.00, "currency": "NGN", "narration": "SANDBOX MOCK POS"},
            ],
        }

    client = http_client or httpx.Client(timeout=8.0)
    should_close = http_client is None
    try:
        resp = client.get(
            f"{creds['base_url']}/accounts/{account_ref}/transactions",
            headers={"X-API-Key": creds["api_key"]} if creds.get("api_key") else {},
        )
        if resp.status_code != 200:
            raise ConflictError(f"UBA Statement Enquiry unavailable (HTTP {resp.status_code}).")
        payload = resp.json()
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="UBA_VERVE_STATEMENT_ENQUIRY",
            resource=account_ref[:32],
            outcome="LIVE_OK",
        )
        db.commit()
        return {"provider": UBA_PROVIDER_KEY, "capability": "ACCOUNT_TRANSACTIONS", "lifecycle_state": "LIVE_VERIFIED", "sandbox_mock": False, **payload}
    except httpx.TimeoutException as exc:
        raise ConflictError("UBA Statement Enquiry timed out.") from exc
    finally:
        if should_close:
            client.close()


def request_uba_financial_action(
    db: Session,
    *,
    principal: Principal,
    capability: str,
    card_id: str,
    amount_ngn: float,
    counterparty: str,
    settings: Settings,
) -> dict[str, Any]:
    """Every CARD_PAYMENT or CARD_AUTHORIZATION requires explicit AEGIS approval and immutable audit logging."""
    cap = capability.strip().upper()
    if cap not in {"CARD_PAYMENT", "CARD_AUTHORIZATION"}:
        raise ValidationError("capability must be CARD_PAYMENT or CARD_AUTHORIZATION.")
    if amount_ngn <= 0:
        raise ValidationError("amount_ngn must be positive.")
    _assert_no_sensitive_card_input(card_id, counterparty)

    state, _ = _compute_lifecycle_state(db, tenant_id=principal.tenant_id, settings=settings)
    if state == "REVOKED":
        raise ConflictError("UBA Verve consent is REVOKED. Cannot initiate financial action.")

    approval = create_approval_request(
        db,
        tenant_id=principal.tenant_id,
        requested_by=principal.username,
        action_type=f"UBA_VERVE_{cap}",
        reason=f"Explicit AEGIS approval required for UBA Verve {cap} of NGN {amount_ngn:,.2f} to {counterparty}.",
        payload={
            "provider": UBA_PROVIDER_KEY,
            "capability": cap,
            "card_id": card_id,
            "amount_ngn": amount_ngn,
            "counterparty": counterparty,
            "uba_lifecycle_state": state,
        },
        commit=False,
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UBA_VERVE_FINANCIAL_ACTION_REQUESTED",
        resource=card_id,
        outcome=f"cap={cap}|amount_ngn={amount_ngn}|approval={approval.approval_id}|executed=false",
    )
    db.commit()
    return {
        "provider": UBA_PROVIDER_KEY,
        "capability": cap,
        "lifecycle_state": state,
        "executed": False,
        "approval_required": True,
        "approval": serialize_approval(approval),
    }


def revoke_uba_verve_consent(
    db: Session,
    *,
    principal: Principal,
) -> dict[str, Any]:
    _upsert_uba_state(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        status="REVOKED",
        last_error="Consent revoked by tenant user.",
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="UBA_VERVE_CONSENT_REVOKED",
        resource=UBA_PROVIDER_KEY,
        outcome="REVOKED",
    )
    db.commit()
    return {"provider": UBA_PROVIDER_KEY, "lifecycle_state": "REVOKED"}
