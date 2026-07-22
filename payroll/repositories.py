"""
Persistence helpers for the payroll domain.

Services own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from .models import (
    DeductionType,
    Employee,
    EmployeeCompensation,
    EmployeeCompensationLine,
    EmployeeLoan,
    PayComponentType,
    PayrollLine,
    PayrollLineItem,
    PayrollRun,
    PayrollRunAuditLog,
    PayrollTaxBand,
    PayrollTaxTable,
    StatutoryContributionRule,
)


def create_run_audit(*, payroll_run, action, performed_by, details=None):
    return PayrollRunAuditLog.objects.create(
        payroll_run=payroll_run,
        action=action,
        performed_by=performed_by,
        details=details or {},
    )


def get_or_create_pay_component(*, host_church, code, defaults):
    return PayComponentType.objects.get_or_create(
        host_church=host_church,
        code=code,
        defaults=defaults,
    )


def get_or_create_deduction_type(*, host_church, code, defaults):
    return DeductionType.objects.get_or_create(
        host_church=host_church,
        code=code,
        defaults=defaults,
    )


def create_tax_table(**fields):
    return PayrollTaxTable.objects.create(**fields)


def create_tax_band(**fields):
    return PayrollTaxBand.objects.create(**fields)


def get_or_create_statutory_rule(*, host_church, code, effective_from, defaults):
    return StatutoryContributionRule.objects.get_or_create(
        host_church=host_church,
        code=code,
        effective_from=effective_from,
        defaults=defaults,
    )


def save_employee(employee):
    employee.save()
    return employee


def create_compensation(**fields):
    return EmployeeCompensation.objects.create(**fields)


def save_compensation_line(line):
    line.full_clean()
    line.save()
    return line


def deactivate_other_compensations(employee, keep_pk):
    return (
        EmployeeCompensation.objects.filter(employee=employee)
        .exclude(pk=keep_pk)
        .update(is_active=False)
    )


def save_loan(loan):
    loan.save()
    return loan


def create_payroll_run(**fields):
    return PayrollRun.objects.create(**fields)


def save_payroll_run(run, *, update_fields=None):
    if update_fields is not None:
        run.save(update_fields=update_fields)
    else:
        run.save()
    return run


def delete_run_lines(payroll_run):
    return payroll_run.lines.all().delete()


def create_payroll_line(**fields):
    return PayrollLine.objects.create(**fields)


def create_payroll_line_item(**fields):
    return PayrollLineItem.objects.create(**fields)


def save_statutory_rule(rule):
    rule.save()
    return rule


def save_tax_band(band):
    band.save()
    return band
