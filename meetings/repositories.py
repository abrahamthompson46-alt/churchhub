"""
Persistence helpers for the meetings domain.

Services and workflow own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from .models import AttendanceRecord, MeetingAttendance


def save_meeting(meeting, *, update_fields=None):
    if update_fields is not None:
        meeting.save(update_fields=update_fields)
    else:
        meeting.save()
    return meeting


def save_meeting_attachment(attachment, *, update_fields=None):
    if update_fields is not None:
        attachment.save(update_fields=update_fields)
    else:
        attachment.save()
    return attachment


def delete_meeting_attachment(attachment):
    attachment.file.delete(save=False)
    attachment.delete()


def save_action_item(item, *, update_fields=None):
    if update_fields is not None:
        item.save(update_fields=update_fields)
    else:
        item.save()
    return item


def save_decision(decision, *, update_fields=None):
    if update_fields is not None:
        decision.save(update_fields=update_fields)
    else:
        decision.save()
    return decision


def save_attendance_event(event, *, update_fields=None):
    if update_fields is not None:
        event.save(update_fields=update_fields)
    else:
        event.save()
    return event


def delete_attendance_not_in(existing_qs, member_ids):
    return existing_qs.exclude(member_id__in=member_ids).delete()


def upsert_meeting_attendance(*, meeting, member_id, is_present):
    return MeetingAttendance.objects.update_or_create(
        meeting=meeting,
        member_id=member_id,
        defaults={"is_present": is_present},
    )


def upsert_event_attendance(*, event, member_id, is_present):
    return AttendanceRecord.objects.update_or_create(
        event=event,
        member_id=member_id,
        defaults={"is_present": is_present},
    )
