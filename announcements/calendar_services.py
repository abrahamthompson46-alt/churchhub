"""Upcoming birthdays and church events for the Communications calendar."""

from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.utils import timezone

from announcements import selectors
from church_system.church_scope import get_active_church

from .services import visible_announcements


def _occurrence_in_year(dob, year):
    try:
        return date(year, dob.month, dob.day)
    except ValueError:
        return date(year, 2, 28)


def _birthday_in_window(dob, start, end):
    years = {start.year, end.year}
    if end.year - start.year > 1:
        years.update(range(start.year, end.year + 1))
    for year in sorted(years):
        occ = _occurrence_in_year(dob, year)
        if start <= occ <= end:
            return occ
    return None


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _calendar_item(
    *,
    kind,
    when,
    title,
    subtitle="",
    url_name="",
    url_kwargs=None,
    member=None,
    turning_age=None,
    meta=None,
):
    return {
        "kind": kind,
        "date": when,
        "sort_key": when,
        "title": title,
        "subtitle": subtitle,
        "url_name": url_name,
        "url_kwargs": url_kwargs or {},
        "member": member,
        "turning_age": turning_age,
        "meta": meta or {},
    }


def get_upcoming_birthdays(request, days=60, limit=100):
    today = timezone.now().date()
    end = today + timedelta(days=days)
    members = selectors.active_members_with_dob_for_request(request)
    items = []
    for member in members.iterator():
        occ = _birthday_in_window(member.date_of_birth, today, end)
        if not occ:
            continue
        turning_age = occ.year - member.date_of_birth.year
        subtitle_parts = []
        if member.department:
            subtitle_parts.append(member.department.name)
        if turning_age:
            subtitle_parts.append(f"Turning {turning_age}")
        items.append(
            _calendar_item(
                kind="birthday",
                when=occ,
                title=member.full_name,
                subtitle=" · ".join(subtitle_parts),
                url_name="members:detail",
                url_kwargs={"member_id": member.pk},
                member=member,
                turning_age=turning_age,
            )
        )
    items.sort(key=lambda row: (row["date"], row["title"]))
    return items[:limit]


def get_upcoming_meetings(request, days=60, limit=50):
    church = get_active_church(request)
    if not church:
        return []
    now = timezone.now()
    end = now + timedelta(days=days)
    from permissions.checks import can_view_meetings

    portal_visible_only = not can_view_meetings(request.user)
    qs = selectors.scheduled_meetings_for_church_in_window(
        church,
        start=now,
        end=end,
        limit=limit,
        portal_visible_only=portal_visible_only,
    )
    items = []
    for meeting in qs:
        subtitle = meeting.location or ""
        if meeting.department:
            subtitle = f"{meeting.department.name}" + (f" · {subtitle}" if subtitle else "")
        if meeting.join_url:
            subtitle = (subtitle + " · Online").strip(" ·") if subtitle else "Online"
        use_portal = portal_visible_only or (
            meeting.show_on_portal and getattr(request.user, "role", "") == "MEMBER"
        )
        items.append(
            _calendar_item(
                kind="meeting",
                when=meeting.scheduled_at,
                title=meeting.title,
                subtitle=subtitle,
                url_name="portal:meeting_live" if use_portal else "meetings:detail",
                url_kwargs={"pk": meeting.pk},
                meta={
                    "location": meeting.location,
                    "join_url": meeting.join_url or "",
                    "show_on_portal": meeting.show_on_portal,
                },
            )
        )
    return items


def get_upcoming_announcement_events(request, days=60, limit=50):
    now = timezone.now()
    end = now + timedelta(days=days)
    qs = selectors.announcement_events_in_window(
        visible_announcements(request.user),
        start=now,
        end=end,
        limit=limit,
    )
    items = []
    for announcement in qs:
        subtitle = announcement.church.name if announcement.church else "General"
        items.append(
            _calendar_item(
                kind="announcement",
                when=announcement.event_date,
                title=announcement.title,
                subtitle=subtitle,
                url_name="announcements:announcement_detail",
                url_kwargs={"pk": announcement.pk},
            )
        )
    return items


def get_communications_calendar(request, days=60, category="all", limit=200):
    """Merged upcoming items sorted chronologically."""
    category = (category or "all").lower()
    items = []
    if category in ("all", "birthdays", "birthday"):
        items.extend(get_upcoming_birthdays(request, days=days, limit=limit))
    if category in ("all", "meetings", "meeting"):
        items.extend(get_upcoming_meetings(request, days=days, limit=limit))
    if category in ("all", "events", "announcements", "announcement"):
        items.extend(get_upcoming_announcement_events(request, days=days, limit=limit))

    items.sort(key=lambda row: (row["sort_key"], row["kind"], row["title"]))
    return items[:limit]


def group_calendar_by_date(items):
    groups = OrderedDict()
    for item in items:
        day = _as_date(item["date"])
        groups.setdefault(day, []).append(item)
    return groups


def attach_calendar_urls(items):
    from django.urls import NoReverseMatch, reverse

    for item in items:
        item["url"] = ""
        if item.get("url_name"):
            try:
                item["url"] = reverse(item["url_name"], kwargs=item.get("url_kwargs") or {})
            except NoReverseMatch:
                item["url"] = ""
    return items


def calendar_summary_counts(request, days=60):
    birthdays = get_upcoming_birthdays(request, days=days, limit=500)
    meetings = get_upcoming_meetings(request, days=days, limit=500)
    events = get_upcoming_announcement_events(request, days=days, limit=500)
    return calendar_summary_counts_from_items(
        [{"kind": "birthday", "date": r["date"]} for r in birthdays]
        + [{"kind": "meeting", "date": r["date"]} for r in meetings]
        + [{"kind": "event", "date": r["date"]} for r in events]
    )


def calendar_summary_counts_from_items(items):
    """Derive summary counts from already-fetched calendar items (no extra queries)."""
    today = timezone.now().date()
    birthdays = [row for row in items if row.get("kind") == "birthday"]
    meetings = [row for row in items if row.get("kind") == "meeting"]
    events = [row for row in items if row.get("kind") in ("event", "announcement")]
    return {
        "birthdays": len(birthdays),
        "meetings": len(meetings),
        "events": len(events),
        "today_birthdays": sum(1 for row in birthdays if row.get("date") == today),
        "total": len(birthdays) + len(meetings) + len(events),
    }
