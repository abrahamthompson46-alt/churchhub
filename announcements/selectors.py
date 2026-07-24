"""
Read/query helpers for the announcements / communications domain.

Views, services, and calendar call selectors for announcement and related reads.
Business rules stay in services; persistence stays in repositories.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from church_system.church_scope import filter_by_church
from members.models import Member
from meetings.models import Meeting, MeetingStatus

from .models import Announcement, AnnouncementView


def pending_announcements_base_qs():
    return Announcement.objects.filter(
        is_approved=False,
        is_archived=False,
        is_rejected=False,
        status=Announcement.STATUS_PENDING,
    ).select_related("church", "created_by")


def approved_announcements_base_qs(*, now=None):
    now = now or timezone.now()
    return Announcement.objects.filter(
        is_approved=True,
        is_archived=False,
        is_rejected=False,
    ).filter(
        Q(auto_expire=False)
        | Q(event_date__isnull=True)
        | Q(event_date__gte=now)
    )


def apply_publish_at_filter(qs, *, now=None, include_scheduled=False):
    if include_scheduled:
        return qs
    now = now or timezone.now()
    return qs.filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))


def announcements_for_church_ids(qs, church_ids):
    return qs.filter(Q(visibility="general") | Q(church_id__in=church_ids))


def announcements_for_church(qs, church):
    return qs.filter(Q(visibility="general") | Q(church=church))


def general_visibility_only(qs):
    return qs.filter(visibility="general")


def exclude_general_visibility(qs):
    return qs.exclude(visibility="general")


def pinned_general_approved_qs(*, excluding_pk=None):
    qs = Announcement.objects.filter(
        visibility="general",
        is_pinned=True,
        is_archived=False,
        is_approved=True,
    )
    if excluding_pk:
        qs = qs.exclude(pk=excluding_pk)
    return qs


def pinned_church_approved_qs(church, *, excluding_pk=None):
    qs = Announcement.objects.filter(
        church=church,
        is_pinned=True,
        is_archived=False,
        is_approved=True,
    )
    if excluding_pk:
        qs = qs.exclude(pk=excluding_pk)
    return qs


def announcement_list_annotated(qs):
    return (
        qs.select_related("church", "created_by", "approved_by")
        .prefetch_related("images")
        .annotate(view_count=Count("views", distinct=True))
        .order_by("-is_pinned", "-created_at")
    )


def filter_announcement_list(qs, *, q="", church=None, pinned_only=False):
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
    if church:
        qs = qs.filter(church=church)
    if pinned_only:
        qs = qs.filter(is_pinned=True)
    return qs


def my_announcements_qs(user, *, status=""):
    qs = Announcement.objects.filter(created_by=user).select_related("church")
    if status == "pending":
        qs = qs.filter(is_approved=False, is_archived=False, is_rejected=False)
    elif status == "approved":
        qs = qs.filter(is_approved=True, is_archived=False, is_rejected=False)
    elif status == "rejected":
        qs = qs.filter(is_rejected=True, is_archived=False)
    elif status == "archived":
        qs = qs.filter(is_archived=True)
    return qs.order_by("-created_at")


def announcement_detail_qs():
    return Announcement.objects.select_related(
        "church", "created_by", "approved_by", "rejected_by"
    )


def get_announcement_or_404(pk, **filters):
    return get_object_or_404(Announcement, pk=pk, **filters)


def get_announcement_detail_or_404(pk):
    return get_object_or_404(announcement_detail_qs(), pk=pk)


def get_from_queryset_or_404(qs, pk):
    return get_object_or_404(qs, pk=pk)


def announcement_exists_in_qs(qs, pk) -> bool:
    return qs.filter(pk=pk).exists()


def announcement_view_count(announcement) -> int:
    return announcement.views.count()


def viewed_announcement_ids_for_user(user, announcement_ids):
    return set(
        AnnouncementView.objects.filter(
            user=user, announcement_id__in=announcement_ids
        ).values_list("announcement_id", flat=True)
    )


def view_counts_by_announcement_ids(announcement_ids):
    return dict(
        AnnouncementView.objects.filter(announcement_id__in=announcement_ids)
        .values("announcement_id")
        .annotate(c=Count("id"))
        .values_list("announcement_id", "c")
    )


def announcement_with_church_for_export(qs, *, limit=5000):
    return qs.select_related("church")[:limit]


def active_members_with_dob_for_request(request):
    return filter_by_church(
        Member.objects.filter(
            is_active=True, date_of_birth__isnull=False
        ).select_related("department", "church"),
        request,
    )


def scheduled_meetings_for_church_in_window(
    church, *, start, end, limit=50, portal_visible_only=False
):
    qs = Meeting.objects.filter(
        church=church,
        scheduled_at__gte=start,
        scheduled_at__lte=end,
        status=MeetingStatus.SCHEDULED,
    )
    if portal_visible_only:
        qs = qs.filter(show_on_portal=True).exclude(join_url="")
    return qs.select_related("department").order_by("scheduled_at")[:limit]


def announcement_events_in_window(qs, *, start, end, limit=50):
    return (
        qs.filter(event_date__isnull=False, event_date__gte=start, event_date__lte=end)
        .select_related("church")
        .order_by("event_date")[:limit]
    )


def manageable_church_exists(manageable_qs, church_pk) -> bool:
    return manageable_qs.filter(pk=church_pk).exists()
