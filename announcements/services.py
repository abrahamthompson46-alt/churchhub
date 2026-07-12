"""Announcement business logic — create, approval, scoping, archive, audit."""

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Count, Q
from django.utils import timezone

from permissions.checks import can_approve_announcements, can_create_announcements, can_view_all_churches
from permissions.scoping import get_manageable_churches
from permissions.scoping_checks import (
    can_approve_for_church,
    is_top_level_approver,
    pending_for_church_scope,
)
from permissions.superadmin import is_superadmin

from .models import (
    MAX_PINNED_PER_CHURCH,
    Announcement,
    AnnouncementAuditLog,
    AnnouncementView,
)


class AnnouncementServiceError(ValueError):
    pass


def _log_audit(announcement, action, user, details=None):
    AnnouncementAuditLog.objects.create(
        announcement=announcement,
        church=announcement.church if announcement else None,
        action=action,
        performed_by=user,
        details=details or {},
    )


def can_approve_announcement(user, announcement):
    """Check if user may approve/reject this specific announcement."""
    if not can_approve_announcements(user):
        return False
    if announcement.visibility == "general":
        return is_top_level_approver(user)
    if not announcement.church_id:
        return False
    return can_approve_for_church(user, announcement.church, "approve_announcements")


def can_edit_announcement(user, announcement):
    if announcement.is_archived or announcement.is_rejected:
        return False
    if can_approve_announcement(user, announcement):
        return True
    return (
        announcement.created_by_id == user.id
        and not announcement.is_approved
        and can_create_announcements(user)
    )


def can_archive_announcement(user, announcement):
    if announcement.is_archived:
        return False
    if can_approve_announcement(user, announcement):
        return True
    return announcement.created_by_id == user.id


def pending_for_user(user):
    """Pending announcements this user is allowed to review."""
    qs = Announcement.objects.filter(
        is_approved=False,
        is_archived=False,
        is_rejected=False,
        status=Announcement.STATUS_PENDING,
    ).select_related("church", "created_by")
    if is_top_level_approver(user):
        return qs
    scoped = pending_for_church_scope(
        user,
        qs,
        "approve_announcements",
        church_lookup="church",
        submitter_field="created_by",
    )
    return scoped.exclude(visibility="general")


def visible_announcements(user, *, include_scheduled=False):
    """Approved, non-archived, non-expired announcements for the user."""
    now = timezone.now()
    qs = Announcement.objects.filter(
        is_approved=True,
        is_archived=False,
        is_rejected=False,
    ).filter(
        Q(auto_expire=False)
        | Q(event_date__isnull=True)
        | Q(event_date__gte=now)
    )
    if not include_scheduled:
        qs = qs.filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))

    if can_view_all_churches(user) or is_superadmin(user):
        return qs

    churches = get_manageable_churches(user)
    church_ids = list(churches.values_list("pk", flat=True))
    if church_ids:
        return qs.filter(Q(visibility="general") | Q(church_id__in=church_ids))

    from church_system.church_scope import get_user_church

    church = get_user_church(user)
    if church:
        return qs.filter(Q(visibility="general") | Q(church=church))
    return qs.filter(visibility="general")


def _assert_pin_limit(church, excluding_pk=None):
    if not church:
        # General (conference-wide) pins: limit globally among general visibility
        qs = Announcement.objects.filter(
            visibility="general",
            is_pinned=True,
            is_archived=False,
            is_approved=True,
        )
    else:
        qs = Announcement.objects.filter(
            church=church,
            is_pinned=True,
            is_archived=False,
            is_approved=True,
        )
    if excluding_pk:
        qs = qs.exclude(pk=excluding_pk)
    if qs.count() >= MAX_PINNED_PER_CHURCH:
        raise AnnouncementServiceError(
            f"At most {MAX_PINNED_PER_CHURCH} pinned announcements are allowed. "
            "Unpin another announcement first."
        )


def create_announcement(
    user,
    *,
    title,
    content,
    visibility="church",
    church=None,
    event_date=None,
    publish_at=None,
    auto_expire=True,
    is_pinned=False,
    auto_approve=None,
):
    """Create an announcement; auto-approve only when the creator may approve it."""
    if not can_create_announcements(user):
        raise PermissionError("You cannot create announcements.")

    title = (title or "").strip()
    content = (content or "").strip()
    if not title:
        raise AnnouncementServiceError("Title is required.")
    if not content:
        raise AnnouncementServiceError("Content is required.")

    if visibility == "general":
        church = None
        if not is_top_level_approver(user):
            raise AnnouncementServiceError(
                "Only top-level leadership can create general (conference-wide) announcements."
            )
    else:
        if not church:
            from church_system.church_scope import get_user_church

            church = get_user_church(user)
        if not church:
            raise AnnouncementServiceError("Church is required for church-scoped announcements.")
        manageable = get_manageable_churches(user)
        if not manageable.filter(pk=church.pk).exists():
            raise AnnouncementServiceError("You cannot post announcements for that church.")

    if auto_approve is None:
        auto_approve = False
        if visibility == "general":
            auto_approve = is_top_level_approver(user) and can_approve_announcements(user)
        elif church and can_approve_for_church(user, church, "approve_announcements"):
            auto_approve = True

    if is_pinned and auto_approve:
        _assert_pin_limit(church)

    with db_transaction.atomic():
        ann = Announcement(
            title=title,
            content=content,
            visibility=visibility,
            church=church,
            event_date=event_date,
            publish_at=publish_at,
            auto_expire=bool(auto_expire),
            is_pinned=bool(is_pinned) and auto_approve,
            created_by=user,
            is_approved=False,
            is_rejected=False,
            is_archived=False,
            status=Announcement.STATUS_PENDING,
        )
        if auto_approve:
            ann.is_approved = True
            ann.approved_by = user
            ann.approved_at = timezone.now()
            ann.status = Announcement.STATUS_APPROVED
        ann.full_clean()
        ann.save()
        _log_audit(
            ann,
            "CREATE",
            user,
            details={
                "title": ann.title,
                "visibility": ann.visibility,
                "auto_approved": auto_approve,
                "church_id": str(ann.church_id) if ann.church_id else None,
            },
        )
        if auto_approve:
            _log_audit(ann, "APPROVE", user, details={"auto": True})
    return ann


def update_announcement(
    announcement,
    user,
    *,
    title=None,
    content=None,
    visibility=None,
    church=None,
    event_date=None,
    publish_at=None,
    auto_expire=None,
    is_pinned=None,
    require_reapproval=True,
):
    if not can_edit_announcement(user, announcement):
        raise PermissionError("You cannot edit this announcement.")

    before = {
        "title": announcement.title,
        "visibility": announcement.visibility,
        "is_pinned": announcement.is_pinned,
        "is_approved": announcement.is_approved,
    }
    was_approved = announcement.is_approved
    editor_is_approver = can_approve_announcement(user, announcement)

    if title is not None:
        announcement.title = title.strip()
    if content is not None:
        announcement.content = content.strip()
    if visibility is not None:
        announcement.visibility = visibility
    if church is not None or visibility == "church":
        if visibility == "general" or announcement.visibility == "general":
            announcement.church = None
        elif church is not None:
            manageable = get_manageable_churches(user)
            if not manageable.filter(pk=church.pk).exists():
                raise AnnouncementServiceError("Invalid church for this announcement.")
            announcement.church = church
    if event_date is not None:
        announcement.event_date = event_date
    if publish_at is not None:
        announcement.publish_at = publish_at
    if auto_expire is not None:
        announcement.auto_expire = bool(auto_expire)

    if is_pinned is not None and editor_is_approver:
        if is_pinned and not announcement.is_pinned:
            _assert_pin_limit(announcement.church, excluding_pk=announcement.pk)
        announcement.is_pinned = bool(is_pinned)

    # Material edits to published posts by non-approvers shouldn't happen (can_edit blocks).
    # Approver edits keep published; creator edits only pending.
    # If an approver edits content of a published post and require_reapproval is True
    # for non-approver path — creators can't edit approved. For approvers, keep approved
    # but log the change. Optional: demote to pending when content changes by non-owner approver.
    if was_approved and require_reapproval and not editor_is_approver:
        announcement.is_approved = False
        announcement.approved_by = None
        announcement.approved_at = None
        announcement.status = Announcement.STATUS_PENDING

    if not announcement.title or not announcement.content:
        raise AnnouncementServiceError("Title and content are required.")

    with db_transaction.atomic():
        announcement.full_clean()
        announcement.save()
        _log_audit(
            announcement,
            "UPDATE",
            user,
            details={"before": before, "after": {
                "title": announcement.title,
                "visibility": announcement.visibility,
                "is_pinned": announcement.is_pinned,
                "is_approved": announcement.is_approved,
            }},
        )
        if is_pinned is True:
            _log_audit(announcement, "PIN", user)
        elif is_pinned is False and before.get("is_pinned"):
            _log_audit(announcement, "UNPIN", user)
    return announcement


def approve_announcement(announcement, user):
    if not can_approve_announcement(user, announcement):
        raise PermissionError("You cannot approve this announcement.")
    if announcement.is_archived:
        raise AnnouncementServiceError("Cannot approve an archived announcement.")
    if announcement.is_approved and not announcement.is_rejected:
        raise AnnouncementServiceError("Announcement is already approved.")
    if announcement.is_pinned:
        _assert_pin_limit(announcement.church, excluding_pk=announcement.pk)

    with db_transaction.atomic():
        announcement.is_approved = True
        announcement.is_rejected = False
        announcement.rejected_by = None
        announcement.rejected_at = None
        announcement.rejection_reason = ""
        announcement.approved_by = user
        announcement.approved_at = timezone.now()
        announcement.status = Announcement.STATUS_APPROVED
        announcement.save()
        _log_audit(announcement, "APPROVE", user, details={"title": announcement.title})
    return announcement


def reject_announcement(announcement, user, reason=""):
    """Soft-reject: keep the record with reason (no hard delete)."""
    if not can_approve_announcement(user, announcement):
        raise PermissionError("You cannot reject this announcement.")
    if announcement.is_approved and not announcement.is_rejected:
        raise AnnouncementServiceError("Cannot reject an approved announcement. Archive it instead.")
    if announcement.is_archived:
        raise AnnouncementServiceError("Cannot reject an archived announcement.")

    reason = (reason or "").strip()
    if not reason:
        raise AnnouncementServiceError("A rejection reason is required.")

    creator = announcement.created_by
    title = announcement.title
    with db_transaction.atomic():
        announcement.is_approved = False
        announcement.is_rejected = True
        announcement.is_pinned = False
        announcement.rejected_by = user
        announcement.rejected_at = timezone.now()
        announcement.rejection_reason = reason
        announcement.status = Announcement.STATUS_REJECTED
        announcement.save()
        _log_audit(
            announcement,
            "REJECT",
            user,
            details={"title": title, "reason": reason},
        )
    return creator, title, announcement


def archive_announcement(announcement, user):
    if not can_archive_announcement(user, announcement):
        raise PermissionError("You cannot archive this announcement.")
    with db_transaction.atomic():
        announcement.is_archived = True
        announcement.is_pinned = False
        announcement.archived_by = user
        announcement.archived_at = timezone.now()
        announcement.status = Announcement.STATUS_ARCHIVED
        announcement.save()
        _log_audit(announcement, "ARCHIVE", user, details={"title": announcement.title})
    return announcement


def get_announcement_list_queryset(user, *, q="", church=None, pinned_only=False):
    qs = visible_announcements(user).select_related(
        "church", "created_by", "approved_by"
    ).prefetch_related("images").annotate(
        view_count=Count("views", distinct=True),
    ).order_by("-is_pinned", "-created_at")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
    if church:
        qs = qs.filter(church=church)
    if pinned_only:
        qs = qs.filter(is_pinned=True)
    return qs


def get_my_announcements_queryset(user, status=""):
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


def paginate_queryset(queryset, page=1, per_page=20):
    return Paginator(queryset, per_page).get_page(page)


def export_announcements_table(queryset):
    headers = [
        "Title", "Status", "Visibility", "Church", "Pinned", "Created",
        "Approved At", "Views", "Event Date",
    ]
    rows = []
    for a in queryset.select_related("church")[:5000]:
        view_count = getattr(a, "view_count", None)
        if view_count is None:
            view_count = a.views.count()
        rows.append([
            a.title,
            a.get_status_display() if hasattr(a, "get_status_display") else a.status,
            a.get_visibility_display(),
            a.church.name if a.church_id else "General",
            "Yes" if a.is_pinned else "No",
            a.created_at.isoformat() if a.created_at else "",
            a.approved_at.isoformat() if a.approved_at else "",
            view_count,
            a.event_date.isoformat() if a.event_date else "",
        ])
    return {
        "headers": headers,
        "rows": rows,
        "title": "Announcements Register",
        "subtitle": "Church communications export",
    }


def mark_viewed(user, announcement):
    obj, created = AnnouncementView.objects.get_or_create(
        user=user, announcement=announcement
    )
    return obj, created


def view_counts_for(announcement_ids):
    return dict(
        AnnouncementView.objects.filter(announcement_id__in=announcement_ids)
        .values("announcement_id")
        .annotate(c=Count("id"))
        .values_list("announcement_id", "c")
    )
