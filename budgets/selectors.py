"""
Read/query helpers for the budgets planning UI.

Budget rows live on transactions.Budget (system of record). This module is
read-only: lists, detail, actuals rollups, and form querysets.
Business rules stay in services; persistence in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from members.models import Department
from organization.models import Church
from transactions.models import Account, Budget, TransactionLine


def budgets_base_qs():
    return Budget.objects.select_related(
        "account", "church", "district", "conference", "department"
    )


def budgets_for_scope_qs(
    *,
    church=None,
    year=None,
    level="CHURCH",
    district=None,
    conference=None,
):
    qs = budgets_base_qs()
    if year:
        qs = qs.filter(year=year)
    if level:
        qs = qs.filter(level=level)
    if level in {"CHURCH", "DEPARTMENT"} and church:
        qs = qs.filter(church=church)
    elif level == "DISTRICT" and district:
        qs = qs.filter(district=district)
    elif level == "CONFERENCE" and conference:
        qs = qs.filter(conference=conference)
    return qs.order_by("account__name", "department__name")


def budget_by_pk(pk):
    return budgets_base_qs().filter(pk=pk).first()


def churches_for_budget_qs(budget):
    if budget.level == "CHURCH":
        return Church.objects.filter(pk=budget.church_id)
    if budget.level == "DEPARTMENT":
        return Church.objects.filter(pk=budget.church_id)
    if budget.level == "DISTRICT" and budget.district_id:
        return Church.objects.filter(district_id=budget.district_id)
    if budget.level == "CONFERENCE" and budget.conference_id:
        return Church.objects.filter(district__zone__conference_id=budget.conference_id)
    return Church.objects.none()


def account_actual_for_year(churches_qs, account, year):
    """Sum approved transaction lines for an account across churches in a year."""
    actual = TransactionLine.objects.filter(
        account=account,
        transaction__church__in=churches_qs,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__year=year,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(actual)


def duplicate_budget_qs(budget):
    qs = Budget.objects.filter(
        year=budget.year, account=budget.account, level=budget.level
    )
    if budget.pk:
        qs = qs.exclude(pk=budget.pk)
    if budget.level == "CHURCH":
        return qs.filter(church=budget.church, department__isnull=True)
    if budget.level == "DEPARTMENT":
        return qs.filter(church=budget.church, department=budget.department)
    if budget.level == "DISTRICT":
        return qs.filter(district=budget.district)
    if budget.level == "CONFERENCE":
        return qs.filter(conference=budget.conference)
    return Budget.objects.none()


def duplicate_budget_exists(budget):
    return duplicate_budget_qs(budget).exists()


def accounts_for_church_qs(church):
    if not church:
        return Account.objects.none()
    return Account.objects.filter(church=church).order_by("name")


def departments_for_church_qs(church):
    if not church:
        return Department.objects.none()
    return Department.objects.filter(church=church).order_by("name")
