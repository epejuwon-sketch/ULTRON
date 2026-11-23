"""Financial Command Center routes: revenue, expenses, budgets, investments, reserves, reports, and audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
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
