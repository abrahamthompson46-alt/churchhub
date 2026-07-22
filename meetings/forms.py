from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from meetings import selectors

from .models import (
    AttendanceEvent,
    Meeting,
    MeetingActionItem,
    MeetingAttachment,
    MeetingDecision,
    MeetingStatus,
    MeetingType,
    MinutesStatus,
)


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            "title",
            "meeting_type",
            "department",
            "agenda",
            "location",
            "chair_person",
            "secretary_name",
            "scheduled_at",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs=input_attrs()),
            "meeting_type": forms.Select(attrs=select_attrs()),
            "department": forms.Select(attrs=select_attrs()),
            "agenda": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "location": forms.TextInput(attrs=input_attrs()),
            "chair_person": forms.TextInput(attrs=input_attrs()),
            "secretary_name": forms.TextInput(attrs=input_attrs()),
            "scheduled_at": forms.DateTimeInput(attrs={**input_attrs(), "type": "datetime-local"}),
            "status": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["department"].queryset = selectors.departments_for_church(church)


class MeetingFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        **input_attrs(),
        "placeholder": "Search title, agenda, minutes…",
    }))
    meeting_type = forms.ChoiceField(
        required=False,
        choices=[("", "All types")] + list(MeetingType.choices),
        widget=forms.Select(attrs=select_attrs()),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + list(MeetingStatus.choices),
        widget=forms.Select(attrs=select_attrs()),
    )
    minutes_status = forms.ChoiceField(
        required=False,
        choices=[("", "All minutes states")] + list(MinutesStatus.choices),
        widget=forms.Select(attrs=select_attrs()),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}))


class MeetingMinutesForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            "status",
            "ended_at",
            "chair_person",
            "secretary_name",
            "minutes_opening",
            "minutes_previous",
            "minutes_deliberations",
            "minutes_motions",
            "minutes_votes",
            "minutes_adjournment",
            "minutes",
        ]
        widgets = {
            "status": forms.Select(attrs=select_attrs()),
            "ended_at": forms.DateTimeInput(attrs={**input_attrs(), "type": "datetime-local"}),
            "chair_person": forms.TextInput(attrs=input_attrs()),
            "secretary_name": forms.TextInput(attrs=input_attrs()),
            "minutes_opening": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "minutes_previous": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "minutes_deliberations": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "minutes_motions": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "minutes_votes": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "minutes_adjournment": forms.Textarea(attrs=textarea_attrs(rows=2)),
            "minutes": forms.Textarea(attrs=textarea_attrs(rows=3)),
        }


class MeetingAttachmentForm(forms.ModelForm):
    class Meta:
        model = MeetingAttachment
        fields = ["label", "file"]
        widgets = {
            "label": forms.TextInput(attrs={**input_attrs(), "placeholder": "e.g. Agenda PDF, Signed minutes"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control form-control-sm"}),
        }


class MinutesRejectForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs=textarea_attrs(rows=3)),
        required=False,
        label="Reason for rejection",
    )


class ActionItemForm(forms.ModelForm):
    class Meta:
        model = MeetingActionItem
        fields = ["description", "assigned_to", "due_date", "status"]
        widgets = {
            "description": forms.Textarea(attrs=textarea_attrs(rows=2)),
            "assigned_to": forms.Select(attrs=select_attrs()),
            "due_date": forms.DateInput(attrs={**input_attrs(), "type": "date"}),
            "status": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["assigned_to"].queryset = selectors.active_members_for_church(church)


class DecisionForm(forms.ModelForm):
    class Meta:
        model = MeetingDecision
        fields = ["motion_text", "decision_text", "vote_result"]
        widgets = {
            "motion_text": forms.TextInput(attrs={**input_attrs(), "placeholder": "Motion (optional)"}),
            "decision_text": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "vote_result": forms.TextInput(attrs={**input_attrs(), "placeholder": "e.g. Carried unanimously"}),
        }


class AttendanceEventForm(forms.ModelForm):
    class Meta:
        model = AttendanceEvent
        fields = ["title", "event_type", "department", "event_date", "headcount", "notes", "meeting"]
        widgets = {
            "title": forms.TextInput(attrs=input_attrs()),
            "event_type": forms.Select(attrs=select_attrs()),
            "department": forms.Select(attrs=select_attrs()),
            "event_date": forms.DateInput(attrs={**input_attrs(), "type": "date"}),
            "headcount": forms.NumberInput(attrs=input_attrs()),
            "notes": forms.Textarea(attrs=textarea_attrs(rows=2)),
            "meeting": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["department"].queryset = selectors.departments_for_church(church)
            self.fields["meeting"].queryset = selectors.meetings_for_church(church)
        self.fields["meeting"].required = False
