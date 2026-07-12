"""Meeting and attendance services."""

from django.db import transaction
from django.utils import timezone

from members.models import Member

from .models import AttendanceRecord, Meeting, MeetingAttendance, MeetingStatus


def mark_meeting_held(meeting, minutes="", ended_at=None):
    meeting.minutes = minutes or meeting.minutes
    meeting.status = MeetingStatus.HELD
    meeting.ended_at = ended_at or timezone.now()
    meeting.save(update_fields=["minutes", "status", "ended_at", "updated_at"])
    return meeting


@transaction.atomic
def record_meeting_attendance(meeting, member_ids, present_ids=None):
    """Bulk-set attendance for a meeting."""
    present_ids = set(present_ids or member_ids)
    meeting.attendees.all().delete()
    members = Member.objects.filter(pk__in=member_ids, church=meeting.church)
    for member in members:
        MeetingAttendance.objects.create(
            meeting=meeting,
            member=member,
            is_present=member.pk in present_ids,
        )
    return meeting.attendees.count()


@transaction.atomic
def record_event_attendance(event, member_ids, present_ids=None):
    """Bulk-set attendance for an attendance event."""
    present_ids = set(present_ids or member_ids)
    event.records.all().delete()
    members = Member.objects.filter(pk__in=member_ids, church=event.church)
    for member in members:
        AttendanceRecord.objects.create(
            event=event,
            member=member,
            is_present=member.pk in present_ids,
        )
    return event.records.count()
