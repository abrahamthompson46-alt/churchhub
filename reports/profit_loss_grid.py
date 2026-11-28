"""Monthly receipts and expense matrix for End of Year and income views."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear

from transactions.models import TransactionLine

# Operating receipts: retain + income per remittance policy (not remit payables).
OPERATING_RECEIPT_TYPES = {"TITHE", "COMBINED", "INCOME", "COMBINED_RETENTION"}
# Fund contributions (equity/funds); shown for information, excluded from net.
FUND_RECEIPT_TYPES = {"WELFARE_FUND"}
EXPENSE_TYPES = {"EXPENSE", "SALARY_EXPENSE", "EMPLOYER_SSNIT_EXPENSE", "DEPRECIATION_EXPENSE"}

GRID_INCLUDED_TYPES = OPERATING_RECEIPT_TYPES | FUND_RECEIPT_TYPES | EXPENSE_TYPES

GRID_TITLE = "Monthly receipts and expense (posted books)"
GRID_SUBTITLE = (
    "Approved journals only. Net uses operating receipts minus expense. "
    "Remittance payables are excluded. Fund contributions are informational."
)
GRID_LABELS = {
    "account_column": "Account",
    "total_column": "Total",
    "operating_section": "Operating receipts",
    "fund_section": "Fund receipts",
    "expense_section": "Expense",
    "total_operating": "Total operating receipts",
    "total_fund": "Total fund contributions",
    "total_expense": "Total expense",
    "net_row": "Net surplus / (deficit)",
    # Backward-compatible keys (tests / legacy snippets)
    "income_section": "Operating receipts",
    "total_income": "Total operating receipts",
    "net_total": "Net surplus / (deficit)",
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


def _empty_grid() -> dict:
    return {
        "title": GRID_TITLE,
        "subtitle": GRID_SUBTITLE,
        "labels": GRID_LABELS,
        "columns": [],
        "operating_rows": [],
        "fund_rows": [],
        "expense_rows": [],
        "income_rows": [],
        "operating_totals": [],
        "fund_totals": [],
        "expense_totals": [],
        "income_totals": [],
        "net_totals": [],
        "grand_operating": Decimal("0"),
        "grand_fund": Decimal("0"),
        "grand_expense": Decimal("0"),
        "grand_net": Decimal("0"),
        "grand_income": Decimal("0"),
        "net_positive": True,
    }


def build_profit_loss_grid(churches, start: date, end: date) -> dict:
    """
    Posted-books matrix: operating receipts, fund receipts, and expense accounts
    × fiscal months in range.

    Amounts use approved, non-voided journal line totals per calendar month.
    """
    columns = _month_columns(start, end)
    if not columns or not churches.exists():
        return _empty_grid()

    qs = (
        TransactionLine.objects.filter(
            transaction__church__in=churches,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            transaction__date__gte=start,
            transaction__date__lte=end,
            account__account_type__in=list(GRID_INCLUDED_TYPES),
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

    operating_rows = []
    fund_rows = []
    expense_rows = []
    for (_aid, _name, acc_type), entry in sorted(bucket.items(), key=lambda x: x[0][1]):
        row = {
            "account_id": entry["account_id"],
            "account_name": entry["account_name"],
            "cells": [entry["cells"][c["key"]] for c in columns],
            "total": entry["total"],
        }
        if acc_type in OPERATING_RECEIPT_TYPES:
            operating_rows.append(row)
        elif acc_type in FUND_RECEIPT_TYPES:
            fund_rows.append(row)
        elif acc_type in EXPENSE_TYPES:
            expense_rows.append(row)

    def _column_totals(rows):
        if not columns:
            return [], Decimal("0")
        totals = [Decimal("0") for _ in columns]
        grand = Decimal("0")
        for row in rows:
            grand += row["total"]
            for idx, val in enumerate(row["cells"]):
                totals[idx] += val
        return totals, grand

    operating_totals, grand_operating = _column_totals(operating_rows)
    fund_totals, grand_fund = _column_totals(fund_rows)
    expense_totals, grand_expense = _column_totals(expense_rows)
    net_totals = [operating_totals[i] - expense_totals[i] for i in range(len(columns))]
    grand_net = grand_operating - grand_expense

    return {
        "title": GRID_TITLE,
        "subtitle": GRID_SUBTITLE,
        "labels": GRID_LABELS,
        "columns": columns,
        "operating_rows": operating_rows,
        "fund_rows": fund_rows,
        "expense_rows": expense_rows,
        "income_rows": operating_rows,
        "operating_totals": operating_totals,
        "fund_totals": fund_totals,
        "expense_totals": expense_totals,
        "income_totals": operating_totals,
        "net_totals": net_totals,
        "grand_operating": grand_operating,
        "grand_fund": grand_fund,
        "grand_expense": grand_expense,
        "grand_net": grand_net,
        "grand_income": grand_operating,
        "net_positive": grand_net >= 0,
    }