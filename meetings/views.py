from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from church_system.church_scope import require_church
from church_system.flash import flash_exception, flash_info, flash_success
from meetings import repositories as repo
from meetings import selectors
from permissions.checks import (
    any_permission_required,
    can_manage_meetings,
    permission_required,
)
from sitecontrol.checks import require_feature

from .forms import (
    ActionItemForm,
    AttendanceEventForm,
    DecisionForm,
    MeetingAttachmentForm,
    MeetingFilterForm,
    MeetingForm,
    MeetingMinutesForm,
    MinutesRejectForm,
)
from .services import record_event_attendance, record_meeting_attendance
from .workflow import (
    MeetingWorkflowError,
    approve_minutes,
    can_approve_meeting_minutes,
    can_edit_meeting_metadata,
    can_edit_minutes,
    can_submit_minutes,
    can_view_meetings_user,
    pending_minutes_for_user,
    reject_minutes,
    save_minutes_draft,
    submit_minutes_for_approval,
)


def _filter_meetings(request, qs):
    form = MeetingFilterForm(request.GET or None)
    if form.is_valid():
        qs = selectors.filter_meetings_queryset(qs, form.cleaned_data)
    return qs, form


@login_required
@require_feature("meetings")
@any_permission_required("view_meetings", "manage_meetings")
def meeting_list(request):
    meetings, filter_form = _filter_meetings(request, selectors.meetings_for_request(request))
    meetings = selectors.meetings_list_limited(meetings, limit=200)
    return render(request, "meetings/list.html", {
        "meetings": meetings,
        "filter_form": filter_form,
        "pending_count": pending_minutes_for_user(request.user).count(),
        "can_manage_meetings": can_manage_meetings(request.user),
        "breadcrumbs": [{"label": "Meetings"}],
    })


@login_required
@require_feature("meetings")
@permission_required("approve_minutes")
def pending_minutes(request):
    meetings = pending_minutes_for_user(request.user)
    return render(request, "meetings/pending.html", {
        "meetings": meetings,
        "breadcrumbs": [
            {"label": "Meetings", "url": "/meetings/"},
            {"label": "Pending Minutes"},
        ],
    })


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def meeting_create(request):
    church = require_church(request)
    if request.method == "POST":
        form = MeetingForm(request.POST, church=church)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.church = church
            meeting.created_by = request.user
            repo.save_meeting(meeting)
            flash_success(request, "Meeting scheduled.")
            return redirect("meetings:detail", pk=meeting.pk)
    else:
        form = MeetingForm(church=church)
    return render(request, "meetings/form.html", {
        "form": form,
        "title": "Schedule Meeting",
        "breadcrumbs": [{"label": "Meetings", "url": "/meetings/"}, {"label": "Schedule"}],
    })


def _meeting_context(request, meeting):
    members = selectors.active_members_for_church(meeting.church)
    attendee_ids = selectors.meeting_attendee_member_ids(meeting)
    present_ids = selectors.meeting_present_member_ids(meeting)
    return {
        "meeting": meeting,
        "members": members,
        "attendee_ids": attendee_ids,
        "present_ids": present_ids,
        "action_form": ActionItemForm(church=meeting.church),
        "decision_form": DecisionForm(),
        "minutes_form": MeetingMinutesForm(instance=meeting),
        "attachment_form": MeetingAttachmentForm(),
        "reject_form": MinutesRejectForm(),
        "can_edit_metadata": can_edit_meeting_metadata(request.user, meeting),
        "can_edit_minutes": can_edit_minutes(request.user, meeting),
        "can_submit_minutes": can_submit_minutes(request.user, meeting),
        "can_approve_minutes": can_approve_meeting_minutes(request.user, meeting),
        "can_manage_meetings": can_manage_meetings(request.user),
    }


@login_required
@require_feature("meetings")
@any_permission_required("view_meetings", "manage_meetings")
def meeting_detail(request, pk):
    if not can_view_meetings_user(request.user):
        raise PermissionDenied
    meeting = selectors.get_meeting_or_404(request, pk, detail=True)
    return render(request, "meetings/detail.html", {
        **_meeting_context(request, meeting),
        "breadcrumbs": [
            {"label": "Meetings", "url": "/meetings/"},
            {"label": meeting.title},
        ],
    })


@login_required
@require_feature("meetings")
@any_permission_required("view_meetings", "manage_meetings")
def meeting_edit(request, pk):
    meeting = selectors.get_meeting_or_404(request, pk)
    if not can_edit_meeting_metadata(request.user, meeting):
        raise PermissionDenied
    if request.method == "POST":
        form = MeetingForm(request.POST, instance=meeting, church=meeting.church)
        if form.is_valid():
            meeting = form.save(commit=False)
            repo.save_meeting(meeting)
            flash_success(request, "Meeting updated.")
            return redirect("meetings:detail", pk=meeting.pk)
    else:
        form = MeetingForm(instance=meeting, church=meeting.church)
    return render(request, "meetings/form.html", {
        "form": form,
        "title": "Edit Meeting",
        "meeting": meeting,
        "breadcrumbs": [
            {"label": "Meetings", "url": "/meetings/"},
            {"label": meeting.title, "url": f"/meetings/{meeting.pk}/"},
            {"label": "Edit"},
        ],
    })


@login_required
@require_feature("meetings")
@any_permission_required("view_meetings", "manage_meetings")
def meeting_action(request, pk):
    meeting = selectors.get_meeting_or_404(request, pk)
    if request.method != "POST":
        return redirect("meetings:detail", pk=pk)

    action = request.POST.get("action", "")

    if action == "save_minutes":
        if not can_edit_minutes(request.user, meeting):
            raise PermissionDenied
        form = MeetingMinutesForm(request.POST, instance=meeting)
        if form.is_valid():
            try:
                save_minutes_draft(meeting, form.cleaned_data, request.user)
                flash_success(request, "Minutes draft saved.")
            except MeetingWorkflowError as exc:
                flash_exception(request, exc)
        else:
            flash_exception(request, "Could not save minutes. Check the form and try again.")
        return redirect("meetings:detail", pk=pk)

    if action == "submit_minutes":
        if not can_submit_minutes(request.user, meeting):
            raise PermissionDenied
        form = MeetingMinutesForm(request.POST, instance=meeting)
        if form.is_valid():
            save_minutes_draft(meeting, form.cleaned_data, request.user)
        try:
            submit_minutes_for_approval(meeting, request.user)
            flash_info(request, "Minutes submitted for approval.")
            _notify_minutes_submitted(meeting)
        except MeetingWorkflowError as exc:
            flash_exception(request, exc)
        return redirect("meetings:detail", pk=pk)

    if action == "approve_minutes":
        try:
            if not can_approve_meeting_minutes(request.user, meeting):
                raise MeetingWorkflowError("You cannot approve these minutes.")
            approve_minutes(meeting, request.user)
            flash_success(request, "Minutes approved and locked.")
            _notify_minutes_decision(meeting, approved=True)
        except MeetingWorkflowError as exc:
            flash_exception(request, exc)
        return redirect("meetings:detail", pk=pk)

    if action == "reject_minutes":
        try:
            if not can_approve_meeting_minutes(request.user, meeting):
                raise MeetingWorkflowError("You cannot reject these minutes.")
            form = MinutesRejectForm(request.POST)
            reason = form.cleaned_data.get("rejection_reason", "") if form.is_valid() else ""
            reject_minutes(meeting, request.user, reason=reason)
            flash_info(request, "Minutes returned to the secretary for revision.")
            _notify_minutes_decision(meeting, approved=False, reason=reason)
        except MeetingWorkflowError as exc:
            flash_exception(request, exc)
        return redirect("meetings:detail", pk=pk)

    if action == "upload_attachment":
        if not can_manage_meetings(request.user):
            raise PermissionDenied
        form = MeetingAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.meeting = meeting
            attachment.uploaded_by = request.user
            repo.save_meeting_attachment(attachment)
            flash_success(request, "File uploaded.")
        else:
            flash_exception(request, "Upload failed. Select a valid file.")
        return redirect("meetings:detail", pk=pk)

    if action == "delete_attachment":
        if not can_manage_meetings(request.user):
            raise PermissionDenied
        attachment = selectors.get_meeting_attachment_or_404(
            meeting=meeting, pk=request.POST.get("attachment_id")
        )
        repo.delete_meeting_attachment(attachment)
        flash_success(request, "Attachment removed.")
        return redirect("meetings:detail", pk=pk)

    return redirect("meetings:detail", pk=pk)


def _notify_minutes_submitted(meeting):
    from dashboard.services import notify_user

    for user in selectors.active_users_for_church(meeting.church_id):
        if can_approve_meeting_minutes(user, meeting):
            notify_user(
                user,
                "Minutes pending approval",
                f'"{meeting.title}" minutes are ready for review.',
                category="INFO",
                action_url=f"/meetings/{meeting.pk}/",
            )


def _notify_minutes_decision(meeting, approved=True, reason=""):
    from dashboard.services import notify_user

    submitter = meeting.minutes_submitted_by
    if not submitter:
        return
    if approved:
        notify_user(
            submitter,
            "Minutes approved",
            f'Your minutes for "{meeting.title}" were approved.',
            category="SUCCESS",
            action_url=f"/meetings/{meeting.pk}/",
        )
    else:
        notify_user(
            submitter,
            "Minutes returned",
            f'"{meeting.title}" minutes need revision. {reason}'.strip(),
            category="WARNING",
            action_url=f"/meetings/{meeting.pk}/",
        )


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def meeting_attendance(request, pk):
    meeting = selectors.get_meeting_or_404(request, pk)
    if request.method == "POST":
        member_ids = request.POST.getlist("members")
        present_ids = request.POST.getlist("present")
        count = record_meeting_attendance(meeting, member_ids, present_ids)
        flash_success(request, f"Attendance recorded for {count} member(s).")
    return redirect("meetings:detail", pk=pk)


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def action_item_add(request, pk):
    meeting = selectors.get_meeting_or_404(request, pk)
    if not can_edit_minutes(request.user, meeting):
        raise PermissionDenied
    if request.method == "POST":
        form = ActionItemForm(request.POST, church=meeting.church)
        if form.is_valid():
            item = form.save(commit=False)
            item.meeting = meeting
            repo.save_action_item(item)
            flash_success(request, "Action item added.")
    return redirect("meetings:detail", pk=pk)


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def decision_add(request, pk):
    meeting = selectors.get_meeting_or_404(request, pk)
    if not can_edit_minutes(request.user, meeting):
        raise PermissionDenied
    if request.method == "POST":
        form = DecisionForm(request.POST)
        if form.is_valid():
            decision = form.save(commit=False)
            decision.meeting = meeting
            repo.save_decision(decision)
            flash_success(request, "Decision recorded.")
    return redirect("meetings:detail", pk=pk)


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def attendance_list(request):
    events = selectors.attendance_events_for_request(request)
    return render(request, "meetings/attendance_list.html", {"events": events})


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def attendance_create(request):
    church = require_church(request)
    if request.method == "POST":
        form = AttendanceEventForm(request.POST, church=church)
        if form.is_valid():
            event = form.save(commit=False)
            event.church = church
            event.created_by = request.user
            repo.save_attendance_event(event)
            flash_success(request, "Attendance event created.")
            return redirect("meetings:attendance_detail", pk=event.pk)
    else:
        form = AttendanceEventForm(church=church)
    return render(request, "meetings/attendance_form.html", {"form": form})


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def attendance_detail(request, pk):
    event = selectors.get_attendance_event_or_404(request, pk, with_records=True)
    members = selectors.active_members_for_church(event.church)
    present_ids = selectors.event_present_member_ids(event)
    return render(request, "meetings/attendance_detail.html", {
        "event": event,
        "members": members,
        "present_ids": present_ids,
    })


@login_required
@require_feature("meetings")
@permission_required("manage_meetings")
def attendance_record(request, pk):
    event = selectors.get_attendance_event_or_404(request, pk)
    if request.method == "POST":
        member_ids = request.POST.getlist("members")
        present_ids = request.POST.getlist("present")
        count = record_event_attendance(event, member_ids, present_ids)
        flash_success(request, f"Roll saved — {count} member(s).")
    return redirect("meetings:attendance_detail", pk=pk)
