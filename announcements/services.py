"""Announcement business logic — create, approval, scoping, archive, audit."""

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.utils import timezone

from announcements import repositories as repo
from announcements import selectors
from church_system.denomination_scope import get_church_denomination, get_user_denomination
from permissions.checks import (
    can_approve_announcements,
    can_archive_announcements,
    can_create_announcements,
)
from permissions.scoping import get_manageable_churches
from permissions.scoping_checks import (
    can_approve_for_church,
    is_top_level_approver,
    pending_for_church_scope,
)

from .models import MAX_PINNED_PER_CHURCH, Announcement


class AnnouncementServiceError(ValueError):
    pass


def _log_audit(announcement, action, user, details=None):
    repo.create_audit_log(
        announcement=announcement,
        church=announcement.church if announcement else None,
        action=action,
        performed_by=user,
        details=details or {},
    )


def _same_denomination(user, announcement) -> bool:
    """INV-ANN-01 / INV-DENY-01: missing either side fails closed."""
    if not announcement or not announcement.denomination_id:
        return False
    user_denom = get_user_denomination(user)
    if not user_denom:
        return False
    return user_denom.pk == announcement.denomination_id


def can_approve_announcement(user, announcement):
    """Check if user may approve/reject this specific announcement."""
    if not can_approve_announcements(user):
        return False
    if not _same_denomination(user, announcement):
        return False
    if announcement.visibility == "general":
        return is_top_level_approver(user)
    if not announcement.church_id:
        return False
    return can_approve_for_church(user, announcement.church, "approve_announcements")


def can_edit_announcement(user, announcement):
    if announcement.is_archived or announcement.is_rejected:
        return False
    if not _same_denomination(user, announcement):
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
    if not _same_denomination(user, announcement):
        return False
    if not can_archive_announcements(user) and announcement.created_by_id != user.id:
        return False
    if can_approve_announcement(user, announcement):
        return True
    return (
        announcement.created_by_id == user.id
        and (can_archive_announcements(user) or can_create_announcements(user))
    )


def pending_for_user(user):
    """Pending announcements this user is allowed to review (excludes own submissions)."""
    qs = selectors.pending_announcements_base_qs()
    denom = get_user_denomination(user)
    if not denom:
        return qs.none()
    qs = qs.filter(denomination_id=denom.pk)
    if is_top_level_approver(user):
        return qs.exclude(created_by=user)
    scoped = pending_for_church_scope(
        user,
        qs,
        "approve_announcements",
        church_lookup="church",
        submitter_field="created_by",
    )
    return selectors.exclude_general_visibility(scoped)


def user_matches_announcement_audience(user, announcement) -> bool:
    """Server-side role/department audience check (empty targets = everyone in scope)."""
    roles = announcement.target_roles or []
    if roles and getattr(user, "role", None) not in roles:
        return False
    dept_ids = list(
        announcement.target_department_links.values_list("department_id", flat=True)
    )
    if not dept_ids:
        return True
    member = getattr(user, "member", None)
    if member is None:
        # Staff without a linked member: show only if they manage the church
        # (approvers/creators still see via other paths; published feed for staff
        # without member link sees department-targeted items only when linked).
        return False
    return member.department_id in dept_ids


def visible_announcements(user, *, include_scheduled=False):
    """
    Approved, non-archived, non-expired announcements for the user + audience.

    INV-ANN-02: view_all_churches / institution superadmin never receive an
    unfiltered queryset — always bound to the user's denomination.
    """
    qs = selectors.approved_announcements_base_qs()
    qs = selectors.apply_publish_at_filter(qs, include_scheduled=include_scheduled)
    qs = qs.prefetch_related("target_department_links")

    scoped = selectors.announcements_for_user_scope(qs, user)

    member = getattr(user, "member", None)
    member_dept_id = getattr(member, "department_id", None) if member else None
    has_dept_targets = scoped.filter(target_department_links__isnull=False).distinct()
    no_dept_targets = scoped.filter(target_department_links__isnull=True)
    if member_dept_id:
        matched_dept = has_dept_targets.filter(
            target_department_links__department_id=member_dept_id
        )
        scoped = (no_dept_targets | matched_dept).distinct()
    else:
        scoped = no_dept_targets.distinct()

    # Role audience: JSON `contains` is Postgres-only — evaluate portably.
    role = getattr(user, "role", None)
    matched_ids = []
    for ann_id, target_roles in scoped.values_list("pk", "target_roles"):
        roles = target_roles or []
        if not roles or (role and role in roles):
            matched_ids.append(ann_id)
    return scoped.filter(pk__in=matched_ids)


def _assert_pin_limit(church, *, denomination=None, excluding_pk=None):
    if not church:
        qs = selectors.pinned_general_approved_qs(
            denomination=denomination, excluding_pk=excluding_pk
        )
    else:
        qs = selectors.pinned_church_approved_qs(church, excluding_pk=excluding_pk)
    if qs.count() >= MAX_PINNED_PER_CHURCH:
        raise AnnouncementServiceError(
            f"At most {MAX_PINNED_PER_CHURCH} pinned announcements are allowed. "
            "Unpin another announcement first."
        )


def _resolve_create_denomination(user, *, visibility, church):
    if visibility == "general":
        denom = get_user_denomination(user)
        if not denom:
            raise AnnouncementServiceError(
                "Denomination is required for general announcements."
            )
        return denom
    denom = get_church_denomination(church)
    if not denom:
        raise AnnouncementServiceError(
            "Church has no denomination; cannot create announcements."
        )
    user_denom = get_user_denomination(user)
    if user_denom and user_denom.pk != denom.pk:
        raise AnnouncementServiceError(
            "Cannot create announcements outside your denomination."
        )
    return denom


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
    target_roles=None,
    target_departments=None,
):
    """
    Create an announcement.

    Maker-checker: submissions stay PENDING by default. Pass auto_approve=True
    only for explicit publish-on-create (e.g. admin tooling); leadership should
    normally approve via the pending queue (own submissions are excluded).
    """
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
                "Only top-level leadership can create general (denomination-wide) announcements."
            )
    else:
        if not church:
            from church_system.church_scope import get_user_church

            church = get_user_church(user)
        if not church:
            raise AnnouncementServiceError("Church is required for church-scoped announcements.")
        manageable = get_manageable_churches(user)
        if not selectors.manageable_church_exists(manageable, church.pk):
            raise AnnouncementServiceError("You cannot post announcements for that church.")

    denomination = _resolve_create_denomination(user, visibility=visibility, church=church)

    # SoD: default is pending — do not auto-approve the creator's own submission.
    if auto_approve is None:
        auto_approve = False
    elif auto_approve:
        if visibility == "general":
            auto_approve = is_top_level_approver(user) and can_approve_announcements(user)
        elif church:
            auto_approve = can_approve_for_church(user, church, "approve_announcements")
        else:
            auto_approve = False

    roles = list(target_roles or [])
    departments = list(target_departments or [])

    if is_pinned and auto_approve:
        _assert_pin_limit(church, denomination=denomination)

    with db_transaction.atomic():
        fields = dict(
            title=title,
            content=content,
            visibility=visibility,
            church=church,
            denomination=denomination,
            event_date=event_date,
            publish_at=publish_at,
            auto_expire=bool(auto_expire),
            is_pinned=bool(is_pinned) and auto_approve,
            created_by=user,
            is_approved=False,
            is_rejected=False,
            is_archived=False,
            status=Announcement.STATUS_PENDING,
            target_roles=roles,
        )
        if auto_approve:
            fields.update(
                is_approved=True,
                approved_by=user,
                approved_at=timezone.now(),
                status=Announcement.STATUS_APPROVED,
            )
        ann = repo.create_announcement_instance(**fields)
        if departments:
            repo.set_announcement_departments(ann, departments)
        _log_audit(
            ann,
            "CREATE",
            user,
            details={
                "title": ann.title,
                "visibility": ann.visibility,
                "auto_approved": auto_approve,
                "church_id": str(ann.church_id) if ann.church_id else None,
                "denomination_id": str(ann.denomination_id) if ann.denomination_id else None,
                "target_roles": roles,
                "target_department_ids": [str(d.pk) for d in departments],
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
    target_roles=None,
    target_departments=None,
):
    if not can_edit_announcement(user, announcement):
        raise PermissionError("You cannot edit this announcement.")

    before = {
        "title": announcement.title,
        "visibility": announcement.visibility,
        "is_pinned": announcement.is_pinned,
        "is_approved": announcement.is_approved,
        "denomination_id": announcement.denomination_id,
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
            if not selectors.manageable_church_exists(manageable, church.pk):
                raise AnnouncementServiceError("Invalid church for this announcement.")
            announcement.church = church

    # Re-resolve denomination from authoritative sources (never from creator).
    if announcement.visibility == "general":
        announcement.church = None
        if not is_top_level_approver(user):
            raise AnnouncementServiceError(
                "Only top-level leadership can set general (denomination-wide) visibility."
            )
        denom = get_user_denomination(user)
        if not denom:
            raise AnnouncementServiceError(
                "Denomination is required for general announcements."
            )
        if (
            announcement.denomination_id
            and announcement.denomination_id != denom.pk
        ):
            raise AnnouncementServiceError(
                "Cannot move an announcement to another denomination."
            )
        announcement.denomination = denom
    else:
        if not announcement.church_id:
            raise AnnouncementServiceError(
                "Church is required for church-scoped announcements."
            )
        church_denom = get_church_denomination(announcement.church)
        if not church_denom:
            raise AnnouncementServiceError(
                "Church has no denomination; cannot update announcement."
            )
        if (
            announcement.denomination_id
            and announcement.denomination_id != church_denom.pk
        ):
            raise AnnouncementServiceError(
                "Cannot move an announcement to another denomination."
            )
        announcement.denomination = church_denom

    if event_date is not None:
        announcement.event_date = event_date
    if publish_at is not None:
        announcement.publish_at = publish_at
    if auto_expire is not None:
        announcement.auto_expire = bool(auto_expire)
    if target_roles is not None:
        announcement.target_roles = list(target_roles)

    if is_pinned is not None and editor_is_approver:
        if is_pinned and not announcement.is_pinned:
            _assert_pin_limit(
                announcement.church,
                denomination=announcement.denomination,
                excluding_pk=announcement.pk,
            )
        announcement.is_pinned = bool(is_pinned)

    if was_approved and require_reapproval and not editor_is_approver:
        announcement.is_approved = False
        announcement.approved_by = None
        announcement.approved_at = None
        announcement.status = Announcement.STATUS_PENDING

    if not announcement.title or not announcement.content:
        raise AnnouncementServiceError("Title and content are required.")

    with db_transaction.atomic():
        announcement.full_clean()
        repo.save_announcement(announcement)
        if target_departments is not None:
            repo.set_announcement_departments(announcement, list(target_departments))
        _log_audit(
            announcement,
            "UPDATE",
            user,
            details={"before": before, "after": {
                "title": announcement.title,
                "visibility": announcement.visibility,
                "is_pinned": announcement.is_pinned,
                "is_approved": announcement.is_approved,
                "denomination_id": announcement.denomination_id,
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
        _assert_pin_limit(
            announcement.church,
            denomination=announcement.denomination,
            excluding_pk=announcement.pk,
        )

    with db_transaction.atomic():
        announcement.is_approved = True
        announcement.is_rejected = False
        announcement.rejected_by = None
        announcement.rejected_at = None
        announcement.rejection_reason = ""
        announcement.approved_by = user
        announcement.approved_at = timezone.now()
        announcement.status = Announcement.STATUS_APPROVED
        repo.save_announcement(announcement)
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
        repo.save_announcement(announcement)
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
        repo.save_announcement(announcement)
        _log_audit(announcement, "ARCHIVE", user, details={"title": announcement.title})
    return announcement


def get_announcement_list_queryset(user, *, q="", church=None, pinned_only=False):
    qs = selectors.announcement_list_annotated(visible_announcements(user))
    return selectors.filter_announcement_list(
        qs, q=q, church=church, pinned_only=pinned_only
    )


def get_my_announcements_queryset(user, status=""):
    return selectors.my_announcements_qs(user, status=status)


def paginate_queryset(queryset, page=1, per_page=20):
    return Paginator(queryset, per_page).get_page(page)


def export_announcements_table(queryset):
    headers = [
        "Title", "Status", "Visibility", "Church", "Pinned", "Created",
        "Approved At", "Views", "Event Date",
    ]
    rows = []
    for a in selectors.announcement_with_church_for_export(queryset):
        view_count = getattr(a, "view_count", None)
        if view_count is None:
            view_count = selectors.announcement_view_count(a)
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
    return repo.get_or_create_announcement_view(user=user, announcement=announcement)


def view_counts_for(announcement_ids):
    return selectors.view_counts_by_announcement_ids(announcement_ids)
