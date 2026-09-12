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
    mtd_lines = selectors.lines_for_churches_calendar_month(list(finance_church_ids), month_start_date)
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


def aggregate_giving_calendar_month(finance_church_ids, month_start_date):
    """Full calendar month totals (prior-month KPI comparison)."""
    if not finance_church_ids:
        zeros = Decimal("0")
        return {
            "mtd_tithe": zeros,
            "mtd_combined": zeros,
            "mtd_income": zeros,
            "mtd_expense": zeros,
            "mtd_net": zeros,
        }
    lines = selectors.lines_for_churches_calendar_month(list(finance_church_ids), month_start_date)
    mtd_tithe, mtd_combined = selectors.sum_tithe_combined_mtd(lines)
    mtd_totals = selectors.sum_line_amounts_by_types(lines, ("INCOME", "EXPENSE"))
    mtd_income = mtd_totals["INCOME"]
    mtd_expense = mtd_totals["EXPENSE"]
    return {
        "mtd_tithe": mtd_tithe,
        "mtd_combined": mtd_combined,
        "mtd_income": mtd_income,
        "mtd_expense": mtd_expense,
        "mtd_net": mtd_income - mtd_expense,
    }


def pct_change(current: Decimal, previous: Decimal):
    if previous == 0:
        if current == 0:
            return None
        return 100.0
    return float((current - previous) / previous * 100)


def attach_finance_deltas(bundle, finance_church_ids, month_start_date):
    """Add vs-prior-month % deltas on key money KPIs."""
    if not finance_church_ids:
        return bundle
    prior_start = (month_start_date - relativedelta(months=1)).replace(day=1)
    prior = aggregate_giving_calendar_month(finance_church_ids, prior_start)
    for key in ("mtd_tithe", "mtd_combined", "mtd_income", "mtd_expense", "mtd_net"):
        bundle[f"{key}_delta_pct"] = pct_change(bundle[key], prior[key])
    bundle["compare_label"] = prior_start.strftime("%b %Y")
    return bundle


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
    result = {
        "period_label": period_label,
        "month_start_date": month_start_date,
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
    return attach_finance_deltas(result, finance_church_ids, month_start_date)


def income_expense_trend_chart(finance_church_ids, now=None, months=12):
    """Monthly income, tithe, and combined series for the home finance chart."""
    import json

    now = now or timezone.now()
    empty_json = json.dumps([])
    empty = {
        "labels": empty_json,
        "income": empty_json,
        "expense": empty_json,
        "income_cumulative": empty_json,
        "tithe": empty_json,
        "tithe_cumulative": empty_json,
        "combined": empty_json,
        "combined_cumulative": empty_json,
    }
    if not finance_church_ids:
        return empty

    from dashboard.selectors import COMBINED_GIVING_TYPES, TITHE_GIVING_TYPES

    transactions = selectors.approved_transactions(
        selectors.transactions_for_church_ids(list(finance_church_ids))
    )
    all_time_lines = selectors.lines_for_transactions(transactions)
    six_months_ago = (now - relativedelta(months=months - 1)).replace(day=1)
    six_months_ago_date = (
        timezone.localdate(six_months_ago) if timezone.is_aware(six_months_ago) else six_months_ago.date()
    )
    type_set = ["INCOME", "EXPENSE", *TITHE_GIVING_TYPES, *COMBINED_GIVING_TYPES]
    trend_qs = selectors.trend_aggregates_by_account_types(all_time_lines, six_months_ago_date, type_set)

    buckets = {}
    for i in range(months):
        m_dt = (now - relativedelta(months=i)).replace(day=1)
        label = m_dt.strftime("%b %Y")
        buckets[label] = {"INCOME": 0.0, "EXPENSE": 0.0, "TITHE": 0.0, "COMBINED": 0.0}

    tithe_types = set(TITHE_GIVING_TYPES)
    combined_types = set(COMBINED_GIVING_TYPES)
    for row in trend_qs:
        month_val = row["month"]
        if not month_val:
            continue
        label = month_val.strftime("%b %Y")
        if label not in buckets:
            continue
        acc_type = row["account__account_type"]
        amount = float(abs(row["total"] or 0))
        if acc_type in ("INCOME", "EXPENSE"):
            buckets[label][acc_type] += amount
        if acc_type in tithe_types:
            buckets[label]["TITHE"] += amount
        if acc_type in combined_types:
            buckets[label]["COMBINED"] += amount

    trend_labels = list(reversed(list(buckets.keys())))

    def _series(key):
        return [round(buckets[m][key], 2) for m in trend_labels]

    def _cumulative(values):
        running = 0.0
        out = []
        for amount in values:
            running += amount
            out.append(round(running, 2))
        return out

    income_data = _series("INCOME")
    expense_data = _series("EXPENSE")
    tithe_data = _series("TITHE")
    combined_data = _series("COMBINED")
    return {
        "labels": json.dumps(trend_labels),
        "income": json.dumps(income_data),
        "expense": json.dumps(expense_data),
        "income_cumulative": json.dumps(_cumulative(income_data)),
        "tithe": json.dumps(tithe_data),
        "tithe_cumulative": json.dumps(_cumulative(tithe_data)),
        "combined": json.dumps(combined_data),
        "combined_cumulative": json.dumps(_cumulative(combined_data)),
    }
