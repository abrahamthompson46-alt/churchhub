"""Forms for member portal spiritual submissions."""

from django import forms

from .models import SpiritualSubmissionKind


class PrayerRequestForm(forms.Form):
    body = forms.CharField(
        label="Prayer request",
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control", "placeholder": "Share your prayer need…"}),
    )
    is_anonymous = forms.BooleanField(
        label="Share anonymously with pastoral care team",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_body(self):
        text = (self.cleaned_data.get("body") or "").strip()
        if len(text) < 10:
            raise forms.ValidationError("Please write at least a few words.")
        if len(text) > 5000:
            raise forms.ValidationError("Please keep your request under 5000 characters.")
        return text


class ThanksgivingTestimonyForm(forms.Form):
    kind = forms.ChoiceField(
        label="Type",
        choices=(
            (SpiritualSubmissionKind.THANKSGIVING, "Thanksgiving"),
            (SpiritualSubmissionKind.TESTIMONY, "Testimony"),
        ),
        initial=SpiritualSubmissionKind.THANKSGIVING,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    title = forms.CharField(
        label="Title (optional)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Short headline"}),
    )
    body = forms.CharField(
        label="Your message",
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control", "placeholder": "Share praise or testimony…"}),
    )

    def clean_body(self):
        text = (self.cleaned_data.get("body") or "").strip()
        if len(text) < 10:
            raise forms.ValidationError("Please write at least a few words.")
        if len(text) > 8000:
            raise forms.ValidationError("Please keep your message under 8000 characters.")
        return text
