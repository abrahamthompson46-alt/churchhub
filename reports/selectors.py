"""
Read/query helpers for the reports domain.

Services call selectors for scoped querysets and aggregates.
Permission gates and report formatting stay in services.
Persistence (audit / export jobs) stays in repositories.
"""

from __future__ import annotations

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from church_system.church_scope import get_active_church, get_user_church
from members.models import Member, MemberTransfer
from organization.models import Church, Conference, District, Zone
from permissions.checks import can_view_all_churches
from permissions.scoping import get_manageable_churches
from transactions.models import Account, Transaction, TransactionLine

from .models import ReportExportJob


# ---------------------------------------------------------------------------
# Church / transaction / member scope
# ---------------------------------------------------------------------------


def churches_in_scope(
    request, conference_id=None, zone_id=None, district_id=None, church_id=None
):
    """
    Resolve church queryset from hierarchy filters.

    Always intersects with get_manageable_churches(user). Out-of-scope IDs yield empty.
    """
    user = request.user
    manageable = get_manageable_churches(user)
    qs = manageable

    if church_id:
        qs = qs.filter(pk=church_id)
    elif district_id:
        qs = qs.filter(district_id=district_id)
    elif zone_id:
        qs = qs.filter(district__zone_id=zone_id)
    elif conference_id:
        qs = qs.filter(district__zone__conference_id=conference_id)
    else:
        active = get_active_church(request)
        if active and manageable.filter(pk=active.pk).exists():
            return Church.objects.filter(pk=active.pk)
        if can_view_all_churches(user):
            return qs
        user_church = get_user_church(user)
        if user_church and manageable.filter(pk=user_church.pk).exists():
            return Church.objects.filter(pk=user_church.pk)
        return Church.objects.none()

    return qs


def transactions_in_scope(request, start, end, **hierarchy):
    churches = churches_in_scope(request, **hierarchy)
    return Transaction.objects.filter(
        church__in=churches,
        date__gte=start,
        date__lte=end,
        approval_status="APPROVED",
        is_voided=False,
    )


def members_in_scope(request, **hierarchy):
    churches = churches_in_scope(request, **hierarchy)
    return Member.objects.filter(church__in=churches)


def transaction_lines_for_transactions(txns):
    return TransactionLine.objects.filter(transaction__in=txns).select_related("account")


def sum_line_amount_for_type(lines, acc_type):
    return lines.filter(account__account_type=acc_type).aggregate(t=Sum("amount"))["t"]


def tithe_combined_by_member(txns):
    return (
        TransactionLine.objects.filter(
            transaction__in=txns,
            account__account_type__in=["TITHE", "COMBINED"],
            transaction__member__isnull=False,
        )
        .values(
            "transaction__member_id",
            "transaction__member__first_name",
            "transaction__member__last_name",
            "account__account_type",
        )
        .annotate(total=Sum("amount"))
    )


def transfers_in_scope(churches, start, end):
    return MemberTransfer.objects.filter(
        Q(from_church__in=churches) | Q(to_church__in=churches),
        transfer_date__gte=start,
        transfer_date__lte=end,
    ).select_related("member", "from_church", "to_church")


def attendance_events_in_scope(churches, start, end):
    from meetings.models import AttendanceEvent

    return (
        AttendanceEvent.objects.filter(
            church__in=churches,
            event_date__gte=start,
            event_date__lte=end,
        )
        .select_related("church")
        .annotate(
            present_count=Count("records", filter=Q(records__is_present=True)),
            total_count=Count("records"),
        )
        .order_by("-event_date")
    )


def church_district_rows(churches):
    return list(churches.values("id", "district_id", "district__name"))


def district_tithe_combined_aggregates(church_ids, start, end):
    return (
        TransactionLine.objects.filter(
            transaction__church_id__in=church_ids,
            transaction__date__gte=start,
            transaction__date__lte=end,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__account_type__in=["TITHE", "COMBINED"],
        )
        .values("transaction__church__district_id", "account__account_type")
        .annotate(total=Sum("amount"))
    )


def church_names_set(churches):
    return set(churches.values_list("name", flat=True))


def lines_for_churches(churches, end, start=None):
    qs = TransactionLine.objects.filter(
        transaction__church__in=churches,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__lte=end,
    ).select_related("account", "transaction__church")
    if start:
        qs = qs.filter(transaction__date__gte=start)
    return qs


def account_balance_aggregates(churches, end, start=None):
    qs = TransactionLine.objects.filter(
        transaction__church__in=churches,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__lte=end,
    )
    if start:
        qs = qs.filter(transaction__date__gte=start)
    return qs.values(
        "account_id",
        "account__name",
        "account__account_type",
        "transaction__church_id",
        "transaction__church__name",
    ).annotate(balance=Sum("amount"))


def accounts_by_ids(account_ids):
    return {a.pk: a for a in Account.objects.filter(pk__in=account_ids)}


def welfare_contributions_in_scope(churches, start, end):
    from remittance.models import WelfareContribution

    return WelfareContribution.objects.filter(
        church__in=churches,
        contribution_date__gte=start,
        contribution_date__lte=end,
    ).select_related("member", "church", "transaction")


def welfare_cases_in_scope(churches, start, end):
    from remittance.models import WelfareAssistanceCase

    return WelfareAssistanceCase.objects.filter(
        church__in=churches,
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).select_related("member", "church")


def welfare_contribution_total(contributions):
    return contributions.aggregate(total=Sum("amount"))["total"]


def welfare_disbursed_total(cases):
    return cases.filter(status="DISBURSED").aggregate(total=Sum("amount_approved"))["total"]


def member_gender_counts(members):
    return members.values("gender").annotate(count=Count("id")).order_by("gender")


def member_status_counts(members):
    return (
        members.values("membership_status")
        .annotate(count=Count("id"))
        .order_by("membership_status")
    )


def member_department_counts(members):
    return (
        members.filter(department__isnull=False)
        .values("department__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )


# ---------------------------------------------------------------------------
# Hierarchy filter dropdowns
# ---------------------------------------------------------------------------


def empty_conferences():
    return Conference.objects.none()


def empty_zones():
    return Zone.objects.none()


def empty_districts():
    return District.objects.none()


def empty_churches():
    return Church.objects.none()


def conferences_by_ids(conf_ids):
    return Conference.objects.filter(pk__in=conf_ids).order_by("name")


def zones_by_ids(zone_ids):
    return Zone.objects.filter(pk__in=zone_ids).select_related("conference").order_by("name")


def districts_by_ids(dist_ids):
    return District.objects.filter(pk__in=dist_ids).select_related("zone").order_by("name")


def manageable_churches_ordered(manageable):
    return manageable.select_related("district").order_by("name")


def manageable_hierarchy_ids(manageable):
    return {
        "conference_ids": manageable.values_list(
            "district__zone__conference_id", flat=True
        ).distinct(),
        "zone_ids": manageable.values_list("district__zone_id", flat=True).distinct(),
        "district_ids": manageable.values_list("district_id", flat=True).distinct(),
    }


# ---------------------------------------------------------------------------
# Export jobs
# ---------------------------------------------------------------------------


def export_job_for_user(user, pk):
    return get_object_or_404(ReportExportJob, pk=pk, user=user)


def export_job_by_id(job_id):
    return ReportExportJob.objects.select_related("user").get(pk=job_id)
