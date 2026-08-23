"""
Read/query helpers for the transactions domain.

Views and services call selectors for church-scoped querysets.
Business rules stay in services; persistence writes stay in repositories.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404

from church_system.church_scope import filter_by_church

from .models import (
    Account,
    BankReconciliation,
    FinancialAuditLog,
    FinancialPeriod,
    Transaction,
    WorkingDay,
)


# ---------------------------------------------------------------------------
# Working day / period reads (pure queries)
# ---------------------------------------------------------------------------


def active_working_day(church):
    """Return the currently open working day for a church, if any."""
    return (
        WorkingDay.objects.filter(church=church, status=WorkingDay.STATUS_OPEN)
        .select_related("opened_by", "closed_by")
        .order_by("-date")
        .first()
    )


def last_closed_working_day(church):
    return (
        WorkingDay.objects.filter(church=church, status=WorkingDay.STATUS_CLOSED)
        .select_related("closed_by")
        .order_by("-date")
        .first()
    )


def recent_working_days(church, limit=10):
    return list(
        WorkingDay.objects.filter(church=church)
        .select_related("opened_by", "closed_by")
        .order_by("-date")[:limit]
    )


def working_day_for_date(church, business_date):
    return WorkingDay.objects.filter(church=church, date=business_date).first()


def financial_periods_for_year(church, year):
    return FinancialPeriod.objects.filter(church=church, year=year)


def is_financial_period_locked(church, year, month):
    return FinancialPeriod.objects.filter(
        church=church,
        year=year,
        month=month,
        is_locked=True,
    ).exists()


def remittance_audit_for_transaction(transaction):
    return FinancialAuditLog.objects.filter(
        transaction=transaction,
        action="REMIT",
    ).first()


def account_by_church_and_name(church, name):
    return Account.objects.get(church=church, name=name)


def account_by_church_and_type(church, account_type):
    return Account.objects.filter(church=church, account_type=account_type).first()


# ---------------------------------------------------------------------------
# Request-scoped transaction / audit / reconciliation reads (for views)
# ---------------------------------------------------------------------------


def pending_transactions_qs(request):
    return (
        filter_by_church(
            Transaction.objects.filter(approval_status="PENDING"),
            request,
        )
        .select_related("member", "church")
        .prefetch_related("lines__account")
        .order_by("-date")
    )


def pending_transactions_by_ids_qs(request, ids):
    return filter_by_church(
        Transaction.objects.filter(id__in=ids, approval_status="PENDING"),
        request,
    )


def scoped_transactions_qs(request):
    return filter_by_church(Transaction.objects.all(), request)


def transaction_for_request(request, pk, *, detail=False):
    qs = Transaction.objects.all()
    if detail:
        qs = qs.prefetch_related("lines__account", "reversals")
    return get_object_or_404(filter_by_church(qs, request), pk=pk)


def approved_statement_transactions_qs(request, start_date=None, end_date=None):
    qs = filter_by_church(
        Transaction.objects.filter(approval_status="APPROVED", is_voided=False),
        request,
    ).order_by("date", "created_at")
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    return qs


def audit_logs_qs(request):
    return filter_by_church(
        FinancialAuditLog.objects.select_related(
            "performed_by", "transaction", "church"
        ),
        request,
    ).order_by("-created_at")


def transaction_list_qs(
    request,
    *,
    date_from,
    date_to,
    status="",
    txn_type="",
    include_voided=False,
):
    qs = (
        filter_by_church(
            Transaction.objects.select_related("member", "church", "created_by"),
            request,
        )
        .prefetch_related("lines__account")
        .filter(date__gte=date_from, date__lte=date_to)
        .order_by("-date", "-created_at")
    )
    if status:
        qs = qs.filter(approval_status=status)
        if status == "REVERSED":
            include_voided = True
    if txn_type:
        qs = qs.filter(transaction_type=txn_type)
    if not include_voided:
        qs = qs.filter(is_voided=False)
        qs = qs.exclude(reversal_of__isnull=False)
    return qs


def reconciliations_qs(request):
    return filter_by_church(
        BankReconciliation.objects.select_related("bank_account", "reconciled_by"),
        request,
    ).order_by("-statement_date")


def reconciliation_for_request(request, pk):
    return get_object_or_404(
        filter_by_church(
            BankReconciliation.objects.select_related("bank_account", "reconciled_by"),
            request,
        ),
        pk=pk,
    )


def reconciliation_items(reconciliation):
    return reconciliation.items.select_related(
        "transaction_line__transaction"
    ).order_by("-transaction_line__transaction__date")
