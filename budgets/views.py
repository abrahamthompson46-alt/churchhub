from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from church_system.church_scope import require_church
from church_system.flash import flash_success
from permissions.checks import permission_required
from reports.exporters import export_table_csv, export_table_excel, export_table_pdf
from sitecontrol.checks import require_feature

from .forms import BudgetFilterForm, BudgetForm
from .services import (
    BudgetServiceError,
    apply_budget_scope,
    available_budget_levels,
    budget_kpis,
    budget_summary,
    budgets_for_scope,
    delete_budget,
    export_budget_table,
    get_editable_budget,
    resolve_budget_scope,
    save_budget,
)


def budget_finance_required(view_func):
    """Finance permission + budgets feature gate."""

    @login_required
    @require_feature("budgets")
    @permission_required("manage_finances")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def _list_redirect(year, level):
    return f"{reverse('budgets:list')}?year={year}&level={level}"


@budget_finance_required
def budget_list(request):
    try:
        level = request.GET.get("level", "CHURCH").upper()
        scope = resolve_budget_scope(request, level=level)
    except BudgetServiceError as exc:
        raise PermissionDenied(str(exc)) from exc

    church = scope["church"]
    year = int(request.GET.get("year", timezone.now().year))
    form = BudgetFilterForm(request.GET or {"year": year, "level": level})

    rows = budget_summary(
        church=scope["church"],
        year=year,
        level=level,
        district=scope["district"],
        conference=scope["conference"],
    )
    kpis = budget_kpis(rows)
    budgets = budgets_for_scope(
        church=scope["church"],
        year=year,
        level=level,
        district=scope["district"],
        conference=scope["conference"],
    )

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel", "pdf"):
        payload = export_budget_table(rows, year, scope["scope_label"])
        slug = f"budget-{level.lower()}-{year}"
        if export_fmt == "csv":
            return export_table_csv(payload["headers"], payload["rows"], f"{slug}.csv")
        if export_fmt == "excel":
            return export_table_excel(payload["headers"], payload["rows"], f"{slug}.xlsx", payload["title"])
        return export_table_pdf(
            payload["headers"],
            payload["rows"],
            payload["title"],
            payload["subtitle"],
            f"{slug}.pdf",
        )

    return render(request, "budgets/list.html", {
        "budgets": budgets,
        "rows": rows,
        "kpis": kpis,
        "year": year,
        "level": level,
        "form": form,
        "church": church,
        "scope_label": scope["scope_label"],
        "create_url": f"{reverse('budgets:create')}?level={level}",
        "level_tabs": available_budget_levels(request.user, church) if church else [("CHURCH", "Church")],
    })


@budget_finance_required
def budget_create(request):
    try:
        level = request.GET.get("level", "CHURCH").upper()
        scope = resolve_budget_scope(request, level=level)
    except BudgetServiceError as exc:
        raise PermissionDenied(str(exc)) from exc

    church = require_church(request)
    if request.method == "POST":
        form = BudgetForm(
            request.POST,
            church=church,
            district=scope["district"],
            conference=scope["conference"],
            user=request.user,
        )
        if form.is_valid():
            budget = form.save(commit=False)
            apply_budget_scope(
                budget,
                church=church,
                district=scope["district"],
                conference=scope["conference"],
            )
            save_budget(budget, request.user, church, is_new=True)
            flash_success(request, "Budget line added.")
            return redirect(_list_redirect(budget.year, budget.level))
    else:
        form = BudgetForm(
            church=church,
            district=scope["district"],
            conference=scope["conference"],
            user=request.user,
            initial={"year": timezone.now().year, "level": level},
        )
    return render(request, "budgets/form.html", {
        "form": form,
        "title": "Add Budget Line",
        "scope_label": scope["scope_label"],
        "level": level,
    })


@budget_finance_required
def budget_edit(request, pk):
    try:
        budget, church = get_editable_budget(request, pk)
        scope = resolve_budget_scope(request, level=budget.level)
    except BudgetServiceError as exc:
        raise PermissionDenied(str(exc)) from exc

    old_amount = budget.amount
    if request.method == "POST":
        form = BudgetForm(
            request.POST,
            instance=budget,
            church=church,
            district=scope["district"],
            conference=scope["conference"],
            user=request.user,
        )
        if form.is_valid():
            budget = form.save(commit=False)
            apply_budget_scope(
                budget,
                church=church,
                district=scope["district"],
                conference=scope["conference"],
            )
            save_budget(budget, request.user, church, is_new=False, old_amount=old_amount)
            flash_success(request, "Budget updated.")
            return redirect(_list_redirect(budget.year, budget.level))
    else:
        form = BudgetForm(
            instance=budget,
            church=church,
            district=scope["district"],
            conference=scope["conference"],
            user=request.user,
        )
    return render(request, "budgets/form.html", {
        "form": form,
        "title": "Edit Budget",
        "budget": budget,
        "scope_label": scope["scope_label"],
    })


@budget_finance_required
@require_POST
def budget_delete(request, pk):
    budget, church = get_editable_budget(request, pk)
    year, level = budget.year, budget.level
    delete_budget(budget, request.user, church)
    flash_success(request, "Budget line removed.")
    return redirect(_list_redirect(year, level))
