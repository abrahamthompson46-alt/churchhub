"""
Persistence helpers for the transactions domain.

Services own business rules and call repositories for ORM writes / lookups.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import (
    Account,
    FinancialAuditLog,
    FinancialPeriod,
    MonthlyCutoff,
    OfferingCategory,
    Transaction,
    TransactionLine,
    WorkingDay,
)


def create_audit_log(*, church, action, user, transaction=None, details=None):
    return FinancialAuditLog.objects.create(
        church=church,
        transaction=transaction,
        action=action,
        performed_by=user,
        details=details or {},
    )


def get_account_by_name(church, name):
    return Account.objects.get(church=church, name=name)


def get_account_by_type(church, account_type):
    return Account.objects.get(church=church, account_type=account_type)


def filter_account_by_name(church, name):
    return Account.objects.filter(church=church, name=name).first()


def create_account(*, church, name, account_type, code="", is_active=True):
    return Account.objects.create(
        church=church,
        name=name,
        account_type=account_type,
        code=code,
        is_active=is_active,
    )


def update_or_create_account(*, church, name, defaults):
    return Account.objects.update_or_create(
        church=church,
        name=name,
        defaults=defaults,
    )


def save_account_fields(account, *, update_fields):
    account.save(update_fields=update_fields)
    return account


def get_or_create_offering_category(**kwargs):
    return OfferingCategory.objects.get_or_create(**kwargs)


def create_transaction(**fields):
    return Transaction.objects.create(**fields)


def save_transaction(transaction, *, update_fields=None):
    if update_fields is not None:
        transaction.save(update_fields=update_fields)
    else:
        transaction.save()
    return transaction


def create_transaction_line(*, transaction, account, amount, fund=""):
    return TransactionLine.objects.create(
        transaction=transaction,
        account=account,
        amount=amount,
        fund=fund,
    )


def transaction_line_sum(transaction) -> Decimal:
    total = transaction.lines.aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0.00")


def create_working_day(**fields):
    return WorkingDay.objects.create(**fields)


def save_working_day(working_day, *, update_fields=None):
    if update_fields is not None:
        working_day.save(update_fields=update_fields)
    else:
        working_day.save()
    return working_day


def get_or_create_financial_period(*, church, year, month, defaults=None):
    return FinancialPeriod.objects.get_or_create(
        church=church,
        year=year,
        month=month,
        defaults=defaults or {},
    )


def save_financial_period(period, *, update_fields=None):
    if update_fields is not None:
        period.save(update_fields=update_fields)
    else:
        period.save()
    return period


def mark_monthly_cutoff_transferred(*, cutoff_id=None, church=None, month=None, transfer_date=None):
    if cutoff_id:
        return MonthlyCutoff.objects.filter(pk=cutoff_id, transferred=False).update(
            transferred=True,
            transfer_date=transfer_date,
        )
    if church is not None and month is not None:
        return MonthlyCutoff.objects.filter(
            church=church,
            month=month,
            transferred=False,
        ).update(transferred=True, transfer_date=transfer_date)
    return 0
