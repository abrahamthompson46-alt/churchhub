"""Forms for contribution campaigns."""

from django import forms
from django.utils import timezone

from church_system.uploads import document_upload_validator
from contributions.models import CampaignStatus, ContributionCampaign
from members.models import Member
from transactions.models import OfferingCategory


class ContributionCampaignForm(forms.ModelForm):
    class Meta:
        model = ContributionCampaign
        fields = [
            "name",
            "code",
            "purpose",
            "deadline",
            "target_amount",
            "default_member_target",
            "offering_category",
            "portal_visible",
            "show_church_progress",
            "send_email_reminders",
        ]
        widgets = {
            "purpose": forms.Textarea(attrs={"rows": 4}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church is not None:
            self.fields["offering_category"].queryset = OfferingCategory.objects.filter(
                church=church,
                is_active=True,
            ).order_by("name")
        self.fields["code"].help_text = "Short unique code (e.g. HARVEST2026). Used for receipt posting."
        self.fields["target_amount"].required = False
        self.fields["default_member_target"].required = False

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean_deadline(self):
        deadline = self.cleaned_data.get("deadline")
        if deadline and deadline < timezone.localdate() and not self.instance.pk:
            raise forms.ValidationError("Deadline cannot be in the past for a new campaign.")
        return deadline


class RecordContributionForm(forms.Form):
    member = forms.ModelChoiceField(queryset=Member.objects.none(), label="Member")
    amount = forms.DecimalField(min_value=0.01, max_digits=14, decimal_places=2)
    contribution_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    payment_account_type = forms.ChoiceField(
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        initial="CASH",
    )
    notes = forms.CharField(required=False, max_length=255, widget=forms.TextInput)

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church is not None:
            self.fields["member"].queryset = Member.objects.filter(
                church=church,
                is_deleted=False,
                is_active=True,
            ).order_by("last_name", "first_name")


class BulkContributionForm(forms.Form):
    contribution_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    payment_account_type = forms.ChoiceField(
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        initial="CASH",
    )


class CampaignImportForm(forms.Form):
    file = forms.FileField(label="Excel file (.xlsx)", validators=[document_upload_validator])
    commit = forms.BooleanField(
        required=False,
        initial=False,
        label="Import now (skip preview)",
    )


class CampaignFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + list(CampaignStatus.choices),
    )
