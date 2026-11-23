"""Financial Command Center routes: revenue, expenses, budgets, investments, reserves, reports, and audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import (
    CreateBudgetRequest,
    CreatePaymentMethodRequest,
    RecordInvestmentRequest,
    RecordReserveRequest,
    RecordTransactionRequest,
)
from app.services.finance_cards_service import (
    SUPPORTED_CARD_LINK_PROVIDERS,
    create_card,
    delete_card,
    list_cards,
    preview_sanitized_card_image,
    process_and_attach_card_image,
    update_card,
    verify_card_provider_authorization,
)
from app.services.finance_service import (
    add_payment_method,
    create_budget,
    delete_payment_method,
    generate_cashflow_forecast,
    generate_financial_report,
    list_budgets,
    list_financial_audit,
    list_investments,
    list_payment_methods,
    list_reserves,
    list_transactions,
    record_transaction,
    set_preferred_payment_method,
    upsert_investment,
    upsert_reserve,
)

router = APIRouter(prefix="/api/v1/finance", tags=["Financial Command Center"])


class CreateCardRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=120)
    issuer: str = Field(default="Custom", max_length=120)
    network: str = Field(default="", max_length=32)
    card_type: str = Field(default="VIRTUAL", max_length=32)
    scope: str = Field(default="BUSINESS", max_length=16)
    background_style: str = Field(default="emerald-obsidian", max_length=64)
    accent_color: str = Field(default="#10b981", max_length=24)
    visual_effect: str = Field(default="glass", max_length=32)
    provider_key: str | None = Field(default=None, max_length=64)
    provider_token_ref: str | None = Field(default=None, max_length=160)
    is_preferred: bool = False


class UpdateCardRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=120)
    issuer: str | None = Field(default=None, max_length=120)
    network: str | None = Field(default=None, max_length=32)
    card_type: str | None = Field(default=None, max_length=32)
    scope: str | None = Field(default=None, max_length=16)
    background_style: str | None = Field(default=None, max_length=64)
    accent_color: str | None = Field(default=None, max_length=24)
    visual_effect: str | None = Field(default=None, max_length=32)
    image_crop: dict | None = None
    display_order: int | None = None
    is_preferred: bool | None = None
    provider_key: str | None = Field(default=None, max_length=64)
    provider_token_ref: str | None = Field(default=None, max_length=160)


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def api_record_transaction(
    body: RecordTransactionRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return record_transaction(
        db,
        principal=principal,
        entry_type=body.entry_type,
        category=body.category,
        amount_usd=body.amount_usd,
        description=body.description,
        currency=body.currency,
        counterparty=body.counterparty,
        project_id=body.project_id,
        scope=body.scope,
        settings=settings,
    )


@router.get("/transactions")
def api_list_transactions(
    entry_type: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_transactions(
        db,
        tenant_id=principal.tenant_id,
        entry_type=entry_type,
        project_id=project_id,
        scope=scope,
    )
    return {"total": len(items), "transactions": items}


@router.post("/payment-methods", status_code=status.HTTP_201_CREATED)
def api_add_payment_method(
    body: CreatePaymentMethodRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return add_payment_method(
        db,
        principal=principal,
        provider=body.provider,
        provider_token_ref=body.provider_token_ref,
        brand=body.brand,
        last4=body.last4,
        exp_month=body.exp_month,
        exp_year=body.exp_year,
        cardholder_label=body.cardholder_label,
        currency=body.currency,
        scope=body.scope,
        is_preferred=body.is_preferred,
    )


@router.get("/payment-methods")
def api_list_payment_methods(
    scope: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_payment_methods(db, tenant_id=principal.tenant_id, scope=scope)
    return {
        "total": len(items),
        "payment_methods": items,
        "pci_policy": "TOKENIZED_MASKED_ONLY_NO_RAW_PAN_OR_CVV",
    }


@router.patch("/payment-methods/{payment_method_id}/preferred")
def api_set_preferred_payment_method(
    payment_method_id: str,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return set_preferred_payment_method(db, principal=principal, payment_method_id=payment_method_id)


@router.delete("/payment-methods/{payment_method_id}")
def api_delete_payment_method(
    payment_method_id: str,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return delete_payment_method(db, principal=principal, payment_method_id=payment_method_id)


@router.post("/budgets", status_code=status.HTTP_201_CREATED)
def api_create_budget(
    body: CreateBudgetRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return create_budget(
        db,
        principal=principal,
        name=body.name,
        category=body.category,
        limit_usd=body.limit_usd,
        period=body.period,
        alert_threshold_pct=body.alert_threshold_pct,
    )


@router.get("/budgets")
def api_list_budgets(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_budgets(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "budgets": items}


@router.post("/investments", status_code=status.HTTP_201_CREATED)
def api_record_investment(
    body: RecordInvestmentRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return upsert_investment(
        db,
        principal=principal,
        asset_name=body.asset_name,
        asset_class=body.asset_class,
        cost_basis_usd=body.cost_basis_usd,
        current_value_usd=body.current_value_usd,
        notes=body.notes,
    )


@router.get("/investments")
def api_list_investments(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_investments(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "investments": items}


@router.post("/reserves", status_code=status.HTTP_201_CREATED)
def api_record_reserve(
    body: RecordReserveRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return upsert_reserve(
        db,
        principal=principal,
        name=body.name,
        balance_usd=body.balance_usd,
        target_usd=body.target_usd,
        currency=body.currency,
        custodian=body.custodian,
    )


@router.get("/reserves")
def api_list_reserves(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_reserves(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "reserves": items}


@router.get("/reports/summary")
def api_financial_summary(
    scope: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    return generate_financial_report(db, tenant_id=principal.tenant_id, scope=scope)


@router.get("/forecast")
def api_financial_forecast(
    months: int = Query(default=3, ge=1, le=12),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    return generate_cashflow_forecast(db, tenant_id=principal.tenant_id, months=months)


@router.get("/audit")
def api_financial_audit(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_financial_audit(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "audit_entries": items}


@router.get("/cards")
def api_list_cards(
    scope: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_cards(db, tenant_id=principal.tenant_id, scope=scope)
    return {
        "total": len(items),
        "cards": items,
        "supported_providers": sorted(SUPPORTED_CARD_LINK_PROVIDERS.keys()),
        "pci_policy": "DISPLAY_BRANDING_AND_TOKEN_REF_ONLY_NO_RAW_PAN_CVV_PIN",
    }


@router.post("/cards", status_code=status.HTTP_201_CREATED)
def api_create_card(
    body: CreateCardRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return create_card(
        db,
        principal=principal,
        nickname=body.nickname,
        issuer=body.issuer,
        network=body.network,
        card_type=body.card_type,
        scope=body.scope,
        background_style=body.background_style,
        accent_color=body.accent_color,
        visual_effect=body.visual_effect,
        provider_key=body.provider_key,
        provider_token_ref=body.provider_token_ref,
        is_preferred=body.is_preferred,
    )


@router.patch("/cards/{card_id}")
def api_update_card(
    card_id: str,
    body: UpdateCardRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return update_card(
        db,
        principal=principal,
        card_id=card_id,
        updates=body.model_dump(exclude_unset=True),
    )


@router.post("/cards/{card_id}/image/preview")
async def api_preview_card_image(
    card_id: str,
    file: UploadFile = File(...),
    redaction_mode: str = Form(default="standard"),
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    raw = await file.read()
    return preview_sanitized_card_image(
        db,
        principal=principal,
        card_id=card_id,
        raw_bytes=raw,
        redaction_mode=redaction_mode,
    )


@router.post("/cards/{card_id}/image")
async def api_upload_card_image(
    card_id: str,
    file: UploadFile = File(...),
    redaction_mode: str = Form(default="standard"),
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw = await file.read()
    return process_and_attach_card_image(
        db,
        principal=principal,
        settings=settings,
        card_id=card_id,
        raw_bytes=raw,
        redaction_mode=redaction_mode,
    )


@router.delete("/cards/{card_id}")
def api_delete_card(
    card_id: str,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    return delete_card(db, principal=principal, card_id=card_id)


@router.post("/cards/{card_id}/verify-provider")
def api_verify_card_provider(
    card_id: str,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return verify_card_provider_authorization(
        db,
        principal=principal,
        card_id=card_id,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# UBA Verve Direct Integration (Developer Zone Sandbox & Capability Governance)
# ---------------------------------------------------------------------------
class UbaVerifyRequest(BaseModel):
    use_sandbox_mock: bool = False


class UbaAccountQueryRequest(BaseModel):
    account_ref: str = Field(min_length=3, max_length=64)
    use_sandbox_mock: bool = False


class UbaFinancialActionRequest(BaseModel):
    capability: str = Field(min_length=4, max_length=32)
    card_id: str = Field(min_length=3, max_length=64)
    amount_ngn: float = Field(gt=0)
    counterparty: str = Field(min_length=2, max_length=160)


@router.get("/uba-verve/status")
def api_uba_verve_status(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.uba_verve_adapter import get_uba_verve_status

    return get_uba_verve_status(db, principal=principal, settings=settings)


@router.post("/uba-verve/verify")
def api_uba_verve_verify(
    body: UbaVerifyRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.uba_verve_adapter import verify_uba_verve_connection

    return verify_uba_verve_connection(
        db,
        principal=principal,
        settings=settings,
        use_sandbox_mock=body.use_sandbox_mock,
    )


@router.post("/uba-verve/balance")
def api_uba_verve_balance(
    body: UbaAccountQueryRequest,
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.uba_verve_adapter import query_uba_account_balance

    return query_uba_account_balance(
        db,
        principal=principal,
        account_ref=body.account_ref,
        settings=settings,
        use_sandbox_mock=body.use_sandbox_mock,
    )


@router.post("/uba-verve/transactions")
def api_uba_verve_transactions(
    body: UbaAccountQueryRequest,
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.uba_verve_adapter import query_uba_account_transactions

    return query_uba_account_transactions(
        db,
        principal=principal,
        account_ref=body.account_ref,
        settings=settings,
        use_sandbox_mock=body.use_sandbox_mock,
    )


@router.post("/uba-verve/action")
def api_uba_verve_action(
    body: UbaFinancialActionRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.uba_verve_adapter import request_uba_financial_action

    return request_uba_financial_action(
        db,
        principal=principal,
        capability=body.capability,
        card_id=body.card_id,
        amount_ngn=body.amount_ngn,
        counterparty=body.counterparty,
        settings=settings,
    )


@router.post("/uba-verve/revoke")
def api_uba_verve_revoke(
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.uba_verve_adapter import revoke_uba_verve_consent

    return revoke_uba_verve_consent(db, principal=principal)


# ---------------------------------------------------------------------------
# Flutterwave Sandbox Integration (Hosted Checkout, Callback, Webhook & Verify)
# ---------------------------------------------------------------------------
class FlutterwaveCheckoutRequest(BaseModel):
    amount: float = Field(gt=0)
    currency: str = Field(default="NGN", max_length=12)
    customer_email: str = Field(min_length=5, max_length=255)
    customer_name: str = Field(default="", max_length=160)
    redirect_url: str = Field(default="https://ultron.local/finance/flutterwave/callback", max_length=500)
    payment_options: str = Field(default="card,banktransfer,ussd", max_length=120)
    idempotency_key: str | None = Field(default=None, max_length=120)
    use_sandbox_mock: bool = False


class FlutterwaveVerifyRequest(BaseModel):
    tx_ref: str = Field(min_length=4, max_length=120)
    transaction_id: str = Field(min_length=1, max_length=64)


@router.get("/flutterwave/status")
def api_flutterwave_status(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.flutterwave_service import get_flutterwave_status

    return get_flutterwave_status(db, principal=principal, settings=settings)


@router.get("/flutterwave/payments")
def api_list_flutterwave_payments(
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.flutterwave_service import list_flutterwave_payments

    items = list_flutterwave_payments(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "payments": items}


@router.post("/flutterwave/checkout", status_code=status.HTTP_201_CREATED)
def api_flutterwave_checkout(
    body: FlutterwaveCheckoutRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.flutterwave_service import initiate_hosted_checkout

    return initiate_hosted_checkout(
        db,
        principal=principal,
        amount=body.amount,
        currency=body.currency,
        customer_email=body.customer_email,
        customer_name=body.customer_name,
        redirect_url=body.redirect_url,
        payment_options=body.payment_options,
        idempotency_key=body.idempotency_key,
        settings=settings,
        use_sandbox_mock=body.use_sandbox_mock,
    )


@router.get("/flutterwave/callback")
def api_flutterwave_callback(
    tx_ref: str = Query(..., min_length=4),
    status_param: str = Query(..., alias="status"),
    transaction_id: str | None = Query(default=None),
    principal: Principal = Depends(require_perm("finance:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.flutterwave_service import handle_flutterwave_callback

    return handle_flutterwave_callback(
        db,
        principal=principal,
        tx_ref=tx_ref,
        status=status_param,
        transaction_id=transaction_id,
        settings=settings,
    )


@router.post("/flutterwave/verify")
def api_flutterwave_verify(
    body: FlutterwaveVerifyRequest,
    principal: Principal = Depends(require_perm("finance:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.flutterwave_service import verify_flutterwave_transaction

    return verify_flutterwave_transaction(
        db,
        principal=principal,
        tx_ref=body.tx_ref,
        transaction_id=body.transaction_id,
        settings=settings,
    )


@router.post("/flutterwave/webhook")
async def api_flutterwave_webhook(
    request: Request,
    verif_hash: str | None = Header(default=None, alias="verif-hash"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.flutterwave_service import handle_flutterwave_webhook

    payload = await request.json()
    return handle_flutterwave_webhook(
        db,
        verif_hash=verif_hash,
        payload=payload,
        settings=settings,
    )

