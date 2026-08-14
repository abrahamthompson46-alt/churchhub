"""Object- and tenant-scoped authorization for private MEDIA files.

INV-MED-01 / INV-MED-02 / INV-DENY-01: authentication is not authorization.
Deny by default. Unknown prefixes and missing denomination/church fail closed.
"""

from __future__ import annotations

from church_system.denomination_scope import get_church_denomination, get_user_denomination
from church_system.media_access import is_public_media_path, normalize_media_relative_path


def user_may_access_media(user, relative_path: str) -> bool:
    """Return True only when *user* may fetch this MEDIA_ROOT-relative file.

    Public branding is handled by the view before this is called. This function
    never treats ``is_authenticated`` as sufficient.
    """
    path = normalize_media_relative_path(relative_path)
    if not path:
        return False
    if is_public_media_path(path):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_platform_user", False):
        return False
    if not get_user_denomination(user):
        return False

    handler = _handler_for_path(path)
    if handler is None:
        return False
    return bool(handler(user, path))


def _handler_for_path(path: str):
    for prefix, handler in _PREFIX_HANDLERS:
        if path.startswith(prefix):
            return handler
    return None


def _church_in_scope(user, church) -> bool:
    if not church:
        return False
    user_denom = get_user_denomination(user)
    if not user_denom:
        return False
    church_denom = get_church_denomination(church)
    if not church_denom or church_denom.pk != user_denom.pk:
        return False
    from permissions.scoping import get_manageable_churches

    return get_manageable_churches(user).filter(pk=church.pk).exists()


def _portal_member(user):
    return getattr(user, "member", None)


def _is_portal_member_role(user) -> bool:
    from permissions.roles import UserRole

    return getattr(user, "role", None) == UserRole.MEMBER


def _members_photo(user, path: str) -> bool:
    from members.models import Member
    from permissions.checks import can_view_members

    for member in Member.objects.filter(profile_picture=path).select_related("church"):
        portal = _portal_member(user)
        if portal is not None and portal.pk == member.pk:
            user_denom = get_user_denomination(user)
            church_denom = get_church_denomination(member.church)
            return bool(
                user_denom and church_denom and user_denom.pk == church_denom.pk
            )
        # INV-MED-01: portal MEMBER may fetch own photo only, even if view_members is granted.
        if _is_portal_member_role(user):
            continue
        if can_view_members(user) and _church_in_scope(user, member.church):
            return True
    return False


def _record_image(user, path: str) -> bool:
    from members.models import Record
    from permissions.checks import can_view_member_records

    qs = Record.objects.filter(images__image=path).select_related("church", "member")
    portal = _portal_member(user)
    for record in qs:
        if portal is not None and record.member_id == portal.pk and _church_in_scope(
            user, record.church
        ):
            return True
        if _is_portal_member_role(user):
            continue
        if can_view_member_records(user) and _church_in_scope(user, record.church):
            return True
    return False


def _history_image(user, path: str) -> bool:
    from members.models import History
    from permissions.checks import can_view_member_records

    qs = History.objects.filter(images__image=path).select_related("church", "member")
    portal = _portal_member(user)
    for history in qs:
        if portal is not None and history.member_id == portal.pk and _church_in_scope(
            user, history.church
        ):
            return True
        if _is_portal_member_role(user):
            continue
        if can_view_member_records(user) and _church_in_scope(user, history.church):
            return True
    return False


def _meeting_attachment(user, path: str) -> bool:
    from meetings.models import MeetingAttachment
    from permissions.checks import can_view_meetings

    qs = MeetingAttachment.objects.filter(file=path).select_related("meeting__church")
    portal = _portal_member(user)
    for attachment in qs:
        meeting = attachment.meeting
        church = meeting.church
        if not _church_in_scope(user, church):
            continue
        if can_view_meetings(user) and not _is_portal_member_role(user):
            return True
        if (
            portal is not None
            and portal.church_id == church.pk
            and meeting.show_on_portal
        ):
            return True
    return False


def _welfare_attachment(user, path: str) -> bool:
    from permissions.checks import can_view_welfare
    from remittance.models import WelfareCaseAttachment

    qs = WelfareCaseAttachment.objects.filter(file=path).select_related(
        "case__church", "case__member"
    )
    portal = _portal_member(user)
    for attachment in qs:
        case = attachment.case
        if portal is not None and case.member_id == portal.pk and _church_in_scope(
            user, case.church
        ):
            return True
        if _is_portal_member_role(user):
            continue
        if can_view_welfare(user) and _church_in_scope(user, case.church):
            return True
    return False


def _announcement_image(user, path: str) -> bool:
    from announcements.models import AnnouncementImage
    from announcements.services import (
        can_approve_announcement,
        user_matches_announcement_audience,
    )
    from permissions.checks import can_view_announcements

    qs = AnnouncementImage.objects.filter(image=path).select_related(
        "announcement__church", "announcement__created_by"
    )
    for image in qs:
        announcement = image.announcement
        if announcement.created_by_id == user.pk:
            if announcement.church_id:
                return _church_in_scope(user, announcement.church)
            creator_denom = get_user_denomination(announcement.created_by)
            user_denom = get_user_denomination(user)
            return bool(
                user_denom and creator_denom and user_denom.pk == creator_denom.pk
            )
        if can_approve_announcement(user, announcement):
            return True
        if not can_view_announcements(user):
            continue
        if not announcement.is_approved or announcement.is_archived or announcement.is_rejected:
            continue
        if not user_matches_announcement_audience(user, announcement):
            continue
        if announcement.visibility == "church":
            if _church_in_scope(user, announcement.church):
                return True
            continue
        # general: denomination via creator until Announcement.denomination exists
        user_denom = get_user_denomination(user)
        creator_denom = (
            get_user_denomination(announcement.created_by)
            if announcement.created_by_id
            else None
        )
        if user_denom and creator_denom and user_denom.pk == creator_denom.pk:
            return True
    return False


def _export_file(user, path: str) -> bool:
    from reports.models import ReportExportJob

    return ReportExportJob.objects.filter(export_file=path, user=user).exists()


# Longest/most specific prefixes first. Anything else is deny (INV-DENY-01).
_PREFIX_HANDLERS = (
    ("members/profile_pictures/", _members_photo),
    ("meetings/attachments/", _meeting_attachment),
    ("welfare/cases/", _welfare_attachment),
    ("exports/reports/", _export_file),
    ("announcements/", _announcement_image),
    ("records/", _record_image),
    ("history/", _history_image),
)
