"""
Read/query helpers for the dashboard domain.

Services call selectors for scoped querysets and aggregates.
KPI calculations and role rules stay in services.
Notification writes stay in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone

from church_system.church_scope import filter_by_church
from church_system.denomination_scope import get_user_denomination
from members.models import Member, MemberTransfer, TransferStatus
from organization.models import Conference, District
from permissions.scoping import get_manageable_churches
from transactions.models import FinancialPeriod, MonthlyCutoff, Transaction, TransactionLine

from .models import Notification

REMIT_PAYABLE_TYPES = ("TITHE_REMIT_PAYABLE", "COMBINED_REMIT_PAYABLE")
# Gross offering MTD: retain + remit portions (remittance posting uses split accounts).
TITHE_GIVING_TYPES = ("TITHE", "TITHE_REMIT_PAYABLE")
COMBINED_GIVING_TYPES = ("COMBINED", "COMBINED_RETENTION", "COMBINED_REMIT_PAYABLE")
INCOME_REMIT_TYPES = TITHE_GIVING_TYPES + COMBINED_GIVING_TYPES


# ---------------------------------------------------------------------------
# Church switch / notifications
# ---------------------------------------------------------------------------


def manageable_church_by_pk(user, pk):
    return get_manageable_churches(user).filter(pk=pk).first()


def notifications_for_user(user, *, unread_only=False, category=""):
    qs = Notification.objects.filter(user=user).order_by("-created_at")
    if unread_only:
        qs = qs.filter(read=False)
    if category:
        qs = qs.filter(category=category)
    return qs


def unread_notification_count(user):
    from church_system.perf_cache import cache_get, cache_set, notif_unread_key

    key = notif_unread_key(user.pk)
    cached = cache_get(key)
    if cached is not None:
        return cached
    count = Notification.objects.filter(user=user, read=False).count()
    cache_set(key, count, timeout=30)
    return count


def notification_for_user(user, pk):
    return get_object_or_404(Notification, pk=pk, user=user)


# ---------------------------------------------------------------------------
# Financial / cutoff reads
# ---------------------------------------------------------------------------


def transactions_for_request(request):
    return filter_by_church(Transaction.objects.all(), request)


def transactions_for_church_ids(church_ids):
    if not church_ids:
        return Transaction.objects.none()
    return Transaction.objects.filter(church_id__in=list(church_ids))


def approved_transactions(qs):
    return qs.filter(approval_status="APPROVED", is_voided=False)


def pending_transactions_count(qs):
    return qs.filter(approval_status="PENDING").count()


def lines_for_transactions(txns):
    return TransactionLine.objects.filter(transaction__in=txns)


def sum_line_amount_for_type(lines_qs, acc_type):
    return abs(
        lines_qs.filter(account__account_type=acc_type).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )


def sum_line_amounts_by_types(lines_qs, acc_types):
    """One grouped query → {account_type: abs(Sum)} for requested types."""
    rows = (
        lines_qs.filter(account__account_type__in=acc_types)
        .values("account__account_type")
        .annotate(t=Sum("amount"))
    )
    out = {t: Decimal("0") for t in acc_types}
    for row in rows:
        out[row["account__account_type"]] = abs(row["t"] or Decimal("0"))
    return out


def sum_line_amount_for_types(lines_qs, acc_types):
    return abs(
        lines_qs.filter(account__account_type__in=acc_types).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )


def sum_tithe_combined_mtd(lines_qs):
    """Gross tithe and combined offering MTD from split GL lines."""
    return (
        sum_line_amount_for_types(lines_qs, TITHE_GIVING_TYPES),
        sum_line_amount_for_types(lines_qs, COMBINED_GIVING_TYPES),
    )


def remittance_payable_mtd_amounts(church, month_start_date):
    """Return (tithe, combined, total) remittance payable GL sums for church/month."""
    approved_filter = {
        "transaction__church": church,
        "transaction__approval_status": "APPROVED",
        "transaction__is_voided": False,
        "transaction__date__month": month_start_date.month,
        "transaction__date__year": month_start_date.year,
    }
    tithe = abs(
        TransactionLine.objects.filter(
            account__account_type="TITHE_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    combined = abs(
        TransactionLine.objects.filter(
            account__account_type="COMBINED_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return tithe, combined, tithe + combined


def sum_remittance_payable_mtd_for_churches(churches, month_start_date):
    """Per-church cut-off or GL compute, summed — matches the cut-off page."""
    total = Decimal("0")
    for church in churches:
        existing = monthly_cutoff_for_church_month(church, month_start_date)
        if existing:
            total += existing.total_payable
        else:
            _, _, amount = remittance_payable_mtd_amounts(church, month_start_date)
            total += amount
    return total


def monthly_cutoff_for_church_month(church, month_start_date):
    return MonthlyCutoff.objects.filter(church=church, month=month_start_date).first()


def income_expense_trend_aggregates(lines_qs, since_date):
    return (
        lines_qs.filter(
            transaction__date__gte=since_date,
            account__account_type__in=["INCOME", "EXPENSE"],
        )
        .annotate(month=TruncMonth("transaction__date"))
        .values("month", "account__account_type")
        .annotate(total=Sum("amount"))
    )


def recent_approved_transactions(approved_qs, limit=5):
    return (
        approved_qs.select_related("church", "member", "created_by")
        .prefetch_related("lines__account")
        .order_by("-date")[:limit]
    )


def locked_period_exists(church, year, month):
    return FinancialPeriod.objects.filter(
        church=church, year=year, month=month, is_locked=True
    ).exists()


def overdue_cutoff_for_church(church, prior_month):
    return MonthlyCutoff.objects.filter(
        church=church, month=prior_month, transferred=False
    ).first()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def members_for_request(request):
    return filter_by_church(
        Member.objects.select_related("church", "department", "family"),
        request,
    )


def pending_transfers_for_church(church):
    qs = MemberTransfer.objects.filter(status=TransferStatus.PENDING)
    if church:
        qs = qs.filter(Q(from_church=church) | Q(to_church=church))
    return qs


def pending_transfers_for_church_ids(church_ids):
    return MemberTransfer.objects.filter(status=TransferStatus.PENDING).filter(
        Q(from_church_id__in=church_ids) | Q(to_church_id__in=church_ids)
    )


def active_member_count_for_churches(church_ids):
    return Member.objects.filter(church_id__in=church_ids, is_active=True).count()


def member_counts_by_church(church_ids):
    return {
        row["church_id"]: row["count"]
        for row in (
            Member.objects.filter(church_id__in=church_ids, is_active=True)
            .values("church_id")
            .annotate(count=Count("id"))
        )
    }


# ---------------------------------------------------------------------------
# Admin / hierarchy / executive
# ---------------------------------------------------------------------------


def conferences_for_admin(user, conference_ids):
    conferences = Conference.objects.filter(id__in=conference_ids)
    user_denom = get_user_denomination(user)
    if user_denom:
        conferences = conferences.filter(denomination=user_denom)
    return conferences


def district_count_for_ids(district_ids):
    return District.objects.filter(id__in=district_ids).count()


def pending_announcements_for_admin(user, church_ids):
    from announcements.models import Announcement

    pending_ann = Announcement.objects.filter(
        is_approved=False, is_archived=False, is_rejected=False
    )
    user_denom = get_user_denomination(user)
    if church_ids:
        return pending_ann.filter(Q(church_id__in=church_ids) | Q(church__isnull=True))
    if user_denom:
        return pending_ann.filter(
            Q(church__district__zone__conference__denomination=user_denom)
            | Q(church__isnull=True)
        )
    if user.is_superuser:
        return pending_ann
    return pending_ann.none()


def manageable_church_district_rows(manageable):
    return list(manageable.values("id", "district_id", "district__name"))


def district_remit_income_aggregates(church_ids, month_start_date):
    return (
        TransactionLine.objects.filter(
            transaction__church_id__in=church_ids,
            transaction__date__gte=month_start_date,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__account_type__in=REMIT_PAYABLE_TYPES + INCOME_REMIT_TYPES,
        )
        .values("transaction__church__district_id", "account__account_type")
        .annotate(total=Sum("amount"))
    )


def overdue_cutoffs_for_churches(church_ids, prior_month, limit=None):
    qs = (
        MonthlyCutoff.objects.filter(
            church_id__in=church_ids,
            month=prior_month,
            transferred=False,
        )
        .annotate(payable=F("total_tithe") + F("total_combined"))
        .filter(payable__gt=0)
        .select_related("church")
        .order_by("-payable")
    )
    if limit is not None:
        return qs[:limit]
    return qs


def overdue_cutoff_count(church_ids, prior_month):
    return overdue_cutoffs_for_churches(church_ids, prior_month).count()


def locked_periods_count(church_ids, year, month):
    return FinancialPeriod.objects.filter(
        church_id__in=church_ids,
        year=year,
        month=month,
        is_locked=True,
    ).count()


def mtd_lines_for_churches(church_ids, month_start_date):
    return TransactionLine.objects.filter(
        transaction__church_id__in=church_ids,
        transaction__date__gte=month_start_date,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
    )


def pending_transactions_for_churches_count(church_ids):
    return Transaction.objects.filter(
        church_id__in=church_ids,
        approval_status="PENDING",
    ).count()


def pending_assets_for_churches_count(church_ids):
    from assets.models import FixedAsset

    return FixedAsset.objects.filter(
        church_id__in=church_ids,
        status="PENDING_APPROVAL",
    ).count()


def church_mtd_giving_totals(church_ids, month_start_date):
    line_aggs = (
        TransactionLine.objects.filter(
            transaction__church_id__in=church_ids,
            transaction__date__gte=month_start_date,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__account_type__in=INCOME_REMIT_TYPES,
        )
        .values("transaction__church_id")
        .annotate(total=Sum("amount"))
    )
    return {
        row["transaction__church_id"]: abs(row["total"] or Decimal("0"))
        for row in line_aggs
    }


def upcoming_meetings_for_church(church, now):
    from meetings.models import Meeting, MeetingStatus

    return Meeting.objects.filter(
        church=church,
        scheduled_at__gte=now,
        status=MeetingStatus.SCHEDULED,
    ).order_by("scheduled_at")


def pending_transactions_for_request_count(request):
    return filter_by_church(
        Transaction.objects.filter(approval_status="PENDING"), request
    ).count()


def open_working_day_church_ids(church_ids):
    """Return set of church PKs that currently have an OPEN working day."""
    from transactions.models import WorkingDay

    if not church_ids:
        return set()
    return set(
        WorkingDay.objects.filter(
            church_id__in=list(church_ids),
            status=WorkingDay.STATUS_OPEN,
        ).values_list("church_id", flat=True)
    )


def open_visitors_for_church(church, *, limit=8):
    """Visitors still needing pastoral follow-up (not converted/closed)."""
    from members.models import Visitor, VisitorFollowUpStatus

    if not church:
        return Visitor.objects.none()
    open_statuses = (
        VisitorFollowUpStatus.NEW,
        VisitorFollowUpStatus.CONTACTED,
        VisitorFollowUpStatus.IN_PROGRESS,
    )
    return (
        Visitor.objects.filter(
            church=church,
            follow_up_status__in=open_statuses,
            is_deleted=False,
        )
        .select_related("assigned_elder")
        .order_by("-visit_date", "-created_at")[:limit]
    )


def open_visitors_count_for_church(church):
    from members.models import Visitor, VisitorFollowUpStatus

    if not church:
        return 0
    return Visitor.objects.filter(
        church=church,
        follow_up_status__in=(
            VisitorFollowUpStatus.NEW,
            VisitorFollowUpStatus.CONTACTED,
            VisitorFollowUpStatus.IN_PROGRESS,
        ),
        is_deleted=False,
    ).count()


def meetings_this_week_for_church(church, *, now=None, limit=5):
    from datetime import timedelta

    from meetings.models import Meeting, MeetingStatus

    if not church:
        return Meeting.objects.none()
    now = now or timezone.now()
    end = now + timedelta(days=7)
    return (
        Meeting.objects.filter(
            church=church,
            scheduled_at__gte=now,
            scheduled_at__lte=end,
            status=MeetingStatus.SCHEDULED,
        )
        .select_related("department")
        .order_by("scheduled_at")[:limit]
    )


def pending_transfers_preview_for_church(church, *, limit=5):
    if not church:
        return MemberTransfer.objects.none()
    return (
        pending_transfers_for_church(church)
        .select_related("member", "from_church", "to_church")
        .order_by("-created_at")[:limit]
    )
