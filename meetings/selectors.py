"""
Read/query helpers for the meetings domain.

Views, forms, services, and workflow call selectors for church-scoped reads.
Business rules stay in services/workflow; persistence stays in repositories.
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404

from accounts.models import User
from church_system.church_scope import filter_by_church
from members.models import Department, Member

from .models import (
    AttendanceEvent,
    Meeting,
    MeetingAttachment,
    MinutesStatus,
)


def meetings_for_request(request):
    return filter_by_church(
        Meeting.objects.select_related(
            "department",
            "church",
            "created_by",
            "minutes_submitted_by",
            "minutes_approved_by",
        ),
        request,
    )


def filter_meetings_queryset(qs, cleaned_data):
    """Apply MeetingFilterForm cleaned_data to a meeting queryset."""
    q = (cleaned_data.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(agenda__icontains=q)
            | Q(location__icontains=q)
            | Q(chair_person__icontains=q)
            | Q(minutes__icontains=q)
            | Q(minutes_deliberations__icontains=q)
            | Q(minutes_motions__icontains=q)
        )
    if cleaned_data.get("meeting_type"):
        qs = qs.filter(meeting_type=cleaned_data["meeting_type"])
    if cleaned_data.get("status"):
        qs = qs.filter(status=cleaned_data["status"])
    if cleaned_data.get("minutes_status"):
        qs = qs.filter(minutes_status=cleaned_data["minutes_status"])
    if cleaned_data.get("date_from"):
        qs = qs.filter(scheduled_at__date__gte=cleaned_data["date_from"])
    if cleaned_data.get("date_to"):
        qs = qs.filter(scheduled_at__date__lte=cleaned_data["date_to"])
    return qs


def meetings_list_limited(qs, *, limit=200):
    return qs.order_by("-scheduled_at")[:limit]


def get_meeting_or_404(request, pk, *, detail=False):
    qs = meetings_for_request(request)
    if detail:
        qs = qs.prefetch_related(
            "attendees__member",
            "visitor_attendees__visitor",
            "action_items",
            "decisions",
            "attachments__uploaded_by",
        )
    return get_object_or_404(qs, pk=pk)


def pending_minutes_base_qs():
    return Meeting.objects.filter(
        minutes_status=MinutesStatus.PENDING_APPROVAL,
    ).select_related("church", "minutes_submitted_by", "department")


def meetings_for_church(church):
    return Meeting.objects.filter(church=church)


def departments_for_church(church):
    return Department.objects.filter(church=church)


def active_members_for_church(church):
    """Members eligible for meeting/event attendance rolls (active membership only)."""
    from members.models import MembershipStatus

    return Member.objects.filter(
        church=church,
        is_active=True,
        membership_status=MembershipStatus.ACTIVE,
    ).order_by("last_name", "first_name")


def member_ids_in_church(church, member_ids):
    """Attendance POST ids: same rules as the on-screen roll (active membership only)."""
    if not member_ids:
        return set()
    return set(
        active_members_for_church(church)
        .filter(pk__in=member_ids)
        .values_list("pk", flat=True)
    )


def visitors_for_attendance_roll(church):
    """Open follow-up visitors eligible for optional attendance rolls."""
    from members.models import Visitor, VisitorFollowUpStatus

    if church is None:
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
        .order_by("last_name", "first_name")
    )


def visitor_ids_in_church(church, visitor_ids):
    if not visitor_ids:
        return set()
    return set(
        visitors_for_attendance_roll(church)
        .filter(pk__in=visitor_ids)
        .values_list("pk", flat=True)
    )


def meeting_visitor_roll_ids(meeting):
    return set(meeting.visitor_attendees.values_list("visitor_id", flat=True))


def meeting_present_visitor_ids(meeting):
    return set(
        meeting.visitor_attendees.filter(is_present=True).values_list(
            "visitor_id", flat=True
        )
    )


def event_visitor_roll_ids(event):
    return set(event.visitor_records.values_list("visitor_id", flat=True))


def event_present_visitor_ids(event):
    return set(
        event.visitor_records.filter(is_present=True).values_list("visitor_id", flat=True)
    )


def meeting_attendee_member_ids(meeting):
    return set(meeting.attendees.values_list("member_id", flat=True))


def meeting_present_member_ids(meeting):
    return set(
        meeting.attendees.filter(is_present=True).values_list("member_id", flat=True)
    )


def meeting_attendance_count(meeting) -> int:
    return meeting.attendees.count()


def event_attendance_count(event) -> int:
    return event.records.count()


def event_present_member_ids(event):
    return set(
        event.records.filter(is_present=True).values_list("member_id", flat=True)
    )


def attendance_events_for_request(request):
    return filter_by_church(
        AttendanceEvent.objects.select_related("church", "department"),
        request,
    ).order_by("-event_date")


def get_attendance_event_or_404(request, pk, *, with_records=False):
    qs = filter_by_church(AttendanceEvent.objects.all(), request)
    if with_records:
        qs = qs.prefetch_related("records__member", "visitor_records__visitor")
    return get_object_or_404(qs, pk=pk)


def get_meeting_attachment_or_404(*, meeting, pk):
    return get_object_or_404(MeetingAttachment, pk=pk, meeting=meeting)


def active_users_for_church(church_id):
    return User.objects.filter(is_active=True, church_id=church_id)


def portal_live_meetings_for_church(church, *, limit=10):
    """Scheduled meetings exposed on the member portal with a join link."""
    from django.utils import timezone

    from .models import MeetingStatus

    if church is None:
        return Meeting.objects.none()
    now = timezone.now()
    return (
        Meeting.objects.filter(
            church=church,
            status=MeetingStatus.SCHEDULED,
            show_on_portal=True,
            scheduled_at__gte=now,
        )
        .exclude(join_url="")
        .select_related("department", "church")
        .order_by("scheduled_at")[:limit]
    )


def portal_live_meeting_or_404(church, pk):
    """Portal-safe meeting fetch — only portal-visible scheduled/held with join link."""
    from .models import MeetingStatus

    return get_object_or_404(
        Meeting.objects.filter(
            church=church,
            show_on_portal=True,
        )
        .exclude(join_url="")
        .filter(status__in=[MeetingStatus.SCHEDULED, MeetingStatus.HELD])
        .select_related("department", "church"),
        pk=pk,
    )
