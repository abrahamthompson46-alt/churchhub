"""Meeting minutes workflow — maker-checker approval."""

from django.utils import timezone

from meetings import repositories as repo
from meetings import selectors
from permissions.checks import can_manage_meetings, can_view_meetings
from permissions.scoping_checks import can_approve_for_church, pending_for_church_scope

from .models import MeetingStatus, MinutesStatus


class MeetingWorkflowError(Exception):
    pass


def can_view_meetings_user(user):
    return can_view_meetings(user) or can_manage_meetings(user)


def can_edit_meeting_metadata(user, meeting):
    if not can_manage_meetings(user):
        return False
    return meeting.minutes_status != MinutesStatus.APPROVED


def can_edit_minutes(user, meeting):
    if not can_manage_meetings(user):
        return False
    return meeting.minutes_editable


def can_submit_minutes(user, meeting):
    if not can_edit_minutes(user, meeting):
        return False
    return meeting.minutes_status in {MinutesStatus.DRAFT, MinutesStatus.REJECTED}


def can_approve_meeting_minutes(user, meeting):
    if meeting.minutes_status != MinutesStatus.PENDING_APPROVAL:
        return False
    if meeting.minutes_submitted_by_id and meeting.minutes_submitted_by_id == user.pk:
        return False
    return can_approve_for_church(user, meeting.church, "approve_minutes")


def pending_minutes_for_user(user):
    qs = selectors.pending_minutes_base_qs()
    return pending_for_church_scope(
        user,
        qs,
        "approve_minutes",
        church_lookup="church",
        submitter_field="minutes_submitted_by",
    ).order_by("minutes_submitted_at")


def save_minutes_draft(meeting, data, user):
    if not can_edit_minutes(user, meeting):
        raise MeetingWorkflowError("You cannot edit minutes for this meeting.")
    section_fields = [
        "minutes_opening",
        "minutes_previous",
        "minutes_deliberations",
        "minutes_motions",
        "minutes_votes",
        "minutes_adjournment",
        "minutes",
    ]
    update_fields = ["updated_at"]
    for field in section_fields:
        if field in data:
            setattr(meeting, field, data[field])
            update_fields.append(field)
    for field in ("status", "ended_at", "chair_person", "secretary_name"):
        if field in data:
            setattr(meeting, field, data[field])
            update_fields.append(field)
    if meeting.status == MeetingStatus.HELD and not meeting.ended_at:
        meeting.ended_at = timezone.now()
        update_fields.append("ended_at")
    if meeting.minutes_status == MinutesStatus.REJECTED:
        meeting.minutes_status = MinutesStatus.DRAFT
        meeting.minutes_rejection_reason = ""
        update_fields.extend(["minutes_status", "minutes_rejection_reason"])
    repo.save_meeting(meeting, update_fields=list(dict.fromkeys(update_fields)))
    return meeting


def submit_minutes_for_approval(meeting, user):
    if not can_submit_minutes(user, meeting):
        raise MeetingWorkflowError("You cannot submit these minutes for approval.")
    if meeting.status != MeetingStatus.HELD:
        raise MeetingWorkflowError("Mark the meeting as Held before submitting minutes.")
    if not any([
        meeting.minutes_opening,
        meeting.minutes_deliberations,
        meeting.minutes_motions,
        meeting.minutes,
    ]):
        raise MeetingWorkflowError("Add minutes content before submitting for approval.")
    meeting.minutes_status = MinutesStatus.PENDING_APPROVAL
    meeting.minutes_submitted_by = user
    meeting.minutes_submitted_at = timezone.now()
    meeting.minutes_rejection_reason = ""
    repo.save_meeting(
        meeting,
        update_fields=[
            "minutes_status",
            "minutes_submitted_by",
            "minutes_submitted_at",
            "minutes_rejection_reason",
            "updated_at",
        ],
    )
    return meeting


def approve_minutes(meeting, user):
    if not can_approve_meeting_minutes(user, meeting):
        raise MeetingWorkflowError("You cannot approve these minutes.")
    meeting.minutes_status = MinutesStatus.APPROVED
    meeting.minutes_locked = True
    meeting.minutes_approved_by = user
    meeting.minutes_approved_at = timezone.now()
    meeting.minutes_rejection_reason = ""
    repo.save_meeting(
        meeting,
        update_fields=[
            "minutes_status",
            "minutes_locked",
            "minutes_approved_by",
            "minutes_approved_at",
            "minutes_rejection_reason",
            "updated_at",
        ],
    )
    return meeting


def reject_minutes(meeting, user, reason=""):
    if not can_approve_meeting_minutes(user, meeting):
        raise MeetingWorkflowError("You cannot reject these minutes.")
    meeting.minutes_status = MinutesStatus.REJECTED
    meeting.minutes_locked = False
    meeting.minutes_rejection_reason = reason.strip()
    meeting.minutes_approved_by = None
    meeting.minutes_approved_at = None
    repo.save_meeting(
        meeting,
        update_fields=[
            "minutes_status",
            "minutes_locked",
            "minutes_rejection_reason",
            "minutes_approved_by",
            "minutes_approved_at",
            "updated_at",
        ],
    )
    return meeting
