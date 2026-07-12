"""Member giving history from approved transactions."""

from decimal import Decimal

from django.db.models import Sum

from accounts.permissions import can_manage_finances, can_manage_members
from transactions.models import Transaction, TransactionLine


GIVING_ACCOUNT_TYPES = ("TITHE", "COMBINED", "INCOME", "WELFARE_FUND")


def can_view_member_giving(user, member):
    if can_manage_finances(user):
        return True
    if can_manage_members(user):
        return True
    linked = getattr(user, "member_id", None)
    return linked is not None and linked == member.pk


def member_giving_lines(member, year=None):
    txns = Transaction.objects.filter(
        member=member,
        approval_status="APPROVED",
        is_voided=False,
    ).order_by("-date")
    if year:
        txns = txns.filter(date__year=year)
    lines = TransactionLine.objects.filter(
        transaction__in=txns,
        account__account_type__in=GIVING_ACCOUNT_TYPES,
    ).select_related("transaction", "account")
    return lines


def member_giving_summary(member, year=None):
    lines = member_giving_lines(member, year)
    by_type = {}
    for acc_type in GIVING_ACCOUNT_TYPES:
        total = lines.filter(account__account_type=acc_type).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        by_type[acc_type] = abs(total)
    by_type["total"] = sum(by_type.values())

    from remittance.welfare_services import member_welfare_summary

    welfare = member_welfare_summary(member, year=year)
    by_type["welfare_contributed"] = welfare["contributed"]
    by_type["welfare_received"] = welfare["received"]
    return by_type


def church_giving_leaders(church, year=None, limit=20):
    """Top contributing members for a church."""
    from members.models import Member

    txns = Transaction.objects.filter(
        church=church,
        approval_status="APPROVED",
        is_voided=False,
        member__isnull=False,
    )
    if year:
        txns = txns.filter(date__year=year)
    lines = TransactionLine.objects.filter(
        transaction__in=txns,
        account__account_type__in=("TITHE", "COMBINED"),
    )
    totals = {}
    for line in lines.select_related("transaction__member"):
        mid = line.transaction.member_id
        totals[mid] = totals.get(mid, Decimal("0")) + abs(line.amount)
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
    members = {m.pk: m for m in Member.objects.filter(pk__in=[r[0] for r in ranked])}
    return [{"member": members[mid], "total": total} for mid, total in ranked if mid in members]
