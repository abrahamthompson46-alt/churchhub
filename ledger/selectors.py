"""
Read/query helpers for the ledger posting-template domain.

Ledger stores LedgerCategory templates only. Account / Transaction reads here
support CoA UI and ledger-sourced journal lists — books of record remain in
transactions. Business rules stay in services; persistence in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404

from ledger.models import LedgerCategory
from members.models import Member
from transactions.models import Account, Budget, Transaction, TransactionLine


def categories_for_church_qs(church, *, include_inactive=False):
    qs = LedgerCategory.objects.filter(church=church).select_related(
        "default_debit_account",
        "default_credit_account",
    )
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return qs


def categories_for_type_qs(church, transaction_type):
    return categories_for_church_qs(church).filter(transaction_type=transaction_type)


def categories_ordered(qs):
    return qs.order_by("transaction_type", "sort_order", "name")


def get_category_or_404(church, pk):
    return get_object_or_404(
        categories_for_church_qs(church, include_inactive=True),
        pk=pk,
    )


def get_active_category_or_404(church, pk):
    return get_object_or_404(
        categories_for_church_qs(church),
        pk=pk,
    )


def get_active_category_or_none(church, pk):
    return (
        categories_for_church_qs(church)
        .filter(pk=pk)
        .first()
    )


def get_active_category_for_church(church, pk):
    """Raise LedgerCategory.DoesNotExist when missing (posting path)."""
    return categories_for_church_qs(church).get(pk=pk)


def category_code_exists(church, code, *, exclude_pk=None):
    qs = LedgerCategory.objects.filter(church=church, code=code)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def category_for_church_or_none(church, pk):
    return LedgerCategory.objects.filter(pk=pk, church=church).first()


def active_category_count(church):
    return LedgerCategory.objects.filter(church=church, is_active=True).count()


def accounts_for_church_qs(church, *, active_only=False, account_type=None):
    qs = Account.objects.filter(church=church).order_by("account_type", "name")
    if active_only:
        qs = qs.filter(is_active=True)
    if account_type:
        qs = qs.filter(account_type=account_type)
    return qs


def active_accounts_for_church_qs(church):
    return Account.objects.filter(church=church, is_active=True).order_by("name")


def accounts_by_name_for_church(church):
    return {a.name: a for a in Account.objects.filter(church=church)}


def get_account_or_404(church, pk):
    return get_object_or_404(Account, pk=pk, church=church)


def account_by_type(church, account_type):
    return Account.objects.get(church=church, account_type=account_type)


def account_name_exists(church, name, *, exclude_pk=None):
    qs = Account.objects.filter(church=church, name=name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def account_code_exists(church, code, *, exclude_pk=None):
    if not code:
        return False
    qs = Account.objects.filter(church=church, code=code)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def account_has_journal_lines(account):
    return account.transaction_lines.exists()


def ledger_entries_qs(
    church,
    *,
    status="",
    transaction_type="",
    date_from=None,
    date_to=None,
    member=None,
    category=None,
):
    qs = (
        Transaction.objects.filter(
            church=church,
            ledger_category__isnull=False,
        )
        .select_related(
            "ledger_category",
            "member",
            "created_by",
        )
        .prefetch_related("lines__account")
        .order_by("-date", "-created_at")
    )
    if status:
        qs = qs.filter(approval_status=status)
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if member:
        qs = qs.filter(member=member)
    if category:
        qs = qs.filter(ledger_category=category)
    return qs


def recent_entries_for_category_qs(church, category, *, limit=8):
    return ledger_entries_qs(church, category=category)[:limit]


def approved_ledger_txns_qs(church, *, date_from=None, date_to=None):
    qs = Transaction.objects.filter(
        church=church,
        ledger_category__isnull=False,
        approval_status="APPROVED",
        is_voided=False,
    )
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return qs


def category_volume_for_transactions(cat_txns):
    return (
        TransactionLine.objects.filter(
            transaction__in=cat_txns,
            amount__gt=0,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )


def ledger_summary_counts(church):
    categories = LedgerCategory.objects.filter(church=church, is_active=True)
    entries = Transaction.objects.filter(
        church=church,
        ledger_category__isnull=False,
    )
    accounts = Account.objects.filter(church=church, is_active=True)
    return {
        "account_count": accounts.count(),
        "category_count": categories.count(),
        "receipt_count": categories.filter(transaction_type="RECEIPT").count(),
        "expense_count": categories.filter(transaction_type="EXPENSE").count(),
        "transfer_count": categories.filter(transaction_type="TRANSFER").count(),
        "entry_count": entries.count(),
        "pending_count": entries.filter(approval_status="PENDING").count(),
        "approved_count": entries.filter(
            approval_status="APPROVED", is_voided=False
        ).count(),
    }


def active_members_for_church_qs(church, *, limit=None):
    qs = Member.objects.filter(church=church, is_active=True).order_by(
        "last_name", "first_name"
    )
    if limit is not None:
        return qs[:limit]
    return qs


def member_for_church(church, pk):
    return Member.objects.filter(pk=pk, church=church).first()


def church_budget_for_account_year(church, account, year):
    return Budget.objects.filter(
        church=church,
        year=year,
        account=account,
        level="CHURCH",
    ).first()
