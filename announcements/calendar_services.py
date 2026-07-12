"""Upcoming birthdays and church events for the Communications calendar."""

from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.utils import timezone

from church_system.church_scope import filter_by_church, get_active_church
from members.models import Member

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
    members = filter_by_church(
        Member.objects.filter(is_active=True, date_of_birth__isnull=False).select_related(
            "department", "church"
        ),
        request,
    )
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
    from meetings.models import Meeting, MeetingStatus

    church = get_active_church(request)
    if not church:
        return []
    now = timezone.now()
    end = now + timedelta(days=days)
    qs = Meeting.objects.filter(
        church=church,
        scheduled_at__gte=now,
        scheduled_at__lte=end,
        status=MeetingStatus.SCHEDULED,
    ).select_related("department").order_by("scheduled_at")
    items = []
    for meeting in qs[:limit]:
        subtitle = meeting.location or ""
        if meeting.department:
            subtitle = f"{meeting.department.name}" + (f" · {subtitle}" if subtitle else "")
        items.append(
            _calendar_item(
                kind="meeting",
                when=meeting.scheduled_at,
                title=meeting.title,
                subtitle=subtitle,
                url_name="meetings:detail",
                url_kwargs={"pk": meeting.pk},
                meta={"location": meeting.location},
            )
        )
    return items


def get_upcoming_announcement_events(request, days=60, limit=50):
    now = timezone.now()
    end = now + timedelta(days=days)
    qs = (
        visible_announcements(request.user)
        .filter(event_date__isnull=False, event_date__gte=now, event_date__lte=end)
        .select_related("church")
        .order_by("event_date")
    )
    items = []
    for announcement in qs[:limit]:
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
    today = timezone.now().date()
    return {
        "birthdays": len(birthdays),
        "meetings": len(meetings),
        "events": len(events),
        "today_birthdays": sum(1 for row in birthdays if row["date"] == today),
        "total": len(birthdays) + len(meetings) + len(events),
    }
