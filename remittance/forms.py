"""Remittance policy and welfare forms."""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from remittance.models import RemittancePolicy, WelfareAssistanceCase
from remittance.services import get_unit_choices


class RemittancePolicyForm(forms.ModelForm):
    class Meta:
        model = RemittancePolicy
        fields = (
            "offering_type",
            "application_scope",
            "unit_type",
            "unit_id",
            "retain_percent",
            "remit_percent",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        )
        widgets = {
            "offering_type": forms.Select(attrs=select_attrs()),
            "application_scope": forms.Select(attrs=select_attrs()),
            "unit_type": forms.Select(attrs=select_attrs()),
            "retain_percent": forms.NumberInput(attrs=input_attrs(step="0.01", min="0", max="100")),
            "remit_percent": forms.NumberInput(attrs=input_attrs(step="0.01", min="0", max="100")),
            "effective_from": forms.DateInput(attrs=input_attrs(type="date")),
            "effective_to": forms.DateInput(attrs=input_attrs(type="date")),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs=textarea_attrs(rows=3)),
        }

    def __init__(self, *args, church=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.user = user
        unit_type = (
            self.data.get("unit_type")
            or (self.instance.unit_type if self.instance.pk else None)
            or self.initial.get("unit_type", "CHURCH")
        )
        choices = get_unit_choices(unit_type, church=church, user=user)
        initial_unit = (
            self.data.get("unit_id")
            or (str(self.instance.unit_id) if self.instance.pk else None)
            or self.initial.get("unit_id", "")
        )
        self.fields["unit_id"] = forms.ChoiceField(
            choices=choices or [("", "Select unit")],
            widget=forms.Select(attrs=select_attrs()),
            initial=initial_unit,
        )

    def clean(self):
        cleaned = super().clean()
        retain = cleaned.get("retain_percent")
        remit = cleaned.get("remit_percent")
        if retain is not None and remit is not None:
            if Decimal(str(retain)) + Decimal(str(remit)) != Decimal("100"):
                raise ValidationError("Retain and remit percentages must sum to 100.")

        raw_unit = self.data.get("unit_id") if self.data else None
        unit_type = cleaned.get("unit_type")
        if not unit_type and self.data:
            unit_type = self.data.get("unit_type")
        if raw_unit and self.user and unit_type:
            allowed = {
                choice_id
                for choice_id, _label in self.fields["unit_id"].choices
                if choice_id
            }
            if str(raw_unit) not in allowed:
                from remittance.services import log_remittance_scope_violation

                log_remittance_scope_violation(
                    self.user,
                    unit_type,
                    raw_unit,
                    reason="RemittancePolicyForm rejected out-of-scope unit_id",
                    church=self.church,
                )
        return cleaned


class SettlementDraftForm(forms.Form):
    offering_type = forms.ChoiceField(
        choices=RemittancePolicy.OFFERING_TYPES,
        widget=forms.Select(attrs=select_attrs()),
    )
    period_start = forms.DateField(widget=forms.DateInput(attrs=input_attrs(type="date")))
    period_end = forms.DateField(widget=forms.DateInput(attrs=input_attrs(type="date")))

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("period_start")
        end = cleaned.get("period_end")
        if start and end and end < start:
            raise ValidationError("Period end must be on or after period start.")
        return cleaned


class HierarchySettlementDraftForm(SettlementDraftForm):
    """Draft from a hierarchy unit (district, conference, union, GC)."""

    from_unit = forms.ChoiceField(
        widget=forms.Select(attrs=select_attrs()),
        label="From unit",
    )

    def __init__(self, *args, user=None, church=None, desk_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = desk_choices or []
        self.fields["from_unit"].choices = [("", "Select unit")] + [
            (f"{unit_type}:{unit_id}", label)
            for unit_type, unit_id, label in choices
        ]

    def clean_from_unit(self):
        raw = self.cleaned_data.get("from_unit") or ""
        if not raw or ":" not in raw:
            raise ValidationError("Select the unit sending this settlement.")
        unit_type, unit_id = raw.split(":", 1)
        return unit_type.upper(), unit_id


class WelfareCaseForm(forms.Form):
    member = forms.CharField(widget=forms.HiddenInput())
    assistance_type = forms.ChoiceField(
        choices=WelfareAssistanceCase.ASSISTANCE_TYPES,
        widget=forms.Select(attrs=select_attrs()),
        initial="OTHER",
    )
    priority = forms.ChoiceField(
        choices=WelfareAssistanceCase.PRIORITY_CHOICES,
        widget=forms.Select(attrs=select_attrs()),
        initial="NORMAL",
    )
    amount_requested = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs=input_attrs(step="0.01", min="0.01")),
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs=textarea_attrs(rows=3)),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church

    def clean(self):
        cleaned = super().clean()
        member_id = cleaned.get("member")
        if not member_id:
            raise ValidationError({"member": "Select a member."})
        from members.models import Member

        if not self.church:
            raise ValidationError({"member": "Church context is required."})
        try:
            cleaned["member_obj"] = Member.objects.get(
                pk=member_id,
                church=self.church,
                is_active=True,
            )
        except (Member.DoesNotExist, ValueError):
            raise ValidationError({"member": "Select a valid active member."})
        return cleaned


class WelfareApproveForm(forms.Form):
    amount_approved = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs=input_attrs(step="0.01", min="0.01")),
        help_text="Leave blank to approve the full requested amount.",
    )


class WelfareRejectForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
        required=False,
    )


class WelfareReviewForm(forms.Form):
    review_notes = forms.CharField(
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
        required=False,
    )


class WelfareDisburseForm(forms.Form):
    payment_account_type = forms.ChoiceField(
        choices=(("CASH", "Cash"), ("BANK", "Bank")),
        widget=forms.Select(attrs=select_attrs()),
        initial="CASH",
    )


class WelfareContributionForm(forms.Form):
    member = forms.CharField(widget=forms.HiddenInput())
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs=input_attrs(step="0.01", min="0.01")),
    )
    contribution_date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs=input_attrs(type="date")),
    )
    payment_account_type = forms.ChoiceField(
        choices=(("CASH", "Cash"), ("BANK", "Bank")),
        widget=forms.Select(attrs=select_attrs()),
        initial="CASH",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs=input_attrs()),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church

    def clean(self):
        cleaned = super().clean()
        member_id = cleaned.get("member")
        if not member_id:
            raise ValidationError({"member": "Select a member."})
        from members.models import Member

        if not self.church:
            raise ValidationError({"member": "Church context is required."})
        try:
            cleaned["member_obj"] = Member.objects.get(
                pk=member_id,
                church=self.church,
                is_active=True,
            )
        except (Member.DoesNotExist, ValueError):
            raise ValidationError({"member": "Select a valid active member."})
        return cleaned


class WelfareCaseAttachmentForm(forms.Form):
    label = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs=input_attrs()),
    )
    file = forms.FileField()

    def clean_file(self):
        from church_system.uploads import validate_upload

        uploaded = self.cleaned_data.get("file")
        validate_upload(uploaded, kind="document")
        return uploaded
