"""Monthly income and expense matrix for End of Year and income views."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear

from transactions.models import TransactionLine

INCOME_TYPES = {"TITHE", "COMBINED", "INCOME", "COMBINED_RETENTION"}
EXPENSE_TYPES = {"EXPENSE", "SALARY_EXPENSE", "EMPLOYER_SSNIT_EXPENSE", "DEPRECIATION_EXPENSE"}

GRID_TITLE = "Monthly income and expense (posted books)"
GRID_LABELS = {
    "account_column": "Account",
    "total_column": "Total",
    "income_section": "Income",
    "expense_section": "Expense",
    "total_income": "Total receipts",
    "total_expense": "Total expense",
    "net_row": "Net surplus / (deficit)",
    "net_total": "Net total",
}


def _month_columns(start: date, end: date) -> list[dict]:
    columns = []
    cursor = start.replace(day=1)
    while cursor <= end:
        last_dom = monthrange(cursor.year, cursor.month)[1]
        month_end = min(end, date(cursor.year, cursor.month, last_dom))
        month_start = max(start, cursor)
        columns.append(
            {
                "key": f"{cursor.year}-{cursor.month:02d}",
                "label": cursor.strftime("%b"),
                "year": cursor.year,
                "month": cursor.month,
                "start": month_start,
                "end": month_end,
            }
        )
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return columns


def _display_amount(account_type: str, signed_total: Decimal) -> Decimal:
    """Present activity as a positive magnitude (income statement convention)."""
    if signed_total is None:
        return Decimal("0")
    return abs(Decimal(str(signed_total)))


def build_profit_loss_grid(churches, start: date, end: date) -> dict:
    """
    Posted-books matrix: income and expense accounts × fiscal months in range.

    Amounts use approved, non-voided journal line totals per calendar month.
    """
    columns = _month_columns(start, end)
    if not columns or not churches.exists():
        return {
            "title": GRID_TITLE,
            "subtitle": "",
            "labels": GRID_LABELS,
            "columns": [],
            "income_rows": [],
            "expense_rows": [],
            "income_totals": [],
            "expense_totals": [],
            "net_totals": [],
            "grand_income": Decimal("0"),
            "grand_expense": Decimal("0"),
            "grand_net": Decimal("0"),
        }

    qs = (
        TransactionLine.objects.filter(
            transaction__church__in=churches,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            transaction__date__gte=start,
            transaction__date__lte=end,
            account__account_type__in=list(INCOME_TYPES | EXPENSE_TYPES),
        )
        .annotate(
            month=ExtractMonth("transaction__date"),
            year=ExtractYear("transaction__date"),
        )
        .values("account_id", "account__name", "account__account_type", "year", "month")
        .annotate(total=Sum("amount"))
    )

    bucket: dict[tuple, dict] = {}
    for row in qs:
        acc_id = row["account_id"]
        acc_type = row["account__account_type"]
        key = (acc_id, row["account__name"], acc_type)
        entry = bucket.setdefault(
            key,
            {
                "account_id": str(acc_id),
                "account_name": row["account__name"],
                "account_type": acc_type,
                "cells": {col["key"]: Decimal("0") for col in columns},
                "total": Decimal("0"),
            },
        )
        col_key = f"{row['year']}-{row['month']:02d}"
        if col_key in entry["cells"]:
            display = _display_amount(acc_type, row["total"])
            entry["cells"][col_key] = display
            entry["total"] += display

    income_rows = []
    expense_rows = []
    for (_aid, _name, acc_type), entry in sorted(bucket.items(), key=lambda x: x[0][1]):
        row = {
            "account_id": entry["account_id"],
            "account_name": entry["account_name"],
            "cells": [entry["cells"][c["key"]] for c in columns],
            "total": entry["total"],
        }
        if acc_type in INCOME_TYPES:
            income_rows.append(row)
        elif acc_type in EXPENSE_TYPES:
            expense_rows.append(row)

    def _column_totals(rows):
        if not columns:
            return []
        totals = [Decimal("0") for _ in columns]
        grand = Decimal("0")
        for row in rows:
            grand += row["total"]
            for idx, val in enumerate(row["cells"]):
                totals[idx] += val
        return totals, grand

    income_totals, grand_income = _column_totals(income_rows)
    expense_totals, grand_expense = _column_totals(expense_rows)
    net_totals = [income_totals[i] - expense_totals[i] for i in range(len(columns))]
    grand_net = grand_income - grand_expense

    return {
        "title": GRID_TITLE,
        "subtitle": "",
        "labels": GRID_LABELS,
        "columns": columns,
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "income_totals": income_totals,
        "expense_totals": expense_totals,
        "net_totals": net_totals,
        "grand_income": grand_income,
        "grand_expense": grand_expense,
        "grand_net": grand_net,
        "net_positive": grand_net >= 0,
    }