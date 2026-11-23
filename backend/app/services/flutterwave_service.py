"""Flutterwave Sandbox Integration Service (Official v3 Hosted Checkout, Callback, Webhook & Verification).

Supports Nigerian Naira (NGN) and Verve via Flutterwave Hosted Checkout.
Never collects or stores card PIN, CVV, OTP, or full card PAN.
Live payments and real transfers are disabled unless explicitly authorized.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import contains_raw_payment_card_or_cvv
from app.db.models import FlutterwaveCheckoutPaymentRecord, IntegrationConnectionRecord
from app.db.repositories import append_audit_log

FLW_BASE_URL = "https://api.flutterwave.com/v3"


def _resolve_flw_credentials(
    db: Session,
    *,
    tenant_id: str,
    settings: Settings,
) -> dict[str, str]:
    from app.services.integration_manager import _decrypt_credentials

    rec = db.execute(
        select(IntegrationConnectionRecord).where(
            IntegrationConnectionRecord.tenant_id == tenant_id,
            IntegrationConnectionRecord.provider == "flutterwave",
        )
    ).scalar_one_or_none()

    creds: dict[str, Any] = {}
    if rec is not None and rec.status != "REVOKED":
        try:
            creds = _decrypt_credentials(rec, settings)
        except Exception:
            creds = {}

    pub = str(creds.get("flw_public_key") or settings.flw_public_key or "").strip()
    sec = str(
        creds.get("flw_secret_key")
        or (settings.flw_secret_key.get_secret_value() if settings.flw_secret_key else "")
        or ""
    ).strip()
    enc = str(
        creds.get("flw_encryption_key")
        or (settings.flw_encryption_key.get_secret_value() if settings.flw_encryption_key else "")
        or ""
    ).strip()
    wh_hash = str(
        creds.get("flw_secret_hash")
        or (settings.flw_secret_hash.get_secret_value() if settings.flw_secret_hash else "")
        or ""
    ).strip()
    env = str(creds.get("flw_environment") or settings.flw_environment or "test").strip().lower()

    return {
        "public_key": pub,
        "secret_key": sec,
        "encryption_key": enc,
        "secret_hash": wh_hash,
        "environment": env if env in {"test", "live"} else "test",
    }


def get_flutterwave_status(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
) -> dict[str, Any]:
    creds = _resolve_flw_credentials(db, tenant_id=principal.tenant_id, settings=settings)
    has_keys = bool(creds["public_key"] and creds["secret_key"])
    return {
        "provider": "flutterwave",
        "environment": creds["environment"],
        "live_payments_enabled": False,
        "hosted_checkout_supported": True,
        "supported_currencies": ["NGN", "USD", "GBP", "EUR"],
        "verve_supported": True,
        "has_public_key": bool(creds["public_key"]),
        "has_secret_key": bool(creds["secret_key"]),
        "has_encryption_key": bool(creds["encryption_key"]),
        "has_secret_hash": bool(creds["secret_hash"]),
        "status": "SANDBOX_CONFIGURED" if has_keys else "UNCONFIGURED",
    }


def initiate_hosted_checkout(
    db: Session,
    *,
    principal: Principal,
    amount: float,
    currency: str = "NGN",
    customer_email: str,
    customer_name: str = "",
    redirect_url: str = "https://ultron.local/finance/flutterwave/callback",
    payment_options: str = "card,banktransfer,ussd",
    idempotency_key: str | None = None,
    settings: Settings,
    http_client: httpx.Client | None = None,
    use_sandbox_mock: bool = False,
) -> dict[str, Any]:
    if amount <= 0:
        raise ValidationError("amount must be positive.")
    curr = (currency or "NGN").strip().upper()
    if curr not in {"NGN", "USD", "GBP", "EUR"}:
        raise ValidationError(f"Unsupported currency '{currency}'.")
    if contains_raw_payment_card_or_cvv(customer_email) or contains_raw_payment_card_or_cvv(customer_name):
        raise ValidationError("Raw card numbers, CVV, PIN, or OTP are strictly prohibited.")

    creds = _resolve_flw_credentials(db, tenant_id=principal.tenant_id, settings=settings)
    if creds["environment"] == "live":
        raise ConflictError("Live Flutterwave payments and real transfers are disabled in ULTRON sandbox mode.")

    idem = (idempotency_key or "").strip() or f"idem_{uuid.uuid4().hex[:16]}"
    existing = db.execute(
        select(FlutterwaveCheckoutPaymentRecord).where(
            FlutterwaveCheckoutPaymentRecord.tenant_id == principal.tenant_id,
            FlutterwaveCheckoutPaymentRecord.idempotency_key == idem,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {**_serialize_flw_payment(existing), "idempotent_replay": True}

    tx_ref = f"ULTRON-FLW-{uuid.uuid4().hex[:14].upper()}"
    checkout_url = ""

    if use_sandbox_mock:
        checkout_url = f"https://checkout.flutterwave.com/v3/hosted/pay/mock-{tx_ref.lower()}"
    else:
        if not creds["secret_key"]:
            raise ConflictError("FLW_SECRET_KEY is not configured. Configure Flutterwave test keys or use sandbox mock.")
        client = http_client or httpx.Client(timeout=10.0)
        should_close = http_client is None
        try:
            resp = client.post(
                f"{FLW_BASE_URL}/payments",
                headers={"Authorization": f"Bearer {creds['secret_key']}", "Content-Type": "application/json"},
                json={
                    "tx_ref": tx_ref,
                    "amount": round(float(amount), 2),
                    "currency": curr,
                    "redirect_url": redirect_url,
                    "payment_options": payment_options,
                    "customer": {"email": customer_email.strip(), "name": customer_name.strip() or principal.username},
                    "customizations": {"title": "ULTRON Finance Centre (Sandbox)", "description": "NGN / Verve Hosted Checkout"},
                },
            )
        except httpx.TimeoutException as exc:
            raise ConflictError("Flutterwave Hosted Checkout request timed out.") from exc
        finally:
            if should_close:
                client.close()

        if resp.status_code not in (200, 201):
            raise ConflictError(f"Flutterwave Hosted Checkout failed (HTTP {resp.status_code}).")
        data = resp.json()
        checkout_url = str((data.get("data") or {}).get("link") or "")
        if not checkout_url:
            raise ConflictError("Flutterwave Hosted Checkout response did not include a payment link.")

    rec = FlutterwaveCheckoutPaymentRecord(
        payment_id=f"flw_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        tx_ref=tx_ref,
        idempotency_key=idem,
        amount=round(float(amount), 2),
        currency=curr,
        payment_options=payment_options,
        customer_email=customer_email.strip(),
        customer_name=customer_name.strip() or principal.username,
        checkout_url=checkout_url,
        environment=creds["environment"],
        status="INITIATED",
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FLW_HOSTED_CHECKOUT_INITIATED",
        resource=tx_ref,
        outcome=f"amount={rec.amount}|currency={rec.currency}|env={rec.environment}|mock={use_sandbox_mock}",
    )
    db.commit()
    db.refresh(rec)
    return {**_serialize_flw_payment(rec), "idempotent_replay": False}


def verify_flutterwave_transaction(
    db: Session,
    *,
    principal: Principal,
    tx_ref: str,
    transaction_id: str,
    settings: Settings,
    http_client: httpx.Client | None = None,
    mock_verify_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec = db.execute(
        select(FlutterwaveCheckoutPaymentRecord).where(
            FlutterwaveCheckoutPaymentRecord.tenant_id == principal.tenant_id,
            FlutterwaveCheckoutPaymentRecord.tx_ref == tx_ref.strip(),
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Flutterwave payment '{tx_ref}' not found.")

    if rec.status == "SUCCESSFUL":
        return {**_serialize_flw_payment(rec), "idempotent_replay": True}

    creds = _resolve_flw_credentials(db, tenant_id=principal.tenant_id, settings=settings)
    if creds["environment"] == "live":
        raise ConflictError("Live Flutterwave verification is disabled in ULTRON sandbox mode.")

    if mock_verify_payload is not None:
        tx_data = mock_verify_payload
    else:
        if not creds["secret_key"]:
            raise ConflictError("FLW_SECRET_KEY is not configured for server-side transaction verification.")
        client = http_client or httpx.Client(timeout=10.0)
        should_close = http_client is None
        try:
            resp = client.get(
                f"{FLW_BASE_URL}/transactions/{transaction_id.strip()}/verify",
                headers={"Authorization": f"Bearer {creds['secret_key']}"},
            )
        except httpx.TimeoutException as exc:
            raise ConflictError("Flutterwave transaction verification timed out.") from exc
        finally:
            if should_close:
                client.close()

        if resp.status_code != 200:
            raise ConflictError(f"Flutterwave verification failed (HTTP {resp.status_code}).")
        tx_data = resp.json().get("data") or {}

    now = datetime.now(timezone.utc)
    rec.flw_transaction_id = str(tx_data.get("id") or transaction_id)
    v_status = str(tx_data.get("status") or "").lower()
    v_tx_ref = str(tx_data.get("tx_ref") or "")
    v_currency = str(tx_data.get("currency") or "").upper()
    v_amount = float(tx_data.get("amount") or 0.0)

    if v_status != "successful":
        rec.status = "FAILED"
        rec.verification_detail = f"Transaction status is '{v_status}', not 'successful'."
        rec.updated_at = now
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="FLW_TX_VERIFICATION_REJECTED",
            resource=rec.tx_ref,
            outcome=f"status={v_status}",
        )
        db.commit()
        db.refresh(rec)
        return {**_serialize_flw_payment(rec), "idempotent_replay": False}

    if v_tx_ref != rec.tx_ref or v_currency != rec.currency or v_amount < rec.amount:
        rec.status = "AMOUNT_OR_CURRENCY_MISMATCH"
        rec.verification_detail = (
            f"Mismatch: expected ({rec.tx_ref}, {rec.currency}, {rec.amount}), "
            f"got ({v_tx_ref}, {v_currency}, {v_amount})."
        )
        rec.updated_at = now
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="FLW_TX_VERIFICATION_REJECTED",
            resource=rec.tx_ref,
            outcome="AMOUNT_OR_CURRENCY_MISMATCH",
        )
        db.commit()
        db.refresh(rec)
        return {**_serialize_flw_payment(rec), "idempotent_replay": False}

    rec.status = "SUCCESSFUL"
    rec.verified_at = now
    rec.verification_detail = "Verified tx_ref, amount, currency, and status=successful server-side."
    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FLW_TX_VERIFIED_SUCCESS",
        resource=rec.tx_ref,
        outcome=f"flw_id={rec.flw_transaction_id}|amount={rec.amount}|currency={rec.currency}",
    )
    db.commit()
    db.refresh(rec)
    return {**_serialize_flw_payment(rec), "idempotent_replay": False}


def handle_flutterwave_callback(
    db: Session,
    *,
    principal: Principal,
    tx_ref: str,
    status: str,
    transaction_id: str | None,
    settings: Settings,
    http_client: httpx.Client | None = None,
    mock_verify_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec = db.execute(
        select(FlutterwaveCheckoutPaymentRecord).where(
            FlutterwaveCheckoutPaymentRecord.tenant_id == principal.tenant_id,
            FlutterwaveCheckoutPaymentRecord.tx_ref == tx_ref.strip(),
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Flutterwave payment '{tx_ref}' not found.")

    clean_st = status.strip().lower()
    if clean_st == "cancelled":
        rec.status = "CANCELLED"
        rec.verification_detail = "User cancelled hosted checkout."
        rec.updated_at = datetime.now(timezone.utc)
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="FLW_CHECKOUT_CANCELLED",
            resource=rec.tx_ref,
            outcome="CANCELLED",
        )
        db.commit()
        db.refresh(rec)
        return _serialize_flw_payment(rec)

    if not transaction_id:
        raise ValidationError("transaction_id is required to verify completed callback.")

    return verify_flutterwave_transaction(
        db,
        principal=principal,
        tx_ref=tx_ref,
        transaction_id=transaction_id,
        settings=settings,
        http_client=http_client,
        mock_verify_payload=mock_verify_payload,
    )


def handle_flutterwave_webhook(
    db: Session,
    *,
    verif_hash: str | None,
    payload: dict[str, Any],
    settings: Settings,
    http_client: httpx.Client | None = None,
    mock_verify_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = payload.get("data") or {}
    tx_ref = str(data.get("tx_ref") or "").strip()
    tx_id = str(data.get("id") or "").strip()
    if not tx_ref or not tx_id:
        raise ValidationError("Webhook payload missing data.tx_ref or data.id.")

    rec = db.execute(
        select(FlutterwaveCheckoutPaymentRecord).where(FlutterwaveCheckoutPaymentRecord.tx_ref == tx_ref)
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Flutterwave payment '{tx_ref}' not found.")

    creds = _resolve_flw_credentials(db, tenant_id=rec.tenant_id, settings=settings)
    expected_hash = creds["secret_hash"]
    if not expected_hash or not verif_hash or not hmac.compare_digest(verif_hash.strip(), expected_hash):
        append_audit_log(
            db,
            tenant_id=rec.tenant_id,
            actor="flutterwave_webhook",
            action="FLW_WEBHOOK_REJECTED",
            resource=tx_ref,
            outcome="INVALID_VERIF_HASH",
        )
        db.commit()
        raise AuthenticationError("Invalid or missing Flutterwave verif-hash signature.")

    rec.last_webhook_at = datetime.now(timezone.utc)
    db.flush()

    system_principal = Principal(
        user_id="system-webhook",
        username="flutterwave_webhook",
        tenant_id=rec.tenant_id,
        role="OWNER",
        jti="webhook",
    )
    return verify_flutterwave_transaction(
        db,
        principal=system_principal,
        tx_ref=tx_ref,
        transaction_id=tx_id,
        settings=settings,
        http_client=http_client,
        mock_verify_payload=mock_verify_payload,
    )


def list_flutterwave_payments(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FlutterwaveCheckoutPaymentRecord)
        .where(FlutterwaveCheckoutPaymentRecord.tenant_id == tenant_id)
        .order_by(FlutterwaveCheckoutPaymentRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_flw_payment(r) for r in rows]


def _serialize_flw_payment(r: FlutterwaveCheckoutPaymentRecord) -> dict[str, Any]:
    return {
        "payment_id": r.payment_id,
        "tx_ref": r.tx_ref,
        "idempotency_key": r.idempotency_key,
        "flw_transaction_id": r.flw_transaction_id,
        "amount": r.amount,
        "currency": r.currency,
        "payment_options": r.payment_options,
        "customer_email": r.customer_email,
        "customer_name": r.customer_name,
        "checkout_url": r.checkout_url,
        "environment": r.environment,
        "status": r.status,
        "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        "last_webhook_at": r.last_webhook_at.isoformat() if r.last_webhook_at else None,
        "verification_detail": r.verification_detail,
        "created_at": r.created_at.isoformat(),
    }
