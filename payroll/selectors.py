"""
Read/query helpers for the payroll domain.

Views and services call selectors for church-scoped querysets.
Business rules stay in services; persistence writes stay in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404

from .models import (
    DeductionType,
    Employee,
    EmployeeCompensation,
    EmployeeLoan,
    PayComponentType,
    PayrollLine,
    PayrollRun,
    PayrollTaxTable,
    StatutoryContributionRule,
)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------


def employees_for_church(church, *, status=None, unit_type=None):
    qs = Employee.objects.filter(host_church=church).select_related(
        "department", "member", "user"
    )
    if status:
        qs = qs.filter(status=status)
    if unit_type:
        qs = qs.filter(paying_unit_type=unit_type)
    return qs


def active_employee_count(church):
    return Employee.objects.filter(host_church=church, status="ACTIVE").count()


def employee_for_church(church, pk):
    return get_object_or_404(Employee, pk=pk, host_church=church)


def employees_for_run(payroll_run):
    return Employee.objects.filter(
        host_church=payroll_run.host_church,
        paying_unit_type=payroll_run.paying_unit_type,
        paying_unit_id=payroll_run.paying_unit_id,
        status="ACTIVE",
    ).select_related("department")


def employee_active_loans(employee):
    return EmployeeLoan.objects.filter(employee=employee, status="ACTIVE")


def employee_compensations(employee):
    return employee.compensations.prefetch_related(
        "lines__pay_component", "lines__deduction_type"
    ).order_by("-effective_from")


def active_compensation(employee, as_of_date):
    return (
        EmployeeCompensation.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from")
        .first()
    )


def loan_for_employee(loan_id, employee):
    return EmployeeLoan.objects.filter(pk=loan_id, employee=employee).first()


def loan_by_pk(loan_id):
    return EmployeeLoan.objects.filter(pk=loan_id).first()


def first_active_loan(employee):
    return EmployeeLoan.objects.filter(employee=employee, status="ACTIVE").first()


# ---------------------------------------------------------------------------
# Component / deduction / policy catalogs
# ---------------------------------------------------------------------------


def active_pay_components(church):
    return PayComponentType.objects.filter(host_church=church, is_active=True)


def active_voluntary_deductions(church):
    return DeductionType.objects.filter(
        host_church=church, is_active=True, is_statutory=False
    ).exclude(code__in=("PAYE", "SSNIT_EE", "PENSION_T2"))


def statutory_rules_for_church(church):
    return StatutoryContributionRule.objects.filter(host_church=church).order_by(
        "code", "-effective_from"
    )


def tax_tables_for_church(church):
    return PayrollTaxTable.objects.filter(host_church=church).prefetch_related("bands")


def tax_table_for_church(church, table_pk):
    return get_object_or_404(PayrollTaxTable, pk=table_pk, host_church=church)


def active_tax_table(church, as_of_date):
    return (
        PayrollTaxTable.objects.filter(
            host_church=church,
            is_active=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from")
        .first()
    )


def active_tax_table_exists(church):
    return PayrollTaxTable.objects.filter(host_church=church, is_active=True).exists()


def active_statutory_rules_qs(church, as_of_date):
    return StatutoryContributionRule.objects.filter(
        host_church=church,
        is_active=True,
        effective_from__lte=as_of_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))


# ---------------------------------------------------------------------------
# Payroll runs / lines
# ---------------------------------------------------------------------------


def recent_runs_for_church(church, limit=20):
    return PayrollRun.objects.filter(host_church=church).order_by("-year", "-month")[
        :limit
    ]


def runs_for_church(church):
    return PayrollRun.objects.filter(host_church=church).order_by("-year", "-month")


def over_budget_run_count(church):
    return (
        PayrollRun.objects.filter(
            host_church=church,
            budget_warning__over_budget=True,
        )
        .exclude(status__in=("VOID", "PAID"))
        .count()
    )


def run_for_church(church, pk):
    return get_object_or_404(PayrollRun, pk=pk, host_church=church)


def run_exists_for_period(host_church, paying_unit_type, paying_unit_id, year, month):
    return (
        PayrollRun.objects.filter(
            host_church=host_church,
            paying_unit_type=paying_unit_type,
            paying_unit_id=paying_unit_id,
            year=year,
            month=month,
        )
        .exclude(status="VOID")
        .exists()
    )


def last_run_for_reference_prefix(church, prefix):
    return (
        PayrollRun.objects.filter(host_church=church, reference__startswith=prefix)
        .order_by("-reference")
        .first()
    )


def run_lock_for_update(run_pk):
    return PayrollRun.objects.select_for_update().get(pk=run_pk)


def payroll_line_for_payslip(line_pk):
    return get_object_or_404(
        PayrollLine.objects.select_related(
            "payroll_run", "employee", "employee__user"
        ),
        pk=line_pk,
    )


def employee_posted_payslips(employee):
    return (
        PayrollLine.objects.filter(
            employee=employee,
            payroll_run__status__in=("POSTED", "PAID"),
        )
        .select_related("payroll_run")
        .order_by("-payroll_run__year", "-payroll_run__month")
    )


def ytd_lines_for_employee(employee, year):
    return PayrollLine.objects.filter(
        employee=employee,
        payroll_run__year=year,
        payroll_run__status__in=("POSTED", "PAID"),
    )


def hierarchy_runs_qs(church_ids, year, month=None):
    qs = PayrollRun.objects.filter(
        year=year,
        host_church_id__in=church_ids,
    ).exclude(status__in=("DRAFT", "VOID", "REJECTED"))
    if month:
        qs = qs.filter(month=month)
    return qs


def ytd_posted_gross(church, year) -> Decimal:
    total = PayrollRun.objects.filter(
        host_church=church,
        year=year,
        status__in=("POSTED", "PAID"),
    ).aggregate(total=Sum("total_gross"))["total"]
    return total or Decimal("0")


def salary_expense_account(church):
    from transactions.models import Account

    return Account.objects.filter(church=church, account_type="SALARY_EXPENSE").first()


def salary_budget(church, year, account):
    from transactions.models import Budget

    return Budget.objects.filter(church=church, year=year, account=account).first()


def salary_expense_line_for_transaction(transaction):
    from transactions.models import TransactionLine

    return (
        TransactionLine.objects.filter(
            transaction=transaction,
            account__account_type="SALARY_EXPENSE",
        )
        .order_by("id")
        .first()
    )


def org_unit_by_type(unit_type, unit_id):
    from organization.models import Church, Conference, District, GeneralConference, Union

    model_map = {
        "CHURCH": Church,
        "DISTRICT": District,
        "CONFERENCE": Conference,
        "UNION": Union,
        "GENERAL_CONFERENCE": GeneralConference,
    }
    model = model_map.get(unit_type)
    if not model:
        return None
    return model.objects.filter(pk=unit_id).first()
