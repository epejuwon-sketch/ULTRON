"""Financial Command Center service: ledger, budgets, API/hosting/project costs, investments, reserves, owner distributions, and reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.core.permissions import Principal
from app.db.models import (
    AuditLogRecord,
    FinancialBudget,
    FinancialInvestment,
    FinancialReserve,
    FinancialTransaction,
    LLMUsageLog,
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
    settings: Settings,
) -> dict[str, Any]:
    """Record a financial entry. Owner distributions or outflows above soft limit require ApprovalGate."""
    etype = entry_type.strip().upper()
    if etype not in VALID_ENTRY_TYPES:
        raise ValidationError(f"Unsupported financial entry_type '{etype}'.")
    if amount_usd <= 0:
        raise ValidationError("amount_usd must be positive.")

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
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(FinancialTransaction).where(FinancialTransaction.tenant_id == tenant_id)
    if entry_type:
        stmt = stmt.where(FinancialTransaction.entry_type == entry_type.upper())
    if project_id:
        stmt = stmt.where(FinancialTransaction.project_id == project_id)
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


def generate_financial_report(db: Session, *, tenant_id: str) -> dict[str, Any]:
    """Compute P&L, API/hosting/project spend breakdown, reserves, and investment totals."""
    txs = db.execute(
        select(FinancialTransaction).where(
            FinancialTransaction.tenant_id == tenant_id,
            FinancialTransaction.status.in_(["RECORDED", "APPROVED"]),
        )
    ).scalars().all()

    by_type: dict[str, float] = {k: 0.0 for k in VALID_ENTRY_TYPES}
    for t in txs:
        by_type[t.entry_type] = round(by_type.get(t.entry_type, 0.0) + t.amount_usd, 2)

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
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_revenue_usd": total_revenue,
        "total_expenses_usd": total_expenses,
        "tracked_neon_llm_spend_usd": round(llm_api_spend, 6),
        "net_income_usd": net_income,
        "owner_distributions_usd": by_type["OWNER_DISTRIBUTION"],
        "breakdown_by_entry_type": by_type,
        "total_reserves_usd": round(sum(r["balance_usd"] for r in reserves), 2),
        "total_investments_cost_basis_usd": round(sum(i["cost_basis_usd"] for i in investments), 2),
        "total_investments_current_value_usd": round(sum(i["current_value_usd"] for i in investments), 2),
        "pending_approval_transactions": pending_approvals,
        "live_payment_rail_connected": False,
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
        "status": t.status,
        "approval_id": t.approval_id,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat(),
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
