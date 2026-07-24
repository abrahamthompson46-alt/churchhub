"""Fixed asset register forms."""

from decimal import Decimal

from django import forms

from members.models import Member

from .models import AssetCategory, DepreciationPolicy, FixedAsset, AssetMaintenanceLog
from .services import allowed_methods_for_church, apply_category_defaults, validate_depreciation_method


class FixedAssetForm(forms.ModelForm):
    class Meta:
        model = FixedAsset
        fields = [
            "category",
            "name",
            "description",
            "location",
            "serial_number",
            "purchase_date",
            "acquisition_cost",
            "salvage_value",
            "useful_life_months",
            "depreciation_method",
            "custodian_member",
            "custodian_name",
            "insurance_expiry",
            "warranty_expiry",
            "supplier_name",
            "invoice_reference",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "insurance_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "warranty_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "depreciation_method": forms.Select(attrs={"class": "form-select"}),
            "custodian_member": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, church=None, **kwargs):
        self.church = church
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ("custodian_member",):
                if not isinstance(field.widget, forms.Textarea):
                    field.widget.attrs.setdefault("class", "form-control")
                else:
                    field.widget.attrs.setdefault("class", "form-control")
        if church:
            self.fields["category"].queryset = AssetCategory.objects.filter(
                church=church, is_active=True
            )
            self.fields["custodian_member"].queryset = Member.objects.filter(church=church)
            methods = allowed_methods_for_church(church)
            self.fields["depreciation_method"].choices = [
                c for c in FixedAsset._meta.get_field("depreciation_method").choices if c[0] in methods
            ]

    def clean(self):
        cleaned = super().clean()
        if self.church and cleaned.get("depreciation_method"):
            validate_depreciation_method(self.church, cleaned["depreciation_method"])
        cost = cleaned.get("acquisition_cost")
        salvage = cleaned.get("salvage_value")
        if cost is not None and cost <= Decimal("0"):
            self.add_error("acquisition_cost", "Acquisition cost must be greater than zero.")
        if cost is not None and salvage is not None and salvage > cost:
            self.add_error("salvage_value", "Salvage value cannot exceed acquisition cost.")
        return cleaned

    def save(self, commit=True):
        asset = super().save(commit=False)
        if self.church:
            asset.church = self.church
        if asset.category_id:
            apply_category_defaults(asset, asset.category)
        if commit:
            asset.save()
        return asset


class RejectAssetForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=True,
        label="Rejection reason",
    )


class DepreciationPolicyForm(forms.ModelForm):
    class Meta:
        model = DepreciationPolicy
        fields = [
            "allow_straight_line",
            "allow_declining_balance",
            "default_method",
            "auto_run_monthly",
            "run_day_of_month",
            "post_depreciation_to_ledger",
            "post_disposal_to_ledger",
            "capitalize_on_approval",
            "default_payment_account_type",
            "fiscal_year_start_month",
        ]
        widgets = {
            "allow_straight_line": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_declining_balance": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "auto_run_monthly": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "post_depreciation_to_ledger": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "post_disposal_to_ledger": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "capitalize_on_approval": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "run_day_of_month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 28}),
            "fiscal_year_start_month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "default_method": forms.Select(attrs={"class": "form-select"}),
            "default_payment_account_type": forms.Select(attrs={"class": "form-select"}),
        }


class AssetCategoryForm(forms.ModelForm):
    TEMPLATE_LOCKED_FIELDS = (
        "code",
        "gra_asset_class",
        "useful_life_months",
        "depreciation_method",
        "salvage_percent",
    )

    class Meta:
        model = AssetCategory
        fields = [
            "code",
            "name",
            "gra_asset_class",
            "useful_life_months",
            "depreciation_method",
            "salvage_percent",
            "is_active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "gra_asset_class": forms.Select(attrs={"class": "form-select"}),
            "useful_life_months": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "depreciation_method": forms.Select(attrs={"class": "form-select"}),
            "salvage_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.instance.is_custom:
            for field_name in self.TEMPLATE_LOCKED_FIELDS:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.pk and not self.instance.is_custom:
            for field_name in self.TEMPLATE_LOCKED_FIELDS:
                cleaned[field_name] = getattr(self.instance, field_name)
        return cleaned


class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = AssetMaintenanceLog
        fields = ["service_date", "description", "cost", "vendor"]
        widgets = {
            "service_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "vendor": forms.TextInput(attrs={"class": "form-control"}),
        }


class RunDepreciationForm(forms.Form):
    year = forms.IntegerField(min_value=2000, max_value=2100, widget=forms.NumberInput(attrs={"class": "form-control"}))
    month = forms.IntegerField(min_value=1, max_value=12, widget=forms.NumberInput(attrs={"class": "form-control"}))
