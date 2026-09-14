"""Clerk-assisted birthday flyers for the local church WhatsApp group."""

from __future__ import annotations

from calendar import monthrange
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from announcements import repositories as repo
from announcements import selectors
from announcements.calendar_services import _birthday_in_window
from announcements.flyer_composer import render_birthday_flyer_png
from announcements.models import BirthdayWishDispatch
from church_system.church_scope import require_church
from permissions.checks import can_view_announcements, can_view_members
from permissions.org_scope import church_in_user_scope
from permissions.roles import UserRole

WINDOWS = ("today", "week", "month")


class BirthdayFlyerError(Exception):
    pass


def can_use_birthday_desk(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) == UserRole.MEMBER:
        return False
    return bool(can_view_announcements(user) and can_view_members(user))


def birthday_caption(*, member, church) -> str:
    name = (member.full_name or "").strip() or "our member"
    church_name = (church.name or "our church").strip()
    first = (member.first_name or name.split()[0]).strip()
    return (
        f"Happy Birthday to {name}! 🎉\n\n"
        f"The {church_name} family celebrates you today. "
        f"May God bless you abundantly.\n\n"
        f"Join us in wishing {first} a joyful birthday.\n\n"
        f"— {church_name}"
    )


def _window_bounds(today, window: str):
    if window not in WINDOWS:
        window = "today"
    if window == "today":
        return today, today
    if window == "week":
        return today, today + timedelta(days=6)
    last = monthrange(today.year, today.month)[1]
    from datetime import date

    return date(today.year, today.month, 1), date(today.year, today.month, last)


def list_birthday_desk_rows(church, *, window="today", today=None):
    today = today or timezone.localdate()
    start, end = _window_bounds(today, window)
    members = selectors.active_members_with_dob_for_church(church)
    rows = []
    for member in members.iterator():
        occ = _birthday_in_window(member.date_of_birth, start, end)
        if not occ:
            continue
        dispatch = (
            BirthdayWishDispatch.objects.filter(
                church=church, member=member, occurrence_date=occ
            )
            .only("id", "status", "caption", "flyer")
            .first()
        )
        rows.append(
            {
                "member": member,
                "occurrence_date": occ,
                "dispatch": dispatch,
                "caption": (dispatch.caption if dispatch else birthday_caption(member=member, church=church)),
            }
        )
    rows.sort(key=lambda row: (row["occurrence_date"], row["member"].last_name, row["member"].first_name))
    return rows


def _assert_occurrence_matches(member, occurrence_date):
    occ = _birthday_in_window(member.date_of_birth, occurrence_date, occurrence_date)
    if occ != occurrence_date:
        raise BirthdayFlyerError("That date is not this member's birthday.")
    return occ


@transaction.atomic
def prepare_birthday_flyer(*, user, church, member, occurrence_date):
    if member.church_id != church.pk:
        raise BirthdayFlyerError("Member is not in the active church.")
    if not member.is_active or not member.date_of_birth:
        raise BirthdayFlyerError("Only active members with a date of birth can be featured.")
    occ = _assert_occurrence_matches(member, occurrence_date)
    png = render_birthday_flyer_png(member=member, church=church, occurrence_date=occ)
    caption = birthday_caption(member=member, church=church)
    dispatch, _created = BirthdayWishDispatch.objects.select_for_update().get_or_create(
        church=church,
        member=member,
        occurrence_date=occ,
        defaults={
            "caption": caption,
            "created_by": user,
            "status": BirthdayWishDispatch.STATUS_PREPARED,
        },
    )
    filename = f"{occ.isoformat()}_{member.pk}.png"
    dispatch.flyer.save(filename, ContentFile(png), save=False)
    dispatch.caption = caption
    if dispatch.status == BirthdayWishDispatch.STATUS_POSTED:
        dispatch.status = BirthdayWishDispatch.STATUS_PREPARED
        dispatch.posted_at = None
        dispatch.posted_by = None
    dispatch.created_by = dispatch.created_by or user
    dispatch.save()
    repo.create_audit_log(
        church=church,
        action="BIRTHDAY_PREP",
        performed_by=user,
        details={
            "member_id": str(member.pk),
            "occurrence_date": occ.isoformat(),
            "dispatch_id": str(dispatch.pk),
        },
    )
    return dispatch


def mark_birthday_downloaded(*, user, dispatch):
    if dispatch.status != BirthdayWishDispatch.STATUS_POSTED:
        dispatch.status = BirthdayWishDispatch.STATUS_DOWNLOADED
        dispatch.save(update_fields=["status", "updated_at"])
    repo.create_audit_log(
        church=dispatch.church,
        action="BIRTHDAY_GET",
        performed_by=user,
        details={"dispatch_id": str(dispatch.pk), "member_id": str(dispatch.member_id)},
    )
    return dispatch


def mark_birthday_posted(*, user, dispatch):
    dispatch.status = BirthdayWishDispatch.STATUS_POSTED
    dispatch.posted_by = user
    dispatch.posted_at = timezone.now()
    dispatch.save(update_fields=["status", "posted_by", "posted_at", "updated_at"])
    repo.create_audit_log(
        church=dispatch.church,
        action="BIRTHDAY_POST",
        performed_by=user,
        details={"dispatch_id": str(dispatch.pk), "member_id": str(dispatch.member_id)},
    )
    return dispatch


def require_birthday_church(request):
    church = require_church(request)
    if not church_in_user_scope(request.user, church):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("This church is outside your scope.")
    return church


def notify_church_birthday_desk(church, *, today=None) -> int:
    """In-app remind secretary and local pastor when someone has a birthday today."""
    from accounts.models import User
    from dashboard.services import notify_user

    today = today or timezone.localdate()
    rows = list_birthday_desk_rows(church, window="today", today=today)
    if not rows:
        return 0
    names = ", ".join(row["member"].full_name for row in rows[:8])
    extra = len(rows) - 8
    if extra > 0:
        names = f"{names} and {extra} more"
    action_url = reverse("announcements:birthday_desk")
    users = User.objects.filter(
        church=church,
        is_active=True,
        role__in=[UserRole.SECRETARY, UserRole.LOCAL_PASTOR],
    )
    sent = 0
    event_key = f"birthday.desk.{church.pk}.{today.isoformat()}"
    title = "Birthday flyer desk"
    message = (
        f"{len(rows)} birthday(s) today at {church.name}: {names}. "
        "Prepare the flyer and post it in the church WhatsApp group."
    )
    for user in users:
        if not can_use_birthday_desk(user):
            continue
        notify_user(
            user,
            title,
            message,
            category="MEMBER",
            action_url=action_url,
            severity="INFO",
            event_key=event_key,
        )
        sent += 1
    return sent


def remind_all_church_birthday_desks(*, today=None) -> dict:
    from organization.models import Church

    today = today or timezone.localdate()
    churches_notified = 0
    notifications = 0
    for church in Church.objects.select_related(
        "district__zone__conference__denomination"
    ).iterator():
        count = notify_church_birthday_desk(church, today=today)
        if count:
            churches_notified += 1
            notifications += count
    return {"churches": churches_notified, "notifications": notifications}
