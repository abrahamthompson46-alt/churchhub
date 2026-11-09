"""Forms for contribution campaigns."""

from django import forms
from django.utils import timezone

from church_system.uploads import document_upload_validator
from contributions.models import CampaignKind, CampaignStatus, ContributionCampaign
from members.models import Member
from transactions.models import OfferingCategory


class ContributionCampaignForm(forms.ModelForm):
    class Meta:
        model = ContributionCampaign
        fields = [
            "kind",
            "name",
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
            "purpose": forms.Textarea(attrs={"rows": 2}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church is not None:
            from transactions.services import ensure_district_funeral_offering_category

            ensure_district_funeral_offering_category(church)
            self.fields["offering_category"].queryset = OfferingCategory.objects.filter(
                church=church,
                is_active=True,
            ).order_by("name")
            if not self.is_bound:
                kind = (self.initial.get("kind") if self.initial else None) or self.data.get("kind")
                if kind == CampaignKind.DISTRICT_FUNERAL or (
                    self.instance.pk and self.instance.kind == CampaignKind.DISTRICT_FUNERAL
                ):
                    funeral = OfferingCategory.objects.filter(
                        church=church, code="DISTRICT_FUNERAL", is_active=True
                    ).first()
                    if funeral and not self.instance.pk:
                        self.fields["offering_category"].initial = funeral.pk
                        self.fields["kind"].initial = CampaignKind.DISTRICT_FUNERAL
        self.fields["kind"].help_text = (
            "District funeral collections are held separately from welfare."
        )
        self.fields["purpose"].help_text = "Shown to members on the portal."
        self.fields["target_amount"].required = False
        self.fields["target_amount"].label = "Church goal"
        self.fields["default_member_target"].required = False
        self.fields["default_member_target"].label = "Member target"
        kind_value = (
            (self.initial.get("kind") if self.initial else None)
            or self.data.get("kind")
            or (self.instance.kind if self.instance.pk else None)
        )
        if kind_value == CampaignKind.DISTRICT_FUNERAL:
            self.fields["offering_category"].widget = forms.HiddenInput()
            self.fields["offering_category"].required = False
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.HiddenInput):
                continue
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select form-select-sm")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            else:
                widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_deadline(self):
        deadline = self.cleaned_data.get("deadline")
        if deadline and deadline < timezone.localdate() and not self.instance.pk:
            raise forms.ValidationError("Deadline cannot be in the past for a new campaign.")
        return deadline

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        category = cleaned.get("offering_category")
        if kind == CampaignKind.DISTRICT_FUNERAL and self.church:
            funeral = OfferingCategory.objects.filter(
                church=self.church, code="DISTRICT_FUNERAL", is_active=True
            ).first()
            if funeral:
                cleaned["offering_category"] = funeral
            elif category and category.code == "WELFARE":
                self.add_error(
                    "offering_category",
                    "District funeral collections cannot use the Welfare Fund.",
                )
        return cleaned


class RecordContributionForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        label="Member",
        widget=forms.HiddenInput(),
    )
    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    )
    contribution_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    payment_account_type = forms.ChoiceField(
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        initial="CASH",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    idempotency_key = forms.CharField(max_length=64, widget=forms.HiddenInput)

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church is not None:
            from transactions.services import resolve_transaction_date

            self.fields["member"].queryset = Member.objects.filter(
                church=church,
                is_deleted=False,
                is_active=True,
            ).order_by("last_name", "first_name")
            if not self.is_bound:
                self.fields["contribution_date"].initial = resolve_transaction_date(church)


class RemitCampaignForm(forms.Form):
    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "style": "max-width:10rem"}),
    )
    payment_account_type = forms.ChoiceField(
        choices=[("BANK", "Bank"), ("CASH", "Cash")],
        initial="BANK",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    idempotency_key = forms.CharField(max_length=64, widget=forms.HiddenInput)


class BulkContributionForm(forms.Form):
    contribution_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    idempotency_key = forms.CharField(max_length=64, widget=forms.HiddenInput)
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
    kind = forms.ChoiceField(
        required=False,
        choices=[("", "All types")] + list(CampaignKind.choices),
    )
