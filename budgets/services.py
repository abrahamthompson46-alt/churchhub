"""Budget planning services — variance, rollups, audit, and exports."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError

from budgets import repositories as repo
from budgets import selectors
from permissions.checks import can_view_all_churches

INCOME_ACCOUNT_TYPES = {"TITHE", "COMBINED", "INCOME", "COMBINED_RETENTION", "WELFARE_FUND"}
EXPENSE_ACCOUNT_TYPES = {"EXPENSE", "SALARY_EXPENSE", "EMPLOYER_SSNIT_EXPENSE", "DEPRECIATION_EXPENSE"}


class BudgetServiceError(Exception):
    pass


def _quantize(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"))


def _account_actual(churches_qs, account, year):
    """Sum approved transaction lines for an account across churches in a year."""
    return selectors.account_actual_for_year(churches_qs, account, year)


def _variance_meta(account_type, budgeted, actual):
    """Return variance and whether the line is favorable for the account type."""
    budgeted = _quantize(budgeted)
    actual = _quantize(actual)
    if account_type in INCOME_ACCOUNT_TYPES:
        variance = actual - budgeted
        favorable = variance >= 0
        over_budget = actual < budgeted
    else:
        variance = budgeted - actual
        favorable = variance >= 0
        over_budget = actual > budgeted
    return {
        "budgeted": budgeted,
        "actual": actual,
        "variance": variance,
        "favorable": favorable,
        "over_budget": over_budget,
        "account_type": account_type,
        "tracks_actual": True,
    }


def log_budget_audit(church, action, user, budget, details=None):
    """Write budget change to the financial audit log."""
    payload = {
        "budget_id": str(budget.pk),
        "level": budget.level,
        "year": budget.year,
        "account": budget.account.name,
        "amount": str(budget.amount),
    }
    if details:
        payload.update(details)
    repo.create_budget_audit(
        church=church,
        action=action,
        user=user,
        details=payload,
    )


def budgets_for_scope(church=None, year=None, level="CHURCH", district=None, conference=None):
    return selectors.budgets_for_scope_qs(
        church=church,
        year=year,
        level=level,
        district=district,
        conference=conference,
    )


def budgets_for_church(church, year=None, level="CHURCH"):
    return budgets_for_scope(church=church, year=year, level=level)


def _churches_for_budget(budget):
    return selectors.churches_for_budget_qs(budget)


def budget_line_variance(budget):
    """Compute variance row for a single budget line."""
    account = budget.account
    if budget.level == "DEPARTMENT":
        return {
            "budget_id": budget.pk,
            "account": account.name,
            "account_type": account.account_type,
            "department": budget.department.name if budget.department_id else "",
            "level": budget.get_level_display(),
            "budgeted": _quantize(budget.amount),
            "actual": None,
            "variance": _quantize(budget.amount),
            "favorable": True,
            "over_budget": False,
            "tracks_actual": False,
            "notes": budget.notes,
        }

    churches = _churches_for_budget(budget)
    actual = _quantize(_account_actual(churches, account, budget.year))
    meta = _variance_meta(account.account_type, budget.amount, actual)
    return {
        "budget_id": budget.pk,
        "account": account.name,
        "account_type": account.account_type,
        "department": budget.department.name if budget.department_id else "",
        "level": budget.get_level_display(),
        "notes": budget.notes,
        **meta,
    }


def budget_summary(church, year, level="CHURCH", district=None, conference=None):
    """Budget vs actual rows for a scope."""
    budgets = budgets_for_scope(
        church=church,
        year=year,
        level=level,
        district=district,
        conference=conference,
    )
    return [budget_line_variance(b) for b in budgets]


def budget_kpis(rows):
    """Aggregate KPIs from variance rows."""
    tracked = [r for r in rows if r.get("tracks_actual", True)]
    total_budgeted = sum(r["budgeted"] for r in rows)
    total_actual = sum(r["actual"] for r in tracked if r["actual"] is not None)
    total_variance = sum(
        r["variance"] for r in tracked if r["actual"] is not None
    )
    return {
        "line_count": len(rows),
        "tracked_count": len(tracked),
        "total_budgeted": _quantize(total_budgeted),
        "total_actual": _quantize(total_actual),
        "total_variance": _quantize(total_variance),
        "over_budget_count": sum(1 for r in tracked if r.get("over_budget")),
        "department_allocation_total": _quantize(
            sum(r["budgeted"] for r in rows if not r.get("tracks_actual", True))
        ),
    }


def budget_vs_actual(church, year):
    """Backward-compatible wrapper used by transactions.services."""
    rows = budget_summary(church, year, level="CHURCH")
    return [
        {
            "account": row["account"],
            "budgeted": row["budgeted"],
            "actual": row["actual"],
            "variance": row["variance"],
            "favorable": row.get("favorable", row["variance"] >= 0),
            "over_budget": row.get("over_budget", row["variance"] < 0),
            "account_type": row.get("account_type", ""),
        }
        for row in rows
    ]


def export_budget_table(rows, year, scope_label):
    headers = ["Account", "Type", "Level", "Department", "Budgeted", "Actual", "Variance", "Status"]
    table_rows = []
    for row in rows:
        if row.get("tracks_actual", True) and row.get("actual") is not None:
            status = "On track" if row.get("favorable") else "Over budget"
            actual_display = row["actual"]
            variance_display = row["variance"]
        else:
            status = "Allocation"
            actual_display = "N/A"
            variance_display = row["budgeted"]
        table_rows.append([
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
        "subtitle": scope_label,
        "headers": headers,
        "rows": table_rows,
    }


def resolve_budget_scope(request, level="CHURCH"):
    """Resolve church/district/conference for the active planning scope."""
    from church_system.church_scope import get_active_church, get_user_church

    church = get_active_church(request) or get_user_church(request.user)
    district = None
    conference = None
    scope_label = "Church"

    if level == "CHURCH":
        if not church:
            raise BudgetServiceError("Select a church to plan church-level budgets.")
        scope_label = church.name
    elif level == "DEPARTMENT":
        if not church:
            raise BudgetServiceError("Select a church to plan department budgets.")
        scope_label = f"{church.name} — Departments"
    elif level == "DISTRICT":
        if church:
            district = church.district
        elif request.user.church_id:
            district = request.user.church.district
        if not district:
            raise BudgetServiceError("District context is required for district budgets.")
        scope_label = f"District: {district.name}"
    elif level == "CONFERENCE":
        if not can_view_all_churches(request.user):
            raise BudgetServiceError("Conference budgets require hierarchy access.")
        if church:
            conference = church.district.zone.conference
        if not conference:
            raise BudgetServiceError("Select a church in the conference to plan conference budgets.")
        scope_label = f"Conference: {conference.name}"
    else:
        raise BudgetServiceError(f"Unknown budget level: {level}")

    return {
        "church": church,
        "district": district,
        "conference": conference,
        "scope_label": scope_label,
    }


def apply_budget_scope(budget, church=None, district=None, conference=None):
    """Populate FK fields from level and active scope."""
    budget.church = None
    budget.district = None
    budget.conference = None
    budget.department_id = None if budget.level != "DEPARTMENT" else budget.department_id

    if budget.level in {"CHURCH", "DEPARTMENT"}:
        budget.church = church
        if budget.level == "CHURCH":
            budget.department = None
    elif budget.level == "DISTRICT":
        budget.district = district or (church.district if church else None)
    elif budget.level == "CONFERENCE":
        if conference:
            budget.conference = conference
        elif church:
            budget.conference = church.district.zone.conference


def save_budget(budget, user, church, is_new=False, old_amount=None):
    """Persist budget and audit."""
    audit_church = church or budget.church
    if not audit_church:
        raise BudgetServiceError("Church context is required to save a budget.")
    repo.save_budget(budget)
    if is_new:
        log_budget_audit(audit_church, "BUDGET_CREATE", user, budget)
    else:
        log_budget_audit(
            audit_church,
            "BUDGET_UPDATE",
            user,
            budget,
            details={"previous_amount": str(old_amount)} if old_amount is not None else None,
        )
    return budget


def budget_has_approved_actuals(budget) -> bool:
    """True when approved transactions exist for this budget line's scope."""
    if budget.level == "DEPARTMENT":
        return False
    churches = _churches_for_budget(budget)
    if not churches.exists():
        return False
    actual = _account_actual(churches, budget.account, budget.year)
    return actual > Decimal("0")


def delete_budget(budget, user, church):
    if budget_has_approved_actuals(budget):
        raise BudgetServiceError(
            "Cannot delete a budget line with approved transactions in this year."
        )
    log_budget_audit(church, "BUDGET_DELETE", user, budget)
    repo.delete_budget(budget)


def available_budget_levels(user, church):
    levels = [("CHURCH", "Church"), ("DEPARTMENT", "Department")]
    if church and church.district_id:
        levels.append(("DISTRICT", "District"))
    if can_view_all_churches(user):
        levels.append(("CONFERENCE", "Conference"))
    return levels


def duplicate_budget_exists(budget):
    return selectors.duplicate_budget_exists(budget)


def validate_budget_instance(budget):
    if duplicate_budget_exists(budget):
        raise ValidationError("A budget line already exists for this account, year, and scope.")


def get_editable_budget(request, pk):
    """Load a budget the user may edit/delete within active church context."""
    from django.http import Http404

    from church_system.church_scope import get_active_church, get_user_church

    church = get_active_church(request) or get_user_church(request.user)
    if not church:
        raise BudgetServiceError("Select a church context to manage budgets.")

    budget = selectors.budget_by_pk(pk)
    if not budget:
        raise Http404

    if budget.level in {"CHURCH", "DEPARTMENT"}:
        if budget.church_id != church.pk:
            raise Http404
    elif budget.level == "DISTRICT":
        if budget.district_id != church.district_id:
            raise Http404
    elif budget.level == "CONFERENCE":
        if not can_view_all_churches(request.user):
            raise PermissionDenied("Conference budgets require hierarchy access.")
        if budget.conference_id != church.district.zone.conference_id:
            raise Http404
    return budget, church
