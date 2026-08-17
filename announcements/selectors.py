"""
Read/query helpers for the announcements / communications domain.

Views, services, and calendar call selectors for announcement and related reads.
Business rules stay in services; persistence stays in repositories.

INV-ANN-01 / INV-ANN-02: denomination is the SaaS wall. Never OR naked
visibility=general without a denomination predicate.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from church_system.church_scope import filter_by_church
from church_system.denomination_scope import get_user_denomination
from members.models import Member
from meetings.models import Meeting, MeetingStatus
from permissions.scoping import get_manageable_churches

from .models import Announcement, AnnouncementView


def pending_announcements_base_qs():
    return Announcement.objects.filter(
        is_approved=False,
        is_archived=False,
        is_rejected=False,
        status=Announcement.STATUS_PENDING,
        denomination__isnull=False,
    ).select_related("church", "created_by", "denomination")


def approved_announcements_base_qs(*, now=None):
    now = now or timezone.now()
    return Announcement.objects.filter(
        is_approved=True,
        is_archived=False,
        is_rejected=False,
        denomination__isnull=False,
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


def announcements_for_user_scope(qs, user):
    """
    Church-scoped rows in manageable churches OR general rows for the user's
    denomination. Missing user denomination → empty (INV-DENY-01).
    """
    denom = get_user_denomination(user)
    if not denom:
        return qs.none()
    churches = get_manageable_churches(user)
    church_ids = list(churches.values_list("pk", flat=True))
    general_q = Q(visibility="general", denomination_id=denom.pk)
    if church_ids:
        return qs.filter(
            general_q | Q(visibility="church", church_id__in=church_ids, denomination_id=denom.pk)
        )
    from church_system.church_scope import get_user_church

    church = get_user_church(user)
    if church and getattr(church, "pk", None):
        return qs.filter(
            general_q
            | Q(visibility="church", church_id=church.pk, denomination_id=denom.pk)
        )
    return qs.filter(general_q)


def announcements_for_church_ids(qs, church_ids, *, denomination):
    """Church-id list plus same-denomination general rows only."""
    if not denomination:
        return qs.none()
    return qs.filter(
        Q(visibility="general", denomination_id=denomination.pk)
        | Q(
            visibility="church",
            church_id__in=church_ids,
            denomination_id=denomination.pk,
        )
    )


def announcements_for_church(qs, church):
    from church_system.denomination_scope import get_church_denomination

    denom = get_church_denomination(church) if church else None
    if not church or not denom:
        return qs.none()
    return qs.filter(
        Q(visibility="general", denomination_id=denom.pk)
        | Q(visibility="church", church=church, denomination_id=denom.pk)
    )


def general_visibility_only(qs, *, denomination=None):
    if not denomination:
        return qs.none()
    return qs.filter(visibility="general", denomination_id=denomination.pk)


def exclude_general_visibility(qs):
    return qs.exclude(visibility="general")


def pinned_general_approved_qs(*, denomination=None, excluding_pk=None):
    if not denomination:
        return Announcement.objects.none()
    qs = Announcement.objects.filter(
        visibility="general",
        denomination_id=denomination.pk,
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
        qs.select_related("church", "created_by", "approved_by", "denomination")
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
    """Creator's announcements within their current denomination (fail closed)."""
    denom = get_user_denomination(user)
    if not denom:
        return Announcement.objects.none()
    qs = Announcement.objects.filter(
        created_by=user,
        denomination_id=denom.pk,
    ).select_related("church", "denomination")
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
        "church", "created_by", "approved_by", "rejected_by", "denomination"
    )


def get_announcement_or_404(pk, **filters):
    return get_object_or_404(Announcement, pk=pk, **filters)


def get_announcement_in_user_denomination_or_404(user, pk, **filters):
    """
    INV-ANN-03 / CH-SEC-008: load only within the user's denomination.
    Missing denomination or cross-tenant PK → 404.
    """
    from django.http import Http404

    denom = get_user_denomination(user)
    if not denom:
        raise Http404("No Announcement matches the given query.")
    qs = announcement_detail_qs().filter(
        denomination_id=denom.pk,
        denomination__isnull=False,
        **filters,
    )
    return get_object_or_404(qs, pk=pk)


def get_announcement_detail_or_404(pk):
    """Unscoped legacy helper — prefer get_announcement_in_user_denomination_or_404."""
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
    return qs.select_related("church", "denomination")[:limit]


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
        .select_related("church", "denomination")
        .order_by("event_date")[:limit]
    )


def manageable_church_exists(manageable_qs, church_pk) -> bool:
    return manageable_qs.filter(pk=church_pk).exists()
