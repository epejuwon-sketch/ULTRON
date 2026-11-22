"""Financial Command Center routes: revenue, expenses, budgets, investments, reserves, reports, and audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
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
