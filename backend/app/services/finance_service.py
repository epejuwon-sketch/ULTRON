"""Financial Command Center service: ledger, budgets, API/hosting/project costs, investments, reserves, owner distributions, and reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import contains_raw_payment_card_or_cvv
from app.db.models import (
    AuditLogRecord,
    FinancialBudget,
    FinancialInvestment,
    FinancialReserve,
    FinancialTransaction,
    LLMUsageLog,
    PaymentMethodRecord,
)
from app.db.repositories import append_audit_log
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.notification_service import create_notification

VALID_ENTRY_TYPES = frozenset(
    {
        "REVENUE",
        "EXPENSE",
        "API_SPEND",
        "HOSTING",
        "PROJECT_COST",
        "OWNER_DISTRIBUTION",
        "RESERVE_ALLOCATION",
    }
)

OUTFLOW_TYPES = frozenset({"EXPENSE", "API_SPEND", "HOSTING", "PROJECT_COST", "OWNER_DISTRIBUTION"})
VALID_CARD_BRANDS = frozenset({"VISA", "MASTERCARD", "VERVE", "AMEX"})
VALID_FINANCE_SCOPES = frozenset({"PERSONAL", "BUSINESS"})


def record_transaction(
    db: Session,
    *,
    principal: Principal,
    entry_type: str,
    category: str,
    amount_usd: float,
    description: str,
    currency: str = "USD",
    counterparty: str = "",
    project_id: str | None = None,
    scope: str = "BUSINESS",
    settings: Settings,
) -> dict[str, Any]:
    """Record a financial entry. Owner distributions or outflows above soft limit require ApprovalGate."""
    etype = entry_type.strip().upper()
    if etype not in VALID_ENTRY_TYPES:
        raise ValidationError(f"Unsupported financial entry_type '{etype}'.")
    if amount_usd <= 0:
        raise ValidationError("amount_usd must be positive.")
    clean_scope = scope.strip().upper()
    if clean_scope not in VALID_FINANCE_SCOPES:
        raise ValidationError("scope must be PERSONAL or BUSINESS.")
    if contains_raw_payment_card_or_cvv(description) or contains_raw_payment_card_or_cvv(counterparty):
        raise ValidationError("Raw payment card numbers or CVV values are strictly prohibited in financial records.")

    requires_gate = (
        etype == "OWNER_DISTRIBUTION"
        or (etype in OUTFLOW_TYPES and amount_usd > settings.approval_soft_limit_usd)
    )
    tx_id = f"ftx_{uuid.uuid4().hex[:16]}"
    tx = FinancialTransaction(
        tx_id=tx_id,
        tenant_id=principal.tenant_id,
        project_id=project_id,
        entry_type=etype,
        category=category.strip().lower(),
        amount_usd=round(float(amount_usd), 2),
        currency=currency.strip().upper(),
        counterparty=counterparty.strip(),
        description=description.strip(),
        scope=clean_scope,
        status="PENDING_APPROVAL" if requires_gate else "RECORDED",
        created_by=principal.username,
    )
    db.add(tx)
    db.flush()

    approval_payload: dict[str, Any] | None = None
    if requires_gate:
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type="FINANCIAL_TRANSACTION",
            reason=(
                f"{etype} of ${amount_usd:.2f} {tx.currency} ({category}) requires explicit authorization "
                "(no automated live payment rail is executed)."
            ),
            risk_level="HIGH",
            financial_amount_usd=amount_usd,
            resource_ref=tx_id,
            payload={
                "tx_id": tx_id,
                "entry_type": etype,
                "category": tx.category,
                "amount_usd": tx.amount_usd,
                "counterparty": tx.counterparty,
            },
            commit=False,
        )
        tx.approval_id = approval.approval_id
        approval_payload = serialize_approval(approval)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action=f"FINANCE_{etype}",
        resource=tx_id,
        outcome=f"STATUS={tx.status}|USD={tx.amount_usd:.2f}",
        metadata={"category": tx.category, "project_id": project_id},
    )

    # Check budget alerts on outflows
    if etype in OUTFLOW_TYPES:
        _check_budget_alerts(db, tenant_id=principal.tenant_id, category=tx.category)

    db.commit()
    db.refresh(tx)
    out = _serialize_tx(tx)
    out["approval"] = approval_payload
    out["payment_rail_executed"] = False
    return out


def _check_budget_alerts(db: Session, *, tenant_id: str, category: str) -> None:
    budgets = db.execute(
        select(FinancialBudget).where(
            FinancialBudget.tenant_id == tenant_id,
            FinancialBudget.category == category,
        )
    ).scalars().all()
    if not budgets:
        return
    spent = float(
        db.execute(
            select(func.coalesce(func.sum(FinancialTransaction.amount_usd), 0.0)).where(
                FinancialTransaction.tenant_id == tenant_id,
                FinancialTransaction.category == category,
                FinancialTransaction.entry_type.in_(list(OUTFLOW_TYPES)),
                FinancialTransaction.status.in_(["RECORDED", "APPROVED"]),
            )
        ).scalar_one()
    )
    for b in budgets:
        if b.limit_usd > 0:
            pct = (spent / b.limit_usd) * 100.0
            if pct >= b.alert_threshold_pct:
                create_notification(
                    db,
                    tenant_id=tenant_id,
                    severity="WARNING" if pct < 100 else "CRITICAL",
                    category="FINANCE_BUDGET",
                    title=f"Budget Alert: {b.name}",
                    message=f"Category '{category}' reached {pct:.1f}% of ${b.limit_usd:.2f} budget (${spent:.2f} spent).",
                    metadata={"budget_id": b.budget_id, "spent_usd": spent, "limit_usd": b.limit_usd},
                    commit=False,
                )


def list_transactions(
    db: Session,
    *,
    tenant_id: str,
    entry_type: str | None = None,
    project_id: str | None = None,
    scope: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(FinancialTransaction).where(FinancialTransaction.tenant_id == tenant_id)
    if entry_type:
        stmt = stmt.where(FinancialTransaction.entry_type == entry_type.upper())
    if project_id:
        stmt = stmt.where(FinancialTransaction.project_id == project_id)
    if scope:
        stmt = stmt.where(FinancialTransaction.scope == scope.strip().upper())
    rows = db.execute(stmt.order_by(FinancialTransaction.created_at.desc()).limit(limit)).scalars().all()
    return [_serialize_tx(r) for r in rows]


def create_budget(
    db: Session,
    *,
    principal: Principal,
    name: str,
    category: str,
    limit_usd: float,
    period: str = "MONTHLY",
    alert_threshold_pct: float = 80.0,
) -> dict[str, Any]:
    budget = FinancialBudget(
        budget_id=f"bdg_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        name=name.strip(),
        category=category.strip().lower(),
        period=period.strip().upper(),
        limit_usd=round(float(limit_usd), 2),
        alert_threshold_pct=float(alert_threshold_pct),
        created_by=principal.username,
    )
    db.add(budget)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_BUDGET_CREATED",
        resource=budget.budget_id,
        outcome=f"CAT={budget.category}|LIMIT={budget.limit_usd:.2f}",
    )
    db.commit()
    db.refresh(budget)
    return _serialize_budget(db, budget)


def list_budgets(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FinancialBudget)
        .where(FinancialBudget.tenant_id == tenant_id)
        .order_by(FinancialBudget.created_at.desc())
    ).scalars().all()
    return [_serialize_budget(db, r) for r in rows]


def upsert_investment(
    db: Session,
    *,
    principal: Principal,
    asset_name: str,
    asset_class: str,
    cost_basis_usd: float,
    current_value_usd: float,
    notes: str = "",
) -> dict[str, Any]:
    inv = FinancialInvestment(
        investment_id=f"inv_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        asset_name=asset_name.strip(),
        asset_class=asset_class.strip().upper(),
        cost_basis_usd=round(float(cost_basis_usd), 2),
        current_value_usd=round(float(current_value_usd), 2),
        notes=notes.strip(),
        created_by=principal.username,
    )
    db.add(inv)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_INVESTMENT_RECORDED",
        resource=inv.investment_id,
        outcome=f"{inv.asset_name}|VALUE={inv.current_value_usd:.2f}",
    )
    db.commit()
    db.refresh(inv)
    return _serialize_investment(inv)


def list_investments(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FinancialInvestment)
        .where(FinancialInvestment.tenant_id == tenant_id)
        .order_by(FinancialInvestment.updated_at.desc())
    ).scalars().all()
    return [_serialize_investment(r) for r in rows]


def upsert_reserve(
    db: Session,
    *,
    principal: Principal,
    name: str,
    balance_usd: float,
    target_usd: float = 0.0,
    currency: str = "USD",
    custodian: str = "Treasury",
) -> dict[str, Any]:
    res = FinancialReserve(
        reserve_id=f"rsv_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        name=name.strip(),
        currency=currency.strip().upper(),
        balance_usd=round(float(balance_usd), 2),
        target_usd=round(float(target_usd), 2),
        custodian=custodian.strip(),
    )
    db.add(res)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_RESERVE_RECORDED",
        resource=res.reserve_id,
        outcome=f"{res.name}|BAL={res.balance_usd:.2f}",
    )
    db.commit()
    db.refresh(res)
    return _serialize_reserve(res)


def list_reserves(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FinancialReserve)
        .where(FinancialReserve.tenant_id == tenant_id)
        .order_by(FinancialReserve.updated_at.desc())
    ).scalars().all()
    return [_serialize_reserve(r) for r in rows]


def generate_financial_report(db: Session, *, tenant_id: str, scope: str | None = None) -> dict[str, Any]:
    """Compute P&L, API/hosting/project spend breakdown, reserves, and investment totals."""
    stmt = select(FinancialTransaction).where(
        FinancialTransaction.tenant_id == tenant_id,
        FinancialTransaction.status.in_(["RECORDED", "APPROVED"]),
    )
    if scope:
        stmt = stmt.where(FinancialTransaction.scope == scope.strip().upper())
    txs = db.execute(stmt).scalars().all()

    by_type: dict[str, float] = {k: 0.0 for k in VALID_ENTRY_TYPES}
    by_scope: dict[str, dict[str, float]] = {
        "PERSONAL": {"revenue_usd": 0.0, "expenses_usd": 0.0},
        "BUSINESS": {"revenue_usd": 0.0, "expenses_usd": 0.0},
    }
    for t in txs:
        by_type[t.entry_type] = round(by_type.get(t.entry_type, 0.0) + t.amount_usd, 2)
        sc = t.scope if t.scope in by_scope else "BUSINESS"
        if t.entry_type == "REVENUE":
            by_scope[sc]["revenue_usd"] = round(by_scope[sc]["revenue_usd"] + t.amount_usd, 2)
        elif t.entry_type in OUTFLOW_TYPES:
            by_scope[sc]["expenses_usd"] = round(by_scope[sc]["expenses_usd"] + t.amount_usd, 2)

    llm_api_spend = float(
        db.execute(
            select(func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0)).where(
                LLMUsageLog.tenant_id == tenant_id
            )
        ).scalar_one()
    )
    total_revenue = by_type["REVENUE"]
    total_expenses = round(
        by_type["EXPENSE"]
        + by_type["API_SPEND"]
        + by_type["HOSTING"]
        + by_type["PROJECT_COST"]
        + llm_api_spend,
        2,
    )
    net_income = round(total_revenue - total_expenses, 2)

    investments = list_investments(db, tenant_id=tenant_id)
    reserves = list_reserves(db, tenant_id=tenant_id)

    pending_approvals = int(
        db.execute(
            select(func.count())
            .select_from(FinancialTransaction)
            .where(
                FinancialTransaction.tenant_id == tenant_id,
                FinancialTransaction.status == "PENDING_APPROVAL",
            )
        ).scalar_one()
    )

    return {
        "tenant_id": tenant_id,
        "scope_filter": scope.upper() if scope else "ALL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_revenue_usd": total_revenue,
        "total_expenses_usd": total_expenses,
        "tracked_neon_llm_spend_usd": round(llm_api_spend, 6),
        "net_income_usd": net_income,
        "owner_distributions_usd": by_type["OWNER_DISTRIBUTION"],
        "breakdown_by_entry_type": by_type,
        "breakdown_by_scope": by_scope,
        "total_reserves_usd": round(sum(r["balance_usd"] for r in reserves), 2),
        "total_investments_cost_basis_usd": round(sum(i["cost_basis_usd"] for i in investments), 2),
        "total_investments_current_value_usd": round(sum(i["current_value_usd"] for i in investments), 2),
        "pending_approval_transactions": pending_approvals,
        "live_payment_rail_connected": False,
    }


def add_payment_method(
    db: Session,
    *,
    principal: Principal,
    provider: str,
    provider_token_ref: str,
    brand: str,
    last4: str,
    exp_month: int,
    exp_year: int,
    cardholder_label: str = "",
    currency: str = "NGN",
    scope: str = "PERSONAL",
    is_preferred: bool = False,
) -> dict[str, Any]:
    """Store a tokenized payment method (masked last4 only — strictly rejects raw PAN or CVV)."""
    # Hard security guard against raw card numbers or CVV being passed in any field
    for val in (provider_token_ref, cardholder_label, last4):
        if contains_raw_payment_card_or_cvv(val):
            raise ValidationError("Raw payment card numbers (PAN) or CVV values are strictly rejected. Supply only provider token references and last4.")
    if not last4.isdigit() or len(last4) != 4:
        raise ValidationError("last4 must be exactly 4 digits.")
    clean_brand = brand.strip().upper()
    if clean_brand not in VALID_CARD_BRANDS:
        raise ValidationError(f"Unsupported card brand '{clean_brand}'. Supported: VISA, MASTERCARD, VERVE, AMEX.")
    clean_scope = scope.strip().upper()
    if clean_scope not in VALID_FINANCE_SCOPES:
        raise ValidationError("scope must be PERSONAL or BUSINESS.")

    if is_preferred:
        existing = db.execute(
            select(PaymentMethodRecord).where(
                PaymentMethodRecord.tenant_id == principal.tenant_id,
                PaymentMethodRecord.scope == clean_scope,
            )
        ).scalars().all()
        for pm in existing:
            pm.is_preferred = False

    rec = PaymentMethodRecord(
        payment_method_id=f"pm_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        provider=provider.strip().lower(),
        provider_token_ref=provider_token_ref.strip(),
        brand=clean_brand,
        last4=last4,
        exp_month=int(exp_month),
        exp_year=int(exp_year),
        cardholder_label=cardholder_label.strip()[:160],
        currency=currency.strip().upper()[:12],
        scope=clean_scope,
        is_preferred=is_preferred,
        status="ACTIVE",
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_PAYMENT_METHOD_ADDED",
        resource=rec.payment_method_id,
        outcome=f"{clean_brand} ****{last4} ({clean_scope})",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_payment_method(rec)


def list_payment_methods(
    db: Session, *, tenant_id: str, scope: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(PaymentMethodRecord).where(
        PaymentMethodRecord.tenant_id == tenant_id,
        PaymentMethodRecord.status == "ACTIVE",
    )
    if scope:
        stmt = stmt.where(PaymentMethodRecord.scope == scope.strip().upper())
    rows = db.execute(stmt.order_by(PaymentMethodRecord.is_preferred.desc(), PaymentMethodRecord.created_at.desc())).scalars().all()
    return [_serialize_payment_method(r) for r in rows]


def set_preferred_payment_method(
    db: Session, *, principal: Principal, payment_method_id: str
) -> dict[str, Any]:
    target = db.execute(
        select(PaymentMethodRecord).where(
            PaymentMethodRecord.payment_method_id == payment_method_id,
            PaymentMethodRecord.tenant_id == principal.tenant_id,
            PaymentMethodRecord.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if target is None:
        raise NotFoundError(f"Payment method '{payment_method_id}' not found.")

    siblings = db.execute(
        select(PaymentMethodRecord).where(
            PaymentMethodRecord.tenant_id == principal.tenant_id,
            PaymentMethodRecord.scope == target.scope,
        )
    ).scalars().all()
    for pm in siblings:
        pm.is_preferred = pm.payment_method_id == target.payment_method_id
    db.commit()
    db.refresh(target)
    return _serialize_payment_method(target)


def delete_payment_method(
    db: Session, *, principal: Principal, payment_method_id: str
) -> dict[str, Any]:
    target = db.execute(
        select(PaymentMethodRecord).where(
            PaymentMethodRecord.payment_method_id == payment_method_id,
            PaymentMethodRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if target is None:
        raise NotFoundError(f"Payment method '{payment_method_id}' not found.")
    target.status = "REMOVED"
    target.is_preferred = False
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_PAYMENT_METHOD_REMOVED",
        resource=target.payment_method_id,
        outcome=f"{target.brand} ****{target.last4}",
    )
    db.commit()
    return {"payment_method_id": target.payment_method_id, "status": "REMOVED"}


def generate_cashflow_forecast(db: Session, *, tenant_id: str, months: int = 3) -> dict[str, Any]:
    """Compute a conservative linear cash-flow projection strictly from recorded ledger data."""
    report = generate_financial_report(db, tenant_id=tenant_id)
    rev = report["total_revenue_usd"]
    exp = report["total_expenses_usd"]
    net = report["net_income_usd"]
    reserves = report["total_reserves_usd"]
    runway_months = round(reserves / exp, 2) if exp > 0 else None
    projections = []
    running_balance = reserves
    for m in range(1, max(1, min(12, months)) + 1):
        running_balance = round(running_balance + net, 2)
        projections.append(
            {
                "month_offset": m,
                "projected_revenue_usd": rev,
                "projected_expenses_usd": exp,
                "projected_net_usd": net,
                "projected_reserve_balance_usd": running_balance,
            }
        )
    return {
        "basis": "RECORDED_LEDGER_DATA_ONLY",
        "current_reserves_usd": reserves,
        "monthly_net_baseline_usd": net,
        "estimated_runway_months": runway_months,
        "projections": projections,
    }


def list_financial_audit(db: Session, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.execute(
        select(AuditLogRecord)
        .where(
            AuditLogRecord.tenant_id == tenant_id,
            AuditLogRecord.action.like("FINANCE_%"),
        )
        .order_by(AuditLogRecord.seq.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "seq": r.seq,
            "event_id": r.event_id,
            "actor": r.actor,
            "action": r.action,
            "resource": r.resource,
            "outcome": r.outcome,
            "entry_hash": r.entry_hash,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def _serialize_tx(t: FinancialTransaction) -> dict[str, Any]:
    return {
        "tx_id": t.tx_id,
        "tenant_id": t.tenant_id,
        "project_id": t.project_id,
        "entry_type": t.entry_type,
        "category": t.category,
        "amount_usd": t.amount_usd,
        "currency": t.currency,
        "counterparty": t.counterparty,
        "description": t.description,
        "scope": t.scope,
        "status": t.status,
        "approval_id": t.approval_id,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat(),
    }


def _serialize_payment_method(pm: PaymentMethodRecord) -> dict[str, Any]:
    return {
        "payment_method_id": pm.payment_method_id,
        "provider": pm.provider,
        "brand": pm.brand,
        "masked_number": f"**** **** **** {pm.last4}",
        "last4": pm.last4,
        "exp_month": pm.exp_month,
        "exp_year": pm.exp_year,
        "cardholder_label": pm.cardholder_label,
        "currency": pm.currency,
        "scope": pm.scope,
        "is_preferred": pm.is_preferred,
        "status": pm.status,
        "created_at": pm.created_at.isoformat(),
    }


def _serialize_budget(db: Session, b: FinancialBudget) -> dict[str, Any]:
    spent = float(
        db.execute(
            select(func.coalesce(func.sum(FinancialTransaction.amount_usd), 0.0)).where(
                FinancialTransaction.tenant_id == b.tenant_id,
                FinancialTransaction.category == b.category,
                FinancialTransaction.entry_type.in_(list(OUTFLOW_TYPES)),
                FinancialTransaction.status.in_(["RECORDED", "APPROVED"]),
            )
        ).scalar_one()
    )
    util_pct = round((spent / b.limit_usd) * 100.0, 2) if b.limit_usd > 0 else 0.0
    return {
        "budget_id": b.budget_id,
        "name": b.name,
        "category": b.category,
        "period": b.period,
        "limit_usd": b.limit_usd,
        "spent_usd": round(spent, 2),
        "utilization_pct": util_pct,
        "alert_threshold_pct": b.alert_threshold_pct,
        "alert_triggered": util_pct >= b.alert_threshold_pct,
        "created_at": b.created_at.isoformat(),
    }


def _serialize_investment(i: FinancialInvestment) -> dict[str, Any]:
    gain = round(i.current_value_usd - i.cost_basis_usd, 2)
    return {
        "investment_id": i.investment_id,
        "asset_name": i.asset_name,
        "asset_class": i.asset_class,
        "cost_basis_usd": i.cost_basis_usd,
        "current_value_usd": i.current_value_usd,
        "unrealized_pnl_usd": gain,
        "notes": i.notes,
        "updated_at": i.updated_at.isoformat(),
    }


def _serialize_reserve(r: FinancialReserve) -> dict[str, Any]:
    pct = round((r.balance_usd / r.target_usd) * 100.0, 2) if r.target_usd > 0 else 100.0
    return {
        "reserve_id": r.reserve_id,
        "name": r.name,
        "currency": r.currency,
        "balance_usd": r.balance_usd,
        "target_usd": r.target_usd,
        "funded_pct": pct,
        "custodian": r.custodian,
        "updated_at": r.updated_at.isoformat(),
    }
