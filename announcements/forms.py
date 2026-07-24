from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import inlineformset_factory

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from members.models import Department
from permissions.checks import can_approve_announcements
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches
from permissions.scoping_checks import is_top_level_approver

from .models import (
    Announcement,
    AnnouncementImage,
)
from church_system.uploads import validate_upload

_WIDGETS = {
    "title": forms.TextInput(attrs=input_attrs(placeholder="Enter announcement title")),
    "content": forms.Textarea(attrs=textarea_attrs(rows=5, placeholder="Write the announcement...")),
    "visibility": forms.Select(attrs=select_attrs()),
    "church": forms.Select(attrs=select_attrs()),
    "event_date": forms.DateTimeInput(attrs={**input_attrs(), "type": "datetime-local"}),
    "publish_at": forms.DateTimeInput(attrs={**input_attrs(), "type": "datetime-local"}),
    "auto_expire": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "is_pinned": forms.CheckboxInput(attrs={"class": "form-check-input"}),
}


class AnnouncementForm(forms.ModelForm):
    """Create form — approval status is never set by the submitter."""

    target_roles = forms.MultipleChoiceField(
        choices=UserRole.CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs=select_attrs()),
        help_text="Leave empty to reach all roles in scope.",
    )
    target_departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs=select_attrs()),
        help_text="Leave empty to reach all departments.",
    )

    class Meta:
        model = Announcement
        fields = [
            "title",
            "content",
            "visibility",
            "church",
            "event_date",
            "publish_at",
            "auto_expire",
        ]
        widgets = _WIDGETS

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            churches = get_manageable_churches(user)
            if "church" in self.fields:
                self.fields["church"].queryset = churches
                self.fields["church"].required = False
            if not (is_top_level_approver(user) or can_approve_announcements(user)):
                self.fields["visibility"].choices = [
                    c for c in Announcement.VISIBILITY_CHOICES if c[0] == "church"
                ]
            self.fields["target_departments"].queryset = Department.objects.filter(
                church__in=churches
            ).order_by("name")
        self.fields["publish_at"].required = False
        self.fields["publish_at"].help_text = "Optional. Hide until this date/time after approval."

    def clean(self):
        cleaned = super().clean()
        visibility = cleaned.get("visibility") or "church"
        church = cleaned.get("church")
        if visibility == "church" and not church and self.user:
            from church_system.church_scope import get_user_church

            church = get_user_church(self.user)
            cleaned["church"] = church
        if visibility == "church" and not cleaned.get("church"):
            raise ValidationError({"church": "Select a church for this announcement."})
        if visibility == "general":
            cleaned["church"] = None
        return cleaned


class AnnouncementEditForm(forms.ModelForm):
    """Edit form — approvers may pin; creators edit pending submissions only."""

    target_roles = forms.MultipleChoiceField(
        choices=UserRole.CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs=select_attrs()),
        help_text="Leave empty to reach all roles in scope.",
    )
    target_departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs=select_attrs()),
        help_text="Leave empty to reach all departments.",
    )

    class Meta:
        model = Announcement
        fields = [
            "title",
            "content",
            "visibility",
            "church",
            "event_date",
            "publish_at",
            "auto_expire",
            "is_pinned",
        ]
        widgets = _WIDGETS

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            churches = get_manageable_churches(user)
            if "church" in self.fields:
                self.fields["church"].queryset = churches
                self.fields["church"].required = False
            self.fields["target_departments"].queryset = Department.objects.filter(
                church__in=churches
            ).order_by("name")
        if user and not can_approve_announcements(user):
            self.fields.pop("is_pinned", None)
        self.fields["publish_at"].required = False
        if self.instance and self.instance.pk:
            self.fields["target_roles"].initial = list(self.instance.target_roles or [])
            self.fields["target_departments"].initial = [
                link.department_id
                for link in self.instance.target_department_links.select_related("department")
            ]


class AnnouncementRejectForm(forms.Form):
    reason = forms.CharField(
        label="Rejection reason",
        widget=forms.Textarea(
            attrs=textarea_attrs(rows=3, placeholder="Explain why this was not approved…")
        ),
        min_length=3,
        max_length=2000,
    )


def _validate_image_file(image):
    if not image:
        return
    validate_upload(image, kind="image")


class AnnouncementImageForm(forms.ModelForm):
    class Meta:
        model = AnnouncementImage
        fields = ("image",)

    def clean_image(self):
        image = self.cleaned_data.get("image")
        _validate_image_file(image)
        return image


AnnouncementImageFormSet = inlineformset_factory(
    Announcement,
    AnnouncementImage,
    form=AnnouncementImageForm,
    fields=("image",),
    extra=2,
    can_delete=True,
)
