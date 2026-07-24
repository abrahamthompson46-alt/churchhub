"""
Read/query helpers for the members domain.

Views and services call selectors for church-scoped querysets.
Business rules stay in services; persistence writes stay in repositories.
"""

from __future__ import annotations

from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from django.utils import timezone

from church_system.church_scope import filter_by_church
from permissions.scoping import get_manageable_churches

from .models import (
    Department,
    Family,
    LeadershipRole,
    Member,
    MemberSpiritualGift,
    MemberTransfer,
    Occupation,
    Record,
    RecordType,
    SpiritualGift,
    TransferStatus,
    Visitor,
)


def _years_ago(today, years):
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def apply_age_group_filter(qs, age_group):
    """Filter by age-group using DOB date bounds (SQL), matching age_group_for_age()."""
    if not age_group:
        return qs
    today = timezone.localdate()
    if age_group == "CHILD":
        return qs.filter(date_of_birth__isnull=False, date_of_birth__gt=_years_ago(today, 13))
    if age_group == "TEEN":
        return qs.filter(
            date_of_birth__isnull=False,
            date_of_birth__lte=_years_ago(today, 13),
            date_of_birth__gt=_years_ago(today, 18),
        )
    if age_group == "YOUTH":
        return qs.filter(
            date_of_birth__isnull=False,
            date_of_birth__lte=_years_ago(today, 18),
            date_of_birth__gt=_years_ago(today, 36),
        )
    if age_group == "ADULT":
        return qs.filter(
            date_of_birth__isnull=False,
            date_of_birth__lte=_years_ago(today, 36),
            date_of_birth__gt=_years_ago(today, 60),
        )
    if age_group == "SENIOR":
        return qs.filter(date_of_birth__isnull=False, date_of_birth__lte=_years_ago(today, 60))
    return qs


# ---------------------------------------------------------------------------
# Member directory / detail
# ---------------------------------------------------------------------------


def members_directory_base_qs(request):
    return filter_by_church(
        Member.objects.select_related("church", "occupation", "department", "family"),
        request,
    )


def members_base_qs(request):
    return filter_by_church(Member.objects.all(), request)


def member_directory_qs(
    request,
    *,
    q="",
    status="",
    department="",
    gender="",
    age_group="",
):
    qs = members_directory_base_qs(request)
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(membership_number__icontains=q)
        )
    if status:
        qs = qs.filter(membership_status=status)
    if department:
        qs = qs.filter(department_id=department)
    if gender:
        qs = qs.filter(gender=gender)
    if age_group:
        qs = apply_age_group_filter(qs, age_group)
    return qs.order_by("last_name", "first_name")


def member_for_request(request, member_id, *, detail=False, with_church=False):
    qs = Member.objects.all()
    if detail:
        qs = qs.select_related("church", "occupation", "department", "family")
    elif with_church:
        qs = qs.select_related("church")
    return get_object_or_404(filter_by_church(qs, request), id=member_id)


def member_pk_for_request(request, pk):
    return get_object_or_404(filter_by_church(Member.objects.all(), request), pk=pk)


def active_members_search_qs(request):
    return filter_by_church(
        Member.objects.filter(is_active=True).select_related(
            "department", "church", "family", "occupation"
        ),
        request,
    )


def member_search_results_qs(request, *, member_id="", q=""):
    qs = active_members_search_qs(request)
    if member_id:
        return qs.filter(pk=member_id).order_by("last_name", "first_name")[:20]
    if not q:
        return qs.none()
    qs = qs.annotate(
        search_name=Concat("first_name", Value(" "), "last_name"),
    ).filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(phone__icontains=q)
        | Q(membership_number__icontains=q)
        | Q(search_name__icontains=q)
        | Q(address__icontains=q)
        | Q(membership_status__icontains=q)
        | Q(gender__icontains=q)
        | Q(department__name__icontains=q)
        | Q(family__name__icontains=q)
        | Q(occupation__name__icontains=q)
    )
    return qs.order_by("last_name", "first_name")[:20]


def member_recent_records(member, limit=10):
    return member.records.order_by("-event_date")[:limit]


def member_recent_transfers(member, limit=5):
    return member.transfers.select_related("from_church", "to_church").order_by(
        "-created_at"
    )[:limit]


def member_gift_assignments(member):
    return member.spiritual_gift_assignments.select_related("gift")


def member_active_leadership_roles(member):
    return member.leadership_roles.filter(is_active=True).select_related("department")


def member_attendance_present_count(member):
    try:
        from meetings.models import MeetingAttendance

        return MeetingAttendance.objects.filter(member=member, is_present=True).count()
    except Exception:
        return 0


def members_with_phone(church, phone, *, exclude_pk=None):
    qs = Member.objects.filter(church=church, phone=phone)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def members_with_membership_number(church, membership_number, *, exclude_pk=None):
    qs = Member.objects.filter(church=church, membership_number=membership_number)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def members_name_match(church, first_name, last_name, *, exclude_pk=None):
    qs = Member.objects.filter(
        church=church,
        first_name__iexact=(first_name or "").strip(),
        last_name__iexact=(last_name or "").strip(),
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def members_assigned_to_department(department):
    return Member.objects.filter(department=department)


def completed_transfers_from_church_count(church):
    return MemberTransfer.objects.filter(
        from_church=church,
        status=TransferStatus.COMPLETED,
    ).count()


# ---------------------------------------------------------------------------
# Records / baptism
# ---------------------------------------------------------------------------


def records_qs(
    request,
    *,
    record_type="",
    status="",
    q="",
    date_from=None,
    date_to=None,
):
    qs = filter_by_church(
        Record.objects.select_related("member", "church").order_by("-event_date"),
        request,
    )
    if record_type:
        qs = qs.filter(record_type=record_type)
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(member__first_name__icontains=q)
            | Q(member__last_name__icontains=q)
            | Q(title__icontains=q)
            | Q(place__icontains=q)
            | Q(description__icontains=q)
            | Q(certificate_number__icontains=q)
        )
    if date_from:
        qs = qs.filter(event_date__gte=date_from)
    if date_to:
        qs = qs.filter(event_date__lte=date_to)
    return qs


def record_for_request(request, pk, *, with_member=False):
    qs = Record.objects.all()
    if with_member:
        qs = qs.select_related("member")
    return get_object_or_404(filter_by_church(qs, request), pk=pk)


def baptism_records_qs(request, *, q="", date_from=None, date_to=None, status=""):
    qs = filter_by_church(
        Record.objects.filter(record_type=RecordType.BAPTISM).select_related(
            "member", "church"
        ),
        request,
    )
    if q:
        qs = qs.filter(
            Q(member__first_name__icontains=q)
            | Q(member__last_name__icontains=q)
            | Q(title__icontains=q)
            | Q(place__icontains=q)
            | Q(certificate_number__icontains=q)
            | Q(officiant__icontains=q)
        )
    if date_from:
        qs = qs.filter(event_date__gte=date_from)
    if date_to:
        qs = qs.filter(event_date__lte=date_to)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-event_date")


# ---------------------------------------------------------------------------
# Departments / families
# ---------------------------------------------------------------------------


def departments_qs(request):
    return filter_by_church(
        Department.objects.annotate(members_total=Count("members")).order_by("name"),
        request,
    )


def department_for_request(request, pk):
    return get_object_or_404(filter_by_church(Department.objects.all(), request), pk=pk)


def occupations_qs(request):
    return filter_by_church(Occupation.objects.all().order_by("name"), request)


def occupation_for_request(request, pk):
    return get_object_or_404(filter_by_church(Occupation.objects.all(), request), pk=pk)


def families_qs(request):
    return filter_by_church(
        Family.objects.select_related("head")
        .annotate(members_total=Count("members"))
        .order_by("name"),
        request,
    )


def family_for_request(request, pk):
    return get_object_or_404(
        filter_by_church(Family.objects.select_related("head"), request),
        pk=pk,
    )


def family_members(family):
    return family.members.order_by("last_name", "first_name")


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------


def transfers_for_user_qs(user, *, status=""):
    allowed_churches = get_manageable_churches(user)
    qs = (
        MemberTransfer.objects.select_related(
            "member", "from_church", "to_church", "requested_by"
        )
        .filter(Q(from_church__in=allowed_churches) | Q(to_church__in=allowed_churches))
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def transfer_for_user(user, pk):
    return get_object_or_404(
        MemberTransfer.objects.select_related(
            "member", "from_church", "to_church", "requested_by", "processed_by"
        ),
        pk=pk,
    )


def pending_transfer_exists(member):
    return MemberTransfer.objects.filter(
        member=member,
        status=TransferStatus.PENDING,
    ).exists()


# ---------------------------------------------------------------------------
# Leadership / gifts
# ---------------------------------------------------------------------------


def leadership_roles_qs(request):
    return filter_by_church(
        LeadershipRole.objects.select_related("member", "department", "church"),
        request,
    ).order_by("-is_active", "title")


def leadership_role_for_request(request, pk):
    return get_object_or_404(
        filter_by_church(
            LeadershipRole.objects.select_related("member"),
            request,
        ),
        pk=pk,
    )


def active_leadership_roles_for_member_church(member, church):
    return LeadershipRole.objects.filter(
        member=member,
        church=church,
        is_active=True,
    )


def spiritual_gifts_qs(request):
    return filter_by_church(SpiritualGift.objects.all(), request)


def gift_assignment_for_member(member, assignment_id):
    return get_object_or_404(
        MemberSpiritualGift.objects.select_related("gift"),
        pk=assignment_id,
        member=member,
    )


def active_leadership_roles_for_department(department):
    return LeadershipRole.objects.filter(department=department, is_active=True)


# ---------------------------------------------------------------------------
# Visitors
# ---------------------------------------------------------------------------


def visitors_qs(request, *, q="", status="", date_from=None, date_to=None):
    qs = filter_by_church(
        Visitor.objects.select_related(
            "church", "invited_by", "assigned_elder", "converted_member"
        ),
        request,
    )
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
        )
    if status:
        qs = qs.filter(follow_up_status=status)
    if date_from:
        qs = qs.filter(visit_date__gte=date_from)
    if date_to:
        qs = qs.filter(visit_date__lte=date_to)
    return qs.order_by("-visit_date", "-created_at")


def visitor_for_request(request, pk):
    return get_object_or_404(
        filter_by_church(
            Visitor.objects.select_related(
                "church", "invited_by", "assigned_elder", "converted_member"
            ),
            request,
        ),
        pk=pk,
    )
