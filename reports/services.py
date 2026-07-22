"""Report data builders — hierarchy-aware, read-only queries."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from church_system.church_scope import get_user_church
from members.models import MembershipStatus
from permissions.checks import (
    can_manage_finances,
    can_manage_members,
    can_view_all_churches,
    can_view_members,
    can_view_reports,
)
from permissions.scoping import get_manageable_churches
from permissions.superadmin import is_superadmin
from sitecontrol.services import church_has_feature

from . import repositories as repo
from . import selectors
from .registry import PERIOD_CHOICES, REPORT_CATALOG

ASSET_TYPES = {"CASH", "BANK", "REMITTANCE_RECEIVABLE", "FIXED_ASSET", "ACCUMULATED_DEPRECIATION"}
LIABILITY_TYPES = {
    "DISTRICT_PAYABLE",
    "TITHE_REMIT_PAYABLE",
    "COMBINED_REMIT_PAYABLE",
    "SALARIES_PAYABLE",
    "PAYE_PAYABLE",
    "SSNIT_PAYABLE",
    "PENSION_PAYABLE",
}
# Equity / fund balances (credit-normal). COMBINED_RETENTION is retention income held as fund equity.
FUND_TYPES = {"WELFARE_FUND", "COMBINED_RETENTION"}
INCOME_TYPES = {"TITHE", "COMBINED", "INCOME", "COMBINED_RETENTION"}
EXPENSE_TYPES = {"EXPENSE", "SALARY_EXPENSE", "EMPLOYER_SSNIT_EXPENSE", "DEPRECIATION_EXPENSE"}

# Soft cap for detail rows in register-style reports (exports include note when truncated).
REPORT_ROW_LIMIT = 500


def _feature_allowed(user, church, feature_key):
    """Fail closed when church context is missing (superadmin excepted)."""
    if is_superadmin(user):
        return True
    if not church:
        return False
    return church_has_feature(church, feature_key)


def user_may_access_report(user, report_key, active_church=None):
    """
    Whether the user may run a catalog report.

    Requires view_reports plus the report's domain permission (finance/members/overseer),
    and feature gates fail closed without church context.
    """
    meta = REPORT_CATALOG.get(report_key)
    if not meta:
        return False
    if not can_view_reports(user):
        return False

    perm = meta["permission"]
    if perm == "finance":
        if not can_manage_finances(user):
            return False
    elif perm == "members":
        if not (can_view_members(user) or can_manage_members(user)):
            return False
    elif perm == "overseer":
        if not can_view_all_churches(user):
            return False
    else:
        return False

    church = active_church or get_user_church(user)
    if meta.get("requires_advanced"):
        if not _feature_allowed(user, church, "advanced_reports"):
            return False
    if meta.get("requires_feature"):
        if not _feature_allowed(user, church, meta["requires_feature"]):
            return False
    return True


def reports_for_user(user, active_church=None):
    """Return report catalog entries this user may run."""
    available = []
    for key, meta in REPORT_CATALOG.items():
        if user_may_access_report(user, key, active_church=active_church):
            available.append({"key": key, **meta})
    return available


def parse_report_date(value):
    """Parse ISO date strings from async job params; pass through date objects."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Invalid date value: {value!r}")


def resolve_date_range(period, start_date=None, end_date=None):
    today = timezone.now().date()
    start_date = parse_report_date(start_date) if start_date else None
    end_date = parse_report_date(end_date) if end_date else None
    if period == "weekly":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "monthly":
        return today.replace(day=1), today
    if period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_start_month, day=1), today
    if period == "semi_annual":
        half = 1 if today.month <= 6 else 7
        return today.replace(month=half, day=1), today
    if period == "annual":
        return today.replace(month=1, day=1), today
    if start_date and end_date:
        return start_date, end_date
    return today.replace(day=1), today


def _churches_in_scope(request, conference_id=None, zone_id=None, district_id=None, church_id=None):
    return selectors.churches_in_scope(
        request,
        conference_id=conference_id,
        zone_id=zone_id,
        district_id=district_id,
        church_id=church_id,
    )


def _transactions_in_scope(request, start, end, **hierarchy):
    return selectors.transactions_in_scope(request, start, end, **hierarchy)


def _members_in_scope(request, **hierarchy):
    return selectors.members_in_scope(request, **hierarchy)


def log_report_access(*, user, report_key, action, params=None, row_count=0, church=None, export_format=""):
    return repo.create_access_audit(
        user=user,
        report_key=report_key,
        action=action,
        params=params,
        row_count=row_count,
        church=church,
        export_format=export_format,
    )


def audit_export(
    *,
    user,
    report_key,
    export_format,
    row_count=0,
    church=None,
    params=None,
):
    """
    Write ReportAccessAuditLog for a domain/module file export.

    Call before returning CSV/Excel/PDF from views that use ``reports.exporters``
    (or equivalent) outside the reports catalog runner.
    """
    from .models import ReportAccessAuditLog

    log_report_access(
        user=user,
        report_key=report_key,
        action=ReportAccessAuditLog.ACTION_EXPORT,
        params=params,
        row_count=row_count,
        church=church,
        export_format=export_format or "",
    )


def build_report(report_key, request, period="monthly", start_date=None, end_date=None, **hierarchy):
    start, end = resolve_date_range(period, start_date, end_date)
    builders = {
        "financial_summary": _financial_summary,
        "member_summary": _member_summary,
        "tithe_report": _tithe_report,
        "transfer_report": _transfer_report,
        "attendance_summary": _attendance_summary,
        "hierarchy_rollup": _hierarchy_rollup,
        "payroll_summary": _payroll_summary,
        "trial_balance": _trial_balance,
        "balance_sheet": _balance_sheet,
        "income_statement": _income_statement,
        "cash_position": _cash_position,
        "asset_register": _asset_register_report,
        "depreciation_schedule": _depreciation_schedule_report,
        "asset_hierarchy_rollup": _asset_hierarchy_rollup_report,
        "welfare_register": _welfare_register_report,
        "budget_vs_actual": _budget_vs_actual_report,
    }
    builder = builders.get(report_key)
    if not builder:
        raise ValueError(f"Unknown report: {report_key}")
    data = builder(request, start, end, **hierarchy)
    data["period_label"] = dict(PERIOD_CHOICES).get(period, period)
    data["start_date"] = start
    data["end_date"] = end
    return data


def _financial_summary(request, start, end, **hierarchy):
    txns = _transactions_in_scope(request, start, end, **hierarchy)
    lines = selectors.transaction_lines_for_transactions(txns)

    def _sum_type(acc_type):
        return abs(selectors.sum_line_amount_for_type(lines, acc_type) or Decimal("0"))

    summary = {
        "tithe": _sum_type("TITHE"),
        "combined": _sum_type("COMBINED"),
        "income": _sum_type("INCOME"),
        "expense": _sum_type("EXPENSE"),
        "transaction_count": txns.count(),
    }
    # Operating net excludes tithe/combined (remitted / restricted); documented in row label.
    operating_net = summary["income"] - summary["expense"]
    giving_total = summary["tithe"] + summary["combined"]
    headers = ["Category", "Amount"]
    rows = [
        ["Tithe", summary["tithe"]],
        ["Combined Offering", summary["combined"]],
        ["Giving subtotal (Tithe + Combined)", giving_total],
        ["Church Income (operating)", summary["income"]],
        ["Expenses (operating)", summary["expense"]],
        ["Operating net (Income − Expense)", operating_net],
    ]
    return {"title": "Financial Summary", "summary": summary, "headers": headers, "rows": rows}


def _member_summary(request, start, end, **hierarchy):
    members = _members_in_scope(request, **hierarchy)
    by_gender = selectors.member_gender_counts(members)
    by_status = selectors.member_status_counts(members)
    by_dept = selectors.member_department_counts(members)
    headers = ["Metric", "Count"]
    rows = [
        ["Total Members", members.count()],
        ["Active", members.filter(is_active=True, membership_status=MembershipStatus.ACTIVE).count()],
        ["Inactive", members.filter(is_active=False).count()],
    ]
    for g in by_gender:
        rows.append([f"Gender: {g['gender']}", g["count"]])
    for s in by_status:
        rows.append([f"Status: {s['membership_status']}", s["count"]])
    for d in by_dept[:10]:
        rows.append([f"Dept: {d['department__name']}", d["count"]])
    return {
        "title": "Member Summary",
        "by_gender": list(by_gender),
        "by_status": list(by_status),
        "by_department": list(by_dept),
        "headers": headers,
        "rows": rows,
    }


def _tithe_report(request, start, end, **hierarchy):
    txns = _transactions_in_scope(request, start, end, **hierarchy)
    aggregates = selectors.tithe_combined_by_member(txns)

    member_totals = {}
    for row in aggregates:
        key = row["transaction__member_id"]
        if key not in member_totals:
            member_totals[key] = {
                "name": f"{row['transaction__member__first_name']} {row['transaction__member__last_name']}".strip(),
                "last_name": row["transaction__member__last_name"] or "",
                "tithe": Decimal("0"),
                "combined": Decimal("0"),
            }
        amount = abs(row["total"] or Decimal("0"))
        if row["account__account_type"] == "TITHE":
            member_totals[key]["tithe"] += amount
        else:
            member_totals[key]["combined"] += amount

    headers = ["Member", "Tithe", "Combined", "Total"]
    rows = []
    for entry in sorted(member_totals.values(), key=lambda x: x["last_name"]):
        total = entry["tithe"] + entry["combined"]
        rows.append([entry["name"], entry["tithe"], entry["combined"], total])

    truncated = False
    if len(rows) > REPORT_ROW_LIMIT:
        rows = rows[:REPORT_ROW_LIMIT]
        truncated = True
        rows.append(["… truncated", "", "", f"Showing first {REPORT_ROW_LIMIT} members"])

    return {"title": "Tithe & Offering Report", "headers": headers, "rows": rows, "truncated": truncated}


def _transfer_report(request, start, end, **hierarchy):
    churches = _churches_in_scope(request, **hierarchy)
    transfers = selectors.transfers_in_scope(churches, start, end)

    headers = ["Member", "From", "To", "Status", "Date"]
    qs = transfers.order_by("-transfer_date")
    total_count = qs.count()
    truncated = total_count > REPORT_ROW_LIMIT
    rows = [
        [
            t.member.full_name,
            t.from_church.name,
            t.to_church.name,
            t.status,
            t.transfer_date,
        ]
        for t in qs[:REPORT_ROW_LIMIT]
    ]
    if truncated:
        rows.append(["… truncated", "", "", "", f"Showing {REPORT_ROW_LIMIT} of {total_count}"])
    return {"title": "Member Transfers", "headers": headers, "rows": rows, "truncated": truncated}


def _attendance_summary(request, start, end, **hierarchy):
    churches = _churches_in_scope(request, **hierarchy)
    events = selectors.attendance_events_in_scope(churches, start, end)
    headers = ["Event", "Type", "Date", "Present", "Total"]
    total_count = events.count()
    truncated = total_count > REPORT_ROW_LIMIT
    rows = [
        [
            event.title,
            event.get_event_type_display(),
            event.event_date,
            event.present_count,
            event.total_count,
        ]
        for event in events[:REPORT_ROW_LIMIT]
    ]
    if truncated:
        rows.append(["… truncated", "", "", "", f"Showing {REPORT_ROW_LIMIT} of {total_count}"])
    return {"title": "Attendance Summary", "headers": headers, "rows": rows, "truncated": truncated}


def _hierarchy_rollup(request, start, end, **hierarchy):
    """District-level tithe and offering roll-up for overseers."""
    if not can_view_all_churches(request.user):
        return {"title": "District Roll-up", "headers": [], "rows": []}

    churches = _churches_in_scope(request, **hierarchy)
    church_rows = selectors.church_district_rows(churches)
    if not church_rows:
        return {"title": "District Roll-up", "headers": ["District", "Churches", "Tithe", "Combined", "Total"], "rows": []}

    church_ids = [r["id"] for r in church_rows]
    district_meta = {}
    for r in church_rows:
        d_id = r["district_id"]
        if d_id not in district_meta:
            district_meta[d_id] = {"name": r["district__name"], "church_count": 0}
        district_meta[d_id]["church_count"] += 1

    line_aggs = selectors.district_tithe_combined_aggregates(church_ids, start, end)

    amounts = {d_id: {"tithe": Decimal("0"), "combined": Decimal("0")} for d_id in district_meta}
    for row in line_aggs:
        d_id = row["transaction__church__district_id"]
        if d_id not in amounts:
            continue
        amount = abs(row["total"] or Decimal("0"))
        if row["account__account_type"] == "TITHE":
            amounts[d_id]["tithe"] += amount
        else:
            amounts[d_id]["combined"] += amount

    headers = ["District", "Churches", "Tithe", "Combined", "Total"]
    rows = []
    for d_id, meta in district_meta.items():
        tithe = amounts[d_id]["tithe"]
        combined = amounts[d_id]["combined"]
        rows.append([meta["name"], meta["church_count"], tithe, combined, tithe + combined])

    rows.sort(key=lambda r: r[4], reverse=True)
    return {"title": "District Roll-up", "headers": headers, "rows": rows}


def _payroll_summary(request, start, end, **hierarchy):
    from payroll.services import hierarchy_payroll_rollup

    churches = _churches_in_scope(request, **hierarchy)
    year = end.year
    month = end.month if start.month == end.month and start.year == end.year else None
    rows_data = hierarchy_payroll_rollup(request.user, year=year, month=month)
    church_names = selectors.church_names_set(churches)
    rows_data = [r for r in rows_data if r["church"] in church_names]

    headers = ["Church", "District", "Runs", "Gross", "Net", "Employer Cost"]
    rows = [
        [r["church"], r["district"], r["runs"], r["gross"], r["net"], r["employer_cost"]]
        for r in rows_data
    ]
    return {"title": "Payroll Summary", "headers": headers, "rows": rows}


def _quantize(value):
    from transactions.services import _quantize_currency
    return _quantize_currency(value or Decimal("0"))


def _lines_for_churches(churches, end, start=None):
    return selectors.lines_for_churches(churches, end, start=start)


def _account_balances(churches, end, start=None):
    """
    Return {account_id: {account, balance, church_name}} via DB aggregation.

    Balance is the signed sum of line amounts (debit-positive convention used by GL).
    """
    aggregates = selectors.account_balance_aggregates(churches, end, start=start)
    account_ids = {row["account_id"] for row in aggregates}
    accounts = selectors.accounts_by_ids(account_ids)

    balances = {}
    for row in aggregates:
        acc_id = row["account_id"]
        account = accounts.get(acc_id)
        if not account:
            continue
        balances[acc_id] = {
            "account": account,
            "church_name": row["transaction__church__name"],
            "balance": row["balance"] or Decimal("0"),
        }
    return balances


def _trial_balance(request, start, end, **hierarchy):
    churches = _churches_in_scope(request, **hierarchy)
    balances = _account_balances(churches, end)
    headers = ["Church", "Account", "Type", "Debit", "Credit"]
    rows = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for entry in sorted(balances.values(), key=lambda x: (x["church_name"], x["account"].name)):
        bal = _quantize(entry["balance"])
        debit = bal if bal > 0 else Decimal("0")
        credit = abs(bal) if bal < 0 else Decimal("0")
        total_debit += debit
        total_credit += credit
        rows.append([
            entry["church_name"],
            entry["account"].name,
            entry["account"].get_account_type_display(),
            debit,
            credit,
        ])
    rows.append(["", "TOTAL", "", total_debit, total_credit])
    return {
        "title": "Trial Balance",
        "headers": headers,
        "rows": rows,
        "summary": {"total_debit": total_debit, "total_credit": total_credit},
    }


def _balance_sheet(request, start, end, **hierarchy):
    churches = _churches_in_scope(request, **hierarchy)
    balances = _account_balances(churches, end)
    sections = [
        ("Assets", ASSET_TYPES),
        ("Liabilities", LIABILITY_TYPES),
        ("Funds & Equity", FUND_TYPES),
    ]
    headers = ["Section", "Account", "Church", "Balance"]
    rows = []
    section_totals = {}
    for section_name, types in sections:
        section_total = Decimal("0")
        for entry in sorted(balances.values(), key=lambda x: x["account"].name):
            if entry["account"].account_type not in types:
                continue
            bal = _quantize(entry["balance"])
            # Present liability/fund credit balances as positive for readability.
            if section_name != "Assets":
                display = abs(bal) if bal < 0 else bal
            else:
                display = bal
            section_total += display
            rows.append([section_name, entry["account"].name, entry["church_name"], display])
        section_totals[section_name] = section_total
        rows.append([section_name, f"Total {section_name}", "", section_total])
    return {
        "title": "Balance Sheet",
        "headers": headers,
        "rows": rows,
        "summary": section_totals,
    }


def _income_statement(request, start, end, **hierarchy):
    """
    Period activity for income and expense accounts.

    Income accounts are credit-normal (negative line sums); expense accounts are
    debit-normal (positive). Amounts are shown as positive activity figures.
    """
    churches = _churches_in_scope(request, **hierarchy)
    balances = _account_balances(churches, end, start=start)
    headers = ["Category", "Account", "Church", "Amount"]
    rows = []
    total_income = Decimal("0")
    total_expense = Decimal("0")
    for entry in sorted(balances.values(), key=lambda x: x["account"].name):
        acc_type = entry["account"].account_type
        bal = _quantize(entry["balance"])
        if acc_type in INCOME_TYPES:
            # Credit-normal: activity magnitude is -balance when credits dominate.
            amount = abs(bal)
            total_income += amount
            rows.append(["Income", entry["account"].name, entry["church_name"], amount])
        elif acc_type in EXPENSE_TYPES:
            amount = abs(bal)
            total_expense += amount
            rows.append(["Expense", entry["account"].name, entry["church_name"], amount])
    net = total_income - total_expense
    rows.append(["", "Total Income", "", total_income])
    rows.append(["", "Total Expense", "", total_expense])
    rows.append(["", "Net Surplus / (Deficit)", "", net])
    return {
        "title": "Income Statement",
        "headers": headers,
        "rows": rows,
        "summary": {"income": total_income, "expense": total_expense, "net": net},
    }


def _cash_position(request, start, end, **hierarchy):
    churches = _churches_in_scope(request, **hierarchy)
    balances = _account_balances(churches, end)
    headers = ["Church", "Account", "Type", "Balance"]
    rows = []
    total = Decimal("0")
    for entry in sorted(balances.values(), key=lambda x: (x["church_name"], x["account"].name)):
        if entry["account"].account_type not in {"CASH", "BANK"}:
            continue
        bal = _quantize(entry["balance"])
        total += bal
        rows.append([
            entry["church_name"],
            entry["account"].name,
            entry["account"].get_account_type_display(),
            bal,
        ])
    rows.append(["", "Total Cash & Bank", "", total])
    return {
        "title": "Cash & Bank Position",
        "headers": headers,
        "rows": rows,
        "summary": {"total": total},
    }


def _asset_register_report(request, start, end, **hierarchy):
    from assets.services import report_asset_register
    return report_asset_register(request, start, end, **hierarchy)


def _depreciation_schedule_report(request, start, end, **hierarchy):
    from assets.services import report_depreciation_schedule
    return report_depreciation_schedule(request, start, end, **hierarchy)


def _asset_hierarchy_rollup_report(request, start, end, **hierarchy):
    from assets.services import report_asset_hierarchy_rollup
    return report_asset_hierarchy_rollup(request, start, end, **hierarchy)


def _welfare_register_report(request, start, end, **hierarchy):
    from remittance.welfare_services import get_welfare_fund_balance

    churches = _churches_in_scope(request, **hierarchy)
    church_list = list(churches)
    contributions = selectors.welfare_contributions_in_scope(churches, start, end)
    cases = selectors.welfare_cases_in_scope(churches, start, end)

    contributed = selectors.welfare_contribution_total(contributions) or Decimal("0")
    disbursed = selectors.welfare_disbursed_total(cases) or Decimal("0")
    pending = cases.filter(status__in=("PENDING", "UNDER_REVIEW")).count()
    approved_awaiting = cases.filter(status="APPROVED").count()

    fund_balance = Decimal("0")
    for church in church_list:
        fund_balance += get_welfare_fund_balance(church)

    headers = ["Date", "Member", "Type", "Reference", "Amount", "Status"]
    rows = []
    contrib_qs = contributions.order_by("-contribution_date")
    case_qs = cases.order_by("-created_at")
    contrib_total = contrib_qs.count()
    case_total = case_qs.count()
    half = REPORT_ROW_LIMIT // 2
    truncated = contrib_total > half or case_total > half

    for row in contrib_qs[:half]:
        rows.append([
            row.contribution_date,
            row.member.full_name if row.member else "Anonymous",
            "Contribution",
            row.transaction.reference if row.transaction else "",
            row.amount,
            "Posted",
        ])
    for case in case_qs[:half]:
        rows.append([
            case.created_at.date(),
            case.member.full_name,
            case.get_assistance_type_display(),
            case.case_number,
            case.amount_approved or case.amount_requested,
            case.get_status_display(),
        ])
    if truncated:
        rows.append([
            "",
            "… truncated",
            "",
            f"Showing up to {half} contributions and {half} cases",
            "",
            "",
        ])

    summary = {
        "fund_balance": fund_balance,
        "contributions": contributed,
        "disbursed": disbursed,
        "pending_cases": pending,
        "approved_awaiting": approved_awaiting,
        "net_pool_change": contributed - disbursed,
        "church_count": len(church_list),
    }
    return {
        "title": "Welfare Register",
        "summary": summary,
        "headers": headers,
        "rows": rows,
        "truncated": truncated,
    }


def _budget_vs_actual_report(request, start, end, **hierarchy):
    from budgets.services import budget_kpis, budget_summary, export_budget_table

    churches = list(_churches_in_scope(request, **hierarchy))
    if not churches:
        return {
            "title": "Budget vs Actual",
            "headers": ["Church", "Account", "Type", "Level", "Department", "Budgeted", "Actual", "Variance", "Status"],
            "rows": [],
            "summary": {},
        }

    year = end.year
    all_rows = []
    for church in churches:
        for row in budget_summary(church=church, year=year, level="CHURCH"):
            all_rows.append({**row, "church_name": church.name})

    kpis = budget_kpis(all_rows)
    if len(churches) == 1:
        scope_label = churches[0].name
        payload = export_budget_table(all_rows, year, scope_label)
        return {
            "title": payload["title"],
            "subtitle": payload["subtitle"],
            "summary": kpis,
            "headers": payload["headers"],
            "rows": payload["rows"],
        }

    headers = ["Church", "Account", "Type", "Level", "Department", "Budgeted", "Actual", "Variance", "Status"]
    table_rows = []
    for row in all_rows:
        if row.get("tracks_actual", True) and row.get("actual") is not None:
            status = "On track" if row.get("favorable") else "Over budget"
            actual_display = row["actual"]
            variance_display = row["variance"]
        else:
            status = "Allocation"
            actual_display = "N/A"
            variance_display = row["budgeted"]
        table_rows.append([
            row.get("church_name", ""),
            row["account"],
            row.get("account_type", ""),
            row.get("level", ""),
            row.get("department", "") or "—",
            row["budgeted"],
            actual_display,
            variance_display,
            status,
        ])
    return {
        "title": f"Budget vs Actual — {year}",
        "subtitle": f"{len(churches)} churches",
        "summary": kpis,
        "headers": headers,
        "rows": table_rows,
    }


def get_hierarchy_context(user):
    """Dropdown options for hierarchy filters (manageable churches only)."""
    manageable = get_manageable_churches(user)
    ctx = {
        "conferences": selectors.empty_conferences(),
        "zones": selectors.empty_zones(),
        "districts": selectors.empty_districts(),
        "churches": selectors.empty_churches(),
        "can_filter_hierarchy": False,
    }
    if not can_view_all_churches(user):
        ctx["churches"] = manageable
        return ctx

    ids = selectors.manageable_hierarchy_ids(manageable)
    ctx["can_filter_hierarchy"] = True
    ctx["conferences"] = selectors.conferences_by_ids(ids["conference_ids"])
    ctx["zones"] = selectors.zones_by_ids(ids["zone_ids"])
    ctx["districts"] = selectors.districts_by_ids(ids["district_ids"])
    ctx["churches"] = selectors.manageable_churches_ordered(manageable)
    return ctx
