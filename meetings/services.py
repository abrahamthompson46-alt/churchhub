"""Meeting and attendance services."""

from django.db import transaction
from django.utils import timezone

from meetings import repositories as repo
from meetings import selectors

from .models import MeetingStatus


def mark_meeting_held(meeting, minutes="", ended_at=None):
    meeting.minutes = minutes or meeting.minutes
    meeting.status = MeetingStatus.HELD
    meeting.ended_at = ended_at or timezone.now()
    repo.save_meeting(
        meeting, update_fields=["minutes", "status", "ended_at", "updated_at"]
    )
    return meeting


def _sync_attendance_rows(*, existing_qs, member_ids, present_ids, create_row):
    """
    Update attendance in place instead of wiping the full roll.

    Removes rows for members no longer on the roll; upserts the rest so
    re-entry preserves row identity where possible.
    """
    member_ids = set(member_ids)
    present_ids = set(present_ids or member_ids)
    repo.delete_attendance_not_in(existing_qs, member_ids)
    for member_id in member_ids:
        create_row(member_id, member_id in present_ids)


def _sync_visitor_rows(*, existing_qs, visitor_ids, present_ids, create_row, delete_not_in):
    visitor_ids = set(visitor_ids or ())
    present_ids = set(present_ids or visitor_ids)
    delete_not_in(existing_qs, visitor_ids)
    for visitor_id in visitor_ids:
        create_row(visitor_id, visitor_id in present_ids)


@transaction.atomic
def record_meeting_attendance(
    meeting,
    member_ids,
    present_ids=None,
    *,
    visitor_ids=None,
    visitor_present_ids=None,
):
    """Bulk-set attendance for a meeting."""
    valid_ids = selectors.member_ids_in_church(meeting.church, member_ids)

    def _create(member_id, is_present):
        repo.upsert_meeting_attendance(
            meeting=meeting, member_id=member_id, is_present=is_present
        )

    _sync_attendance_rows(
        existing_qs=meeting.attendees.all(),
        member_ids=valid_ids,
        present_ids=present_ids,
        create_row=_create,
    )

    if visitor_ids is not None:
        valid_visitor_ids = selectors.visitor_ids_in_church(meeting.church, visitor_ids)

        def _create_visitor(visitor_id, is_present):
            repo.upsert_meeting_visitor_attendance(
                meeting=meeting, visitor_id=visitor_id, is_present=is_present
            )

        _sync_visitor_rows(
            existing_qs=meeting.visitor_attendees.all(),
            visitor_ids=valid_visitor_ids,
            present_ids=visitor_present_ids,
            create_row=_create_visitor,
            delete_not_in=repo.delete_meeting_visitor_not_in,
        )
    return selectors.meeting_attendance_count(meeting)


@transaction.atomic
def record_event_attendance(
    event,
    member_ids,
    present_ids=None,
    *,
    visitor_ids=None,
    extra_guests=None,
):
    """Bulk-set attendance for an attendance event."""
    valid_ids = selectors.member_ids_in_church(event.church, member_ids)

    def _create(member_id, is_present):
        repo.upsert_event_attendance(
            event=event, member_id=member_id, is_present=is_present
        )

    _sync_attendance_rows(
        existing_qs=event.records.all(),
        member_ids=valid_ids,
        present_ids=present_ids,
        create_row=_create,
    )

    if visitor_ids is not None:
        valid_visitor_ids = selectors.visitor_ids_in_church(event.church, visitor_ids)

        def _create_visitor(visitor_id, is_present):
            repo.upsert_event_visitor_attendance(
                event=event, visitor_id=visitor_id, is_present=is_present
            )

        _sync_visitor_rows(
            existing_qs=event.visitor_records.all(),
            visitor_ids=valid_visitor_ids,
            present_ids=valid_visitor_ids,
            create_row=_create_visitor,
            delete_not_in=repo.delete_event_visitor_not_in,
        )
        present_visitors = event.visitor_records.filter(is_present=True).count()
        walk_ins = max(int(extra_guests or 0), 0)
        event.headcount = present_visitors + walk_ins
        repo.save_attendance_event(event, update_fields=["headcount"])

    return selectors.event_attendance_count(event)
