"""End-of-year detailed report composition."""

from __future__ import annotations

from decimal import Decimal

from reports.eoy_sections import default_eoy_sections


def build_end_of_year_detailed(services, request, start, end, *, eoy_sections=None, **hierarchy):
    """
    Build the composite EOY payload.

    ``services`` is the reports.services module (avoids circular imports).
    """
    flags = eoy_sections or default_eoy_sections()
    _quantize = services._quantize
    _financial_summary = services._financial_summary
    _income_statement = services._income_statement
    _balance_sheet = services._balance_sheet
    _cash_position = services._cash_position
    _trial_balance = services._trial_balance
    _monthly_giving_breakdown = services._monthly_giving_breakdown
    _eoy_membership_snapshot = services._eoy_membership_snapshot
    _statement_sections_prefixed = services._statement_sections_prefixed
    _statement = services._statement
    _budget_vs_actual_report = services._budget_vs_actual_report
    _settlement_register_report = services._settlement_register_report
    _payroll_summary = services._payroll_summary

    financial = _financial_summary(request, start, end, **hierarchy) if flags.get("operating") else None
    income = (
        _income_statement(request, start, end, **hierarchy) if flags.get("income_statement") else None
    )
    balance = _balance_sheet(request, start, end, **hierarchy) if flags.get("balance_sheet") else None
    cash = _cash_position(request, start, end, **hierarchy) if flags.get("cash") else None
    trial = _trial_balance(request, start, end, show_zeros=False, **hierarchy)

    monthly_lines, monthly_tithe, monthly_combined = [], Decimal("0"), Decimal("0")
    if flags.get("monthly"):
        monthly_lines, monthly_tithe, monthly_combined = _monthly_giving_breakdown(
            request, start, end, **hierarchy
        )

    membership_lines = (
        _eoy_membership_snapshot(request, start, end, **hierarchy) if flags.get("membership") else []
    )

    fs_summary = (financial or {}).get("summary") or {}
    is_summary = (income or {}).get("summary") or {"income": Decimal("0"), "expense": Decimal("0"), "net": Decimal("0")}
    bs_summary = (balance or {}).get("summary") or {}
    cash_total = (cash or {}).get("summary", {}).get("total", Decimal("0"))
    tb_summary = trial["summary"]

    sections = []
    if flags.get("monthly"):
        sections.append(
            {
                "id": "eoy-monthly",
                "title": "Monthly giving (tithe + combined)",
                "total": monthly_tithe + monthly_combined,
                "lines": monthly_lines,
                "empty": "No giving recorded in this period.",
                "layout": "monthly_giving",
            }
        )
    if flags.get("operating") and financial:
        sections.extend(
            _statement_sections_prefixed(
                financial["statement"]["sections"],
                "eoy-fs",
                title_prefix="Operating — ",
            )
        )
    if flags.get("income_statement") and income:
        sections.extend(
            _statement_sections_prefixed(
                income["statement"]["sections"],
                "eoy-is",
                title_prefix="Income statement — ",
            )
        )
    if flags.get("balance_sheet") and balance:
        sections.extend(
            _statement_sections_prefixed(
                balance["statement"]["sections"],
                "eoy-bs",
                title_prefix="Balance sheet — ",
            )
        )
    if flags.get("cash") and cash:
        sections.extend(
            _statement_sections_prefixed(
                cash["statement"]["sections"],
                "eoy-cash",
                title_prefix="Cash & bank — ",
            )
        )
    if flags.get("membership") and membership_lines:
        sections.append(
            {
                "id": "eoy-membership",
                "title": "Membership & attendance snapshot",
                "total": membership_lines[0]["amount"] if membership_lines else 0,
                "lines": membership_lines,
                "empty": "No membership data in scope.",
                "layout": "integer",
            }
        )
    if flags.get("budget"):
        sections.append(_eoy_budget_section(_budget_vs_actual_report, request, start, end, **hierarchy))
    if flags.get("settlement"):
        sections.append(_eoy_settlement_section(_settlement_register_report, request, start, end, **hierarchy))
    if flags.get("payroll"):
        sections.append(_eoy_payroll_section(_payroll_summary, request, start, end, **hierarchy))

    operating_net = Decimal("0")
    if fs_summary:
        operating_net = fs_summary.get("income", Decimal("0")) - fs_summary.get("expense", Decimal("0"))

    kpis = [
        {"label": "Tithe (period)", "value": fs_summary.get("tithe", Decimal("0")), "tone": "primary"},
        {"label": "Combined (period)", "value": fs_summary.get("combined", Decimal("0")), "tone": "accent"},
    ]
    if flags.get("operating") and fs_summary:
        kpis.append(
            {
                "label": "Operating net",
                "value": operating_net,
                "tone": "success" if operating_net >= 0 else "danger",
            }
        )
    if flags.get("income_statement"):
        kpis.append(
            {
                "label": "Net surplus / (deficit)",
                "value": is_summary["net"],
                "tone": "success" if is_summary["net"] >= 0 else "danger",
            }
        )
    if flags.get("balance_sheet"):
        kpis.append(
            {
                "label": "Total assets",
                "value": bs_summary.get("Assets", Decimal("0")),
                "tone": "success",
            }
        )
    if flags.get("cash"):
        kpis.append({"label": "Cash & bank", "value": cash_total, "tone": "accent"})

    notes = [f"Period {start} through {end}."]
    if flags.get("monthly"):
        notes.append("Monthly giving shows tithe and combined by calendar month.")
    if flags.get("operating"):
        notes.append(
            "Operating sections follow the Financial Summary rules (Combined Retention is operating income)."
        )
    if flags.get("balance_sheet") or flags.get("cash"):
        notes.append("Balance sheet and cash figures are as of period end.")
    notes.append(
        f"Trial balance as of period end: debits {_quantize(tb_summary['total_debit'])} "
        f"and credits {_quantize(tb_summary['total_credit'])}."
    )
    if fs_summary.get("transaction_count") is not None:
        notes.append(f"{fs_summary['transaction_count']} approved journal(s) in the period.")

    statement = _statement(
        kpis=kpis,
        sections=sections,
        notes=notes,
        balanced=trial["statement"].get("balanced"),
    )
    footer = []
    if flags.get("income_statement"):
        footer.extend(
            [
                {"label": "Total income (activity)", "amount": is_summary["income"]},
                {"label": "Total expense (activity)", "amount": is_summary["expense"]},
                {"label": "Net surplus / (deficit)", "amount": is_summary["net"], "emphasis": True},
            ]
        )
    if flags.get("balance_sheet"):
        footer.append(
            {"label": "Total assets (period end)", "amount": bs_summary.get("Assets", Decimal("0"))}
        )
    if flags.get("cash"):
        footer.append({"label": "Cash & bank (period end)", "amount": cash_total})
    statement["footer_totals"] = footer

    headers = ["Part", "Metric", "Amount"]
    rows = []
    if flags.get("monthly"):
        rows.extend(
            [
                ["Monthly giving", "Tithe total", monthly_tithe],
                ["Monthly giving", "Combined total", monthly_combined],
            ]
        )
    if flags.get("operating") and fs_summary:
        rows.extend(
            [
                ["Operating", "Tithe", fs_summary.get("tithe", Decimal("0"))],
                ["Operating", "Combined offering", fs_summary.get("combined", Decimal("0"))],
                ["Operating", "Operating income", fs_summary.get("income", Decimal("0"))],
                ["Operating", "Operating expense", fs_summary.get("expense", Decimal("0"))],
                ["Operating", "Operating net", operating_net],
            ]
        )
    if flags.get("income_statement"):
        rows.extend(
            [
                ["Income statement", "Total income", is_summary["income"]],
                ["Income statement", "Total expense", is_summary["expense"]],
                ["Income statement", "Net surplus / (deficit)", is_summary["net"]],
            ]
        )
    if flags.get("balance_sheet"):
        rows.extend(
            [
                ["Balance sheet", "Assets", bs_summary.get("Assets", Decimal("0"))],
                ["Balance sheet", "Liabilities", bs_summary.get("Liabilities", Decimal("0"))],
                ["Balance sheet", "Funds & equity", bs_summary.get("Funds & Equity", Decimal("0"))],
            ]
        )
    if flags.get("cash"):
        rows.append(["Cash & bank", "Total", cash_total])
    rows.extend(
        [
            ["Trial balance", "Total debits", tb_summary["total_debit"]],
            ["Trial balance", "Total credits", tb_summary["total_credit"]],
        ]
    )
    for line in membership_lines:
        rows.append(["Membership", line["label"], line["amount"]])

    chart = {}
    if flags.get("monthly") and monthly_lines:
        chart = {
            "labels": [line["label"] for line in monthly_lines],
            "amounts": [line["amount"] for line in monthly_lines],
        }

    profit_loss_grid = None
    if flags.get("income_statement"):
        from reports.profit_loss_grid import build_profit_loss_grid

        churches = services._churches_in_scope(request, **hierarchy)
        profit_loss_grid = build_profit_loss_grid(churches, start, end)

    return {
        "title": "End of Year Detailed Report",
        "headers": headers,
        "rows": rows,
        "profit_loss_grid": profit_loss_grid,
        "summary": {
            "tithe": fs_summary.get("tithe", Decimal("0")),
            "combined": fs_summary.get("combined", Decimal("0")),
            "operating_net": operating_net,
            "income_statement_net": is_summary["net"],
            "assets": bs_summary.get("Assets", Decimal("0")),
            "cash": cash_total,
            "trial_balanced": trial["statement"].get("balanced"),
        },
        "statement": statement,
        "chart": chart,
    }


def _eoy_budget_section(builder, request, start, end, **hierarchy):
    data = builder(request, start, end, **hierarchy)
    lines = []
    for row in data.get("rows") or []:
        if len(row) < 8:
            continue
        try:
            variance = row[7]
        except (TypeError, IndexError):
            continue
        lines.append({"label": str(row[1]), "church": str(row[0]), "amount": variance})
    total = Decimal("0")
    for line in lines:
        amt = line.get("amount")
        if isinstance(amt, Decimal):
            total += amt
        elif amt is not None:
            total += Decimal(str(amt))
    return {
        "id": "eoy-budget",
        "title": "Budget vs actual (variance)",
        "total": total,
        "lines": lines[:200],
        "empty": "No budget lines in scope for this year.",
    }


def _eoy_settlement_section(builder, request, start, end, **hierarchy):
    pack = builder(request, start, end, **hierarchy)
    summary = pack.get("summary") or {}
    lines = [
        {"label": "Posted settlement batches", "church": "", "amount": summary.get("posted_batches", 0)},
        {"label": "Linked journals", "church": "", "amount": summary.get("linked_journals", 0)},
        {"label": "Remittance payments", "church": "", "amount": summary.get("remittance_payments", 0)},
        {"label": "Gross offering", "church": "", "amount": summary.get("gross", Decimal("0"))},
        {"label": "Payable total", "church": "", "amount": summary.get("payable", Decimal("0"))},
    ]
    return {
        "id": "eoy-settlement",
        "title": "Settlement register summary",
        "total": summary.get("gross", Decimal("0")),
        "lines": lines,
        "empty": "No settlement activity in this period.",
        "layout": "mixed",
    }


def _eoy_payroll_section(builder, request, start, end, **hierarchy):
    data = builder(request, start, end, **hierarchy)
    lines = []
    total = Decimal("0")
    for row in data.get("rows") or []:
        if len(row) < 6:
            continue
        amount = row[5]
        total += amount if isinstance(amount, Decimal) else Decimal(str(amount or 0))
        lines.append({"label": str(row[0]), "church": str(row[1]), "amount": amount})
    return {
        "id": "eoy-payroll",
        "title": "Payroll summary",
        "total": total,
        "lines": lines[:200],
        "empty": "No payroll runs in this period.",
    }