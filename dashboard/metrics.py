"""Unified dashboard metric aggregates (scope-aware)."""

from __future__ import annotations

from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from dashboard import selectors


def aggregate_giving_and_ie_mtd(finance_church_ids, month_start_date):
    """MTD tithe, combined, income, expense, net for a set of churches."""
    if not finance_church_ids:
        zeros = Decimal("0")
        return {
            "mtd_tithe": zeros,
            "mtd_combined": zeros,
            "mtd_income": zeros,
            "mtd_expense": zeros,
            "mtd_net": zeros,
        }
    mtd_lines = selectors.mtd_lines_for_churches(list(finance_church_ids), month_start_date)
    mtd_tithe, mtd_combined = selectors.sum_tithe_combined_mtd(mtd_lines)
    mtd_totals = selectors.sum_line_amounts_by_types(mtd_lines, ("INCOME", "EXPENSE"))
    mtd_income = mtd_totals["INCOME"]
    mtd_expense = mtd_totals["EXPENSE"]
    return {
        "mtd_tithe": mtd_tithe,
        "mtd_combined": mtd_combined,
        "mtd_income": mtd_income,
        "mtd_expense": mtd_expense,
        "mtd_net": mtd_income - mtd_expense,
    }


def aggregate_remittance_mtd(manageable_qs, finance_church_ids, month_start_date) -> Decimal:
    if not finance_church_ids:
        return Decimal("0")
    churches = list(manageable_qs.filter(pk__in=finance_church_ids))
    return selectors.sum_remittance_payable_mtd_for_churches(churches, month_start_date)


def aggregate_member_count(church_ids) -> int:
    if not church_ids:
        return 0
    return selectors.active_member_count_for_churches(list(church_ids))


def build_executive_finance_bundle(
    *,
    church_ids,
    finance_church_ids,
    finance_scope_label,
    manageable,
    month_start_date,
    period_label,
    compliance,
    finance_scope="scope",
):
    """Shared KPI dict for executive strip and widgets."""
    agg = aggregate_giving_and_ie_mtd(finance_church_ids, month_start_date)
    mtd_remit = aggregate_remittance_mtd(manageable, finance_church_ids, month_start_date)
    pending_txn = selectors.pending_transactions_for_churches_count(list(church_ids))
    member_count = aggregate_member_count(church_ids)
    return {
        "period_label": period_label,
        "finance_scope": finance_scope,
        "finance_scope_label": finance_scope_label,
        "church_count": len(church_ids),
        "district_count": manageable.values("district_id").distinct().count() if church_ids else 0,
        "member_count": member_count,
        "mtd_tithe": agg["mtd_tithe"],
        "mtd_combined": agg["mtd_combined"],
        "mtd_income": agg["mtd_income"],
        "mtd_expense": agg["mtd_expense"],
        "mtd_remittance_payable": mtd_remit,
        "mtd_net": agg["mtd_net"],
        "pending_transactions": pending_txn,
        "overdue_remittances": compliance.get("overdue_count", 0),
        "locked_periods": compliance.get("locked_periods", 0),
        "action_items": pending_txn + compliance.get("overdue_count", 0),
    }


def income_expense_trend_chart(finance_church_ids, now=None, months=6):
    """Six-month income vs expense series for chart.js."""
    import json

    now = now or timezone.now()
    if not finance_church_ids:
        labels = []
        return json.dumps(labels), json.dumps([]), json.dumps([])

    transactions = selectors.approved_transactions(
        selectors.transactions_for_church_ids(list(finance_church_ids))
    )
    all_time_lines = selectors.lines_for_transactions(transactions)
    six_months_ago = (now - relativedelta(months=months - 1)).replace(day=1)
    six_months_ago_date = (
        timezone.localdate(six_months_ago) if timezone.is_aware(six_months_ago) else six_months_ago.date()
    )
    trend_qs = selectors.income_expense_trend_aggregates(all_time_lines, six_months_ago_date)

    trend_dict = {}
    for i in range(months):
        m_dt = (now - relativedelta(months=i)).replace(day=1)
        label = m_dt.strftime("%b %Y")
        trend_dict[label] = {"INCOME": 0.0, "EXPENSE": 0.0}

    for row in trend_qs:
        month_val = row["month"]
        if not month_val:
            continue
        label = month_val.strftime("%b %Y")
        acc_type = row["account__account_type"]
        if label in trend_dict and acc_type in trend_dict[label]:
            trend_dict[label][acc_type] += float(abs(row["total"] or 0))

    trend_labels = list(reversed(list(trend_dict.keys())))
    income_data = [trend_dict[m]["INCOME"] for m in trend_labels]
    expense_data = [trend_dict[m]["EXPENSE"] for m in trend_labels]
    return json.dumps(trend_labels), json.dumps(income_data), json.dumps(expense_data)
