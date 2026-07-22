"""
Read/query helpers for the giving portal.

Giving is a reporting/statement layer over approved Transaction / TransactionLine
data. The transactions app remains the accounting system of record.
Business rules and aggregation policy stay in services; this module is reads only.
"""

from __future__ import annotations

from django.db.models import Sum
from django.shortcuts import get_object_or_404

from church_system.church_scope import filter_by_church
from members.models import Member
from transactions.models import Transaction, TransactionLine

GIVING_LINE_ACCOUNT_TYPES = ("TITHE", "COMBINED", "INCOME", "WELFARE_FUND")
LEADERBOARD_ACCOUNT_TYPES = ("TITHE", "COMBINED")


def approved_member_transactions_qs(member, *, year=None):
    qs = Transaction.objects.filter(
        member=member,
        approval_status="APPROVED",
        is_voided=False,
    ).order_by("-date")
    if year:
        qs = qs.filter(date__year=year)
    return qs


def member_giving_lines_qs(member, *, year=None):
    txns = approved_member_transactions_qs(member, year=year)
    return TransactionLine.objects.filter(
        transaction__in=txns,
        account__account_type__in=GIVING_LINE_ACCOUNT_TYPES,
    ).select_related("transaction", "account")


def line_total_for_account_type(lines, account_type):
    return lines.filter(account__account_type=account_type).aggregate(
        t=Sum("amount")
    )["t"]


def line_totals_by_account_type(lines, account_types):
    """Single grouped aggregate: {account_type: Sum(amount)} (signed)."""
    rows = (
        lines.filter(account__account_type__in=account_types)
        .values("account__account_type")
        .annotate(t=Sum("amount"))
    )
    return {row["account__account_type"]: row["t"] for row in rows}


def church_approved_member_transactions_qs(church, *, year=None):
    qs = Transaction.objects.filter(
        church=church,
        approval_status="APPROVED",
        is_voided=False,
        member__isnull=False,
    )
    if year:
        qs = qs.filter(date__year=year)
    return qs


def church_tithe_combined_lines_qs(church, *, year=None):
    txns = church_approved_member_transactions_qs(church, year=year)
    return TransactionLine.objects.filter(
        transaction__in=txns,
        account__account_type__in=LEADERBOARD_ACCOUNT_TYPES,
    ).select_related("transaction__member")


def church_giving_leader_totals(church, *, year=None, limit=20):
    """
    Top member giving totals (tithe + combined) via ORM.

    Uses Sum(Abs(amount)) to match historical Python abs(line.amount) behaviour.
    """
    from django.db.models.functions import Abs

    return list(
        church_tithe_combined_lines_qs(church, year=year)
        .filter(transaction__member_id__isnull=False)
        .values("transaction__member_id")
        .annotate(total=Sum(Abs("amount")))
        .order_by("-total")[:limit]
    )


def members_by_ids(pks):
    return Member.objects.filter(pk__in=list(pks))


def get_scoped_member_or_404(request, member_id):
    return get_object_or_404(
        filter_by_church(Member.objects.all(), request),
        pk=member_id,
    )
