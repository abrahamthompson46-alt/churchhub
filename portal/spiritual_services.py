"""Portal spiritual submission services."""

from __future__ import annotations

from django.utils import timezone

from church_system.church_scope import get_active_church
from permissions.scoping import get_manageable_churches

from .models import SpiritualSubmission, SpiritualSubmissionAuditLog, SpiritualSubmissionKind, SpiritualSubmissionStatus


class PortalSubmitRateLimitError(Exception):
    """Too many portal submissions in a short window."""


def assert_portal_submit_allowed(request, *, max_per_hour: int = 12) -> None:
    from django.core.cache import cache

    if not request.user.is_authenticated:
        return
    key = f"portal_spiritual_submit:{request.user.pk}"
    count = cache.get(key, 0)
    if count >= max_per_hour:
        raise PortalSubmitRateLimitError(
            "You have submitted several messages recently. Please try again later."
        )
    cache.set(key, count + 1, timeout=3600)


def _church_for_portal_user(user, member):
    if member and member.church_id:
        return member.church
    if user.church_id:
        return user.church
    return None


def create_spiritual_submission(*, user, member, kind, body, title="", is_anonymous=False):
    church = _church_for_portal_user(user, member)
    if church is None:
        raise ValueError("A church must be linked to submit.")
    if kind not in SpiritualSubmissionKind.values:
        raise ValueError("Invalid submission kind.")
    body = (body or "").strip()
    if not body:
        raise ValueError("Please enter a message.")
    submission = SpiritualSubmission.objects.create(
        church=church,
        member=member,
        submitted_by=user,
        kind=kind,
        title=(title or "").strip()[:200],
        body=body,
        is_anonymous=bool(is_anonymous),
        status=SpiritualSubmissionStatus.NEW,
    )
    SpiritualSubmissionAuditLog.objects.create(
        submission=submission,
        action=SpiritualSubmissionAuditLog.Action.CREATED,
        performed_by=user,
    )
    from portal.notifications import notify_pastoral_team_new_submission

    notify_pastoral_team_new_submission(submission)
    return submission


def submissions_for_staff_queryset(user, request):
    """Church-scoped submissions the user may review."""
    from permissions.checks import can_view_portal_submissions

    if not can_view_portal_submissions(user):
        return SpiritualSubmission.objects.none()
    qs = SpiritualSubmission.objects.select_related("church", "member", "submitted_by")
    manageable = get_manageable_churches(user)
    church_ids = list(manageable.values_list("pk", flat=True))
    if not church_ids:
        return qs.none()
    qs = qs.filter(church_id__in=church_ids)
    active = get_active_church(request)
    if active and active.pk in church_ids:
        qs = qs.filter(church=active)
    return qs


def count_new_submissions(user, request, *, kind=None):
    qs = submissions_for_staff_queryset(user, request).filter(status=SpiritualSubmissionStatus.NEW)
    if kind:
        qs = qs.filter(kind=kind)
    return qs.count()


def count_new_praise_submissions(user, request):
    qs = submissions_for_staff_queryset(user, request).filter(
        status=SpiritualSubmissionStatus.NEW,
        kind__in=(SpiritualSubmissionKind.THANKSGIVING, SpiritualSubmissionKind.TESTIMONY),
    )
    return qs.count()


def count_new_submissions_scope(user, request):
    return submissions_for_staff_queryset(user, request).filter(
        status=SpiritualSubmissionStatus.NEW
    ).count()


def mark_submission_reviewed(submission, reviewer):
    from permissions.checks import can_manage_portal_submissions

    if not can_manage_portal_submissions(reviewer):
        raise PermissionError("Not allowed to review portal submissions.")
    submission.status = SpiritualSubmissionStatus.REVIEWED
    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    SpiritualSubmissionAuditLog.objects.create(
        submission=submission,
        action=SpiritualSubmissionAuditLog.Action.REVIEWED,
        performed_by=reviewer,
    )
    return submission


def praise_wall_for_church(church, *, limit=20):
    """Reviewed thanksgiving/testimony messages for the member praise wall."""
    if not church:
        return SpiritualSubmission.objects.none()
    return SpiritualSubmission.objects.filter(
        church=church,
        status=SpiritualSubmissionStatus.REVIEWED,
        kind__in=(SpiritualSubmissionKind.THANKSGIVING, SpiritualSubmissionKind.TESTIMONY),
    ).order_by("-reviewed_at", "-created_at")[:limit]


def member_submissions_for_user(user, member, *, kind=None, limit=20):
    if not member:
        return SpiritualSubmission.objects.none()
    qs = SpiritualSubmission.objects.filter(member=member).order_by("-created_at")
    if kind:
        qs = qs.filter(kind=kind)
    return qs[:limit]
