"""Clerk-assisted birthday flyers for the local church WhatsApp group."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

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
CAPTION_MAX = 2000
DEFAULT_FLYER_RETENTION_DAYS = 90


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


def normalize_caption(text, *, member, church) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return birthday_caption(member=member, church=church)
    return cleaned[:CAPTION_MAX]


def _window_bounds(today, window: str):
    if window not in WINDOWS:
        window = "today"
    if window == "today":
        return today, today
    if window == "week":
        return today, today + timedelta(days=6)
    last = monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last)


def list_birthday_desk_rows(church, *, window="today", today=None):
    today = today or timezone.localdate()
    start, end = _window_bounds(today, window)
    members = list(selectors.active_members_with_dob_for_church(church))
    dispatch_map = {}
    if members:
        dispatch_map = {
            (row.member_id, row.occurrence_date): row
            for row in BirthdayWishDispatch.objects.filter(
                church=church,
                member_id__in=[m.pk for m in members],
                occurrence_date__gte=start,
                occurrence_date__lte=end,
            )
        }
    rows = []
    for member in members:
        occ = _birthday_in_window(member.date_of_birth, start, end)
        if not occ:
            continue
        dispatch = dispatch_map.get((member.pk, occ))
        rows.append(
            {
                "member": member,
                "occurrence_date": occ,
                "dispatch": dispatch,
                "caption": (
                    dispatch.caption
                    if dispatch and dispatch.caption
                    else birthday_caption(member=member, church=church)
                ),
            }
        )
    rows.sort(
        key=lambda row: (row["occurrence_date"], row["member"].last_name, row["member"].first_name)
    )
    return rows


def list_missing_birthday_photos(church, *, today=None):
    rows = list_birthday_desk_rows(church, window="month", today=today)
    return [row for row in rows if not row["member"].show_birthday_photo]


def church_missing_birthday_logo(church) -> bool:
    from church_system.denomination_scope import get_church_denomination

    denom = get_church_denomination(church)
    if not denom:
        return True
    return not bool(getattr(getattr(denom, "logo", None), "name", ""))


def _assert_occurrence_matches(member, occurrence_date):
    occ = _birthday_in_window(member.date_of_birth, occurrence_date, occurrence_date)
    if occ != occurrence_date:
        raise BirthdayFlyerError("That date is not this member's birthday.")
    return occ


@transaction.atomic
def prepare_birthday_flyer(*, user, church, member, occurrence_date, caption=None):
    if member.church_id != church.pk:
        raise BirthdayFlyerError("Member is not in the active church.")
    if getattr(member, "hide_public_birthday", False):
        raise BirthdayFlyerError("This member is on the quiet birthday list.")
    if not member.is_active or not member.date_of_birth:
        raise BirthdayFlyerError("Only active members with a date of birth can be featured.")
    occ = _assert_occurrence_matches(member, occurrence_date)
    png = render_birthday_flyer_png(member=member, church=church, occurrence_date=occ)
    caption_text = normalize_caption(caption, member=member, church=church)
    dispatch, _created = BirthdayWishDispatch.objects.select_for_update().get_or_create(
        church=church,
        member=member,
        occurrence_date=occ,
        defaults={
            "caption": caption_text,
            "created_by": user,
            "status": BirthdayWishDispatch.STATUS_PREPARED,
        },
    )
    filename = f"{occ.isoformat()}_{member.pk}.png"
    dispatch.flyer.save(filename, ContentFile(png), save=False)
    dispatch.caption = caption_text
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


def prepare_birthday_flyers_for_window(*, user, church, window="today", today=None):
    prepared = 0
    skipped = 0
    for row in list_birthday_desk_rows(church, window=window, today=today):
        try:
            prepare_birthday_flyer(
                user=user,
                church=church,
                member=row["member"],
                occurrence_date=row["occurrence_date"],
                caption=row["caption"],
            )
            prepared += 1
        except BirthdayFlyerError:
            skipped += 1
    return prepared, skipped


def save_birthday_caption(*, user, dispatch, caption):
    text = (caption or "").strip()
    if not text:
        raise BirthdayFlyerError("Caption cannot be empty.")
    dispatch.caption = text[:CAPTION_MAX]
    dispatch.save(update_fields=["caption", "updated_at"])
    repo.create_audit_log(
        church=dispatch.church,
        action="BIRTHDAY_CAP",
        performed_by=user,
        details={"dispatch_id": str(dispatch.pk), "member_id": str(dispatch.member_id)},
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


def purge_old_birthday_flyers(*, days=DEFAULT_FLYER_RETENTION_DAYS, now=None) -> int:
    days = max(1, int(days))
    cutoff = (now or timezone.now()) - timedelta(days=days)
    removed = 0
    qs = BirthdayWishDispatch.objects.exclude(flyer="").filter(updated_at__lt=cutoff)
    for dispatch in qs.iterator():
        dispatch.flyer.delete(save=False)
        dispatch.flyer = ""
        dispatch.save(update_fields=["flyer", "updated_at"])
        removed += 1
    return removed


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
    when_label = "today" if today == timezone.localdate() else today.strftime("%A, %b %d")
    message = (
        f"{len(rows)} birthday(s) {when_label} at {church.name}: {names}. "
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


def remind_all_church_birthday_desks(*, today=None, days_ahead=0) -> dict:
    from organization.models import Church

    today = today or timezone.localdate()
    days_ahead = max(0, int(days_ahead))
    dates = [today + timedelta(days=offset) for offset in range(days_ahead + 1)]
    churches_notified = 0
    notifications = 0
    for church in Church.objects.select_related(
        "district__zone__conference__denomination"
    ).iterator():
        church_sent = 0
        for occ in dates:
            church_sent += notify_church_birthday_desk(church, today=occ)
        if church_sent:
            churches_notified += 1
            notifications += church_sent
    return {"churches": churches_notified, "notifications": notifications}
