"""Forms for the owner Marketing Hub and public inquiry page."""

from urllib.parse import urlparse

from django import forms

from church_system.widgets import checkbox_attrs, input_attrs, select_attrs, textarea_attrs
from sitecontrol import marketing_selectors
from sitecontrol.models import (
    MarketingAsset,
    MarketingCampaign,
    MarketingLead,
    MarketingSettings,
)


def _require_https(value):
    if value and urlparse(value).scheme != "https":
        raise forms.ValidationError("Use an HTTPS URL.")
    return value


class MarketingSettingsForm(forms.ModelForm):
    class Meta:
        model = MarketingSettings
        fields = (
            "public_inquiry_enabled",
            "sales_notification_email",
            "marketing_site_url",
            "privacy_policy_url",
            "consent_text",
            "notify_on_new_lead",
            "lead_retention_days",
        )
        widgets = {
            "public_inquiry_enabled": forms.CheckboxInput(attrs=checkbox_attrs()),
            "sales_notification_email": forms.EmailInput(attrs=input_attrs()),
            "marketing_site_url": forms.URLInput(attrs=input_attrs()),
            "privacy_policy_url": forms.URLInput(attrs=input_attrs()),
            "consent_text": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "notify_on_new_lead": forms.CheckboxInput(attrs=checkbox_attrs()),
            "lead_retention_days": forms.NumberInput(
                attrs=input_attrs(min="30", max="2555")
            ),
        }

    def clean_marketing_site_url(self):
        return _require_https(self.cleaned_data.get("marketing_site_url"))

    def clean_privacy_policy_url(self):
        return _require_https(self.cleaned_data.get("privacy_policy_url"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("public_inquiry_enabled"):
            if not cleaned.get("privacy_policy_url"):
                self.add_error(
                    "privacy_policy_url",
                    "A privacy policy is required before public inquiries can be enabled.",
                )
            if not (cleaned.get("consent_text") or "").strip():
                self.add_error(
                    "consent_text",
                    "Consent wording is required before public inquiries can be enabled.",
                )
            if cleaned.get("notify_on_new_lead") and not cleaned.get(
                "sales_notification_email"
            ):
                self.add_error(
                    "sales_notification_email",
                    "Set a sales inbox or disable lead notifications.",
                )
        return cleaned


class MarketingCampaignForm(forms.ModelForm):
    class Meta:
        model = MarketingCampaign
        fields = (
            "name",
            "slug",
            "status",
            "source",
            "medium",
            "campaign_tag",
            "starts_at",
            "ends_at",
        )
        widgets = {
            "name": forms.TextInput(attrs=input_attrs()),
            "slug": forms.TextInput(attrs=input_attrs()),
            "status": forms.Select(attrs=select_attrs()),
            "source": forms.TextInput(attrs=input_attrs()),
            "medium": forms.TextInput(attrs=input_attrs()),
            "campaign_tag": forms.TextInput(attrs=input_attrs()),
            "starts_at": forms.DateTimeInput(
                attrs=input_attrs(type="datetime-local"), format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs=input_attrs(type="datetime-local"), format="%Y-%m-%dT%H:%M"
            ),
        }

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "End time must be after the start time.")
        return cleaned


class MarketingLeadUpdateForm(forms.ModelForm):
    class Meta:
        model = MarketingLead
        fields = ("status", "assigned_to", "internal_notes")
        widgets = {
            "status": forms.Select(attrs=select_attrs()),
            "assigned_to": forms.Select(attrs=select_attrs()),
            "internal_notes": forms.Textarea(attrs=textarea_attrs(rows=5)),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = marketing_selectors.platform_owners()
        self.fields["assigned_to"].required = False


class MarketingAssetForm(forms.ModelForm):
    class Meta:
        model = MarketingAsset
        fields = (
            "title",
            "description",
            "asset_type",
            "audience",
            "public_url",
            "status",
            "sort_order",
        )
        widgets = {
            "title": forms.TextInput(attrs=input_attrs()),
            "description": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "asset_type": forms.Select(attrs=select_attrs()),
            "audience": forms.TextInput(attrs=input_attrs()),
            "public_url": forms.URLInput(attrs=input_attrs()),
            "status": forms.Select(attrs=select_attrs()),
            "sort_order": forms.NumberInput(attrs=input_attrs(min="0", max="999")),
        }

    def clean_public_url(self):
        return _require_https(self.cleaned_data.get("public_url"))


class PublicMarketingInquiryForm(forms.Form):
    contact_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs=input_attrs(autocomplete="name")),
    )
    contact_email = forms.EmailField(
        widget=forms.EmailInput(attrs=input_attrs(autocomplete="email")),
    )
    contact_phone = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs=input_attrs(autocomplete="tel")),
    )
    organization_name = forms.CharField(
        max_length=200,
        required=False,
        label="Church or organization",
        widget=forms.TextInput(attrs=input_attrs()),
    )
    denomination = forms.ModelChoiceField(
        queryset=marketing_selectors.public_denominations(),
        required=False,
        empty_label="Select denomination (optional)",
        widget=forms.Select(attrs=select_attrs()),
    )
    message = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(
            attrs=textarea_attrs(
                rows=5,
                placeholder="Tell us what your church needs or request a demonstration.",
            )
        ),
    )
    consent = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs=checkbox_attrs()),
    )
    campaign_slug = forms.SlugField(max_length=80, required=False, widget=forms.HiddenInput())
    utm_source = forms.CharField(max_length=80, required=False, widget=forms.HiddenInput())
    utm_medium = forms.CharField(max_length=80, required=False, widget=forms.HiddenInput())
    utm_campaign = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput())
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, marketing_settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.marketing_settings = marketing_settings
        if marketing_settings:
            self.fields["consent"].label = marketing_settings.consent_text
        self.fields["denomination"].queryset = marketing_selectors.public_denominations()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("Unable to submit this inquiry.")
        return cleaned
