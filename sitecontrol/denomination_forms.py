"""Structured forms for denomination profile editing (no raw JSON)."""

from django import forms

from church_system.widgets import checkbox_attrs, input_attrs, select_attrs, textarea_attrs
from permissions.roles import UserRole
from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.denomination_defaults import DEFAULT_LEVEL_LABELS
from sitecontrol.denomination_services import merge_hierarchy_labels
from sitecontrol.models import Denomination

LEVEL_KEYS = (
    "general_conference",
    "union",
    "conference",
    "zone",
    "district",
    "church",
)

OFFERING_CODES = (
    ("TITHE", "Tithe / ministerial"),
    ("COMBINED", "Combined / weekly offering"),
    ("THANKSGIVING", "Thanksgiving"),
    ("BUILDING", "Building fund"),
    ("MISSION", "Mission"),
    ("WELFARE", "Welfare"),
)


class DenominationTerminologyForm(forms.Form):
    """Edit hierarchy level labels and visibility without touching code."""

    def __init__(self, denomination, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.denomination = denomination
        labels = merge_hierarchy_labels(denomination.hierarchy_labels if denomination else None)
        for key in LEVEL_KEYS:
            level = labels.get(key, DEFAULT_LEVEL_LABELS.get(key, {}))
            self.fields[f"{key}_enabled"] = forms.BooleanField(
                label=f"Enable {key.replace('_', ' ').title()}",
                required=False,
                initial=level.get("enabled", True),
                widget=forms.CheckboxInput(attrs=checkbox_attrs()),
            )
            self.fields[f"{key}_label"] = forms.CharField(
                label="Singular label",
                max_length=80,
                initial=level.get("label", ""),
                widget=forms.TextInput(attrs=input_attrs()),
            )
            self.fields[f"{key}_label_plural"] = forms.CharField(
                label="Plural label",
                max_length=80,
                initial=level.get("label_plural", ""),
                widget=forms.TextInput(attrs=input_attrs()),
            )

    def save(self, denomination):
        hierarchy_labels = {}
        for key in LEVEL_KEYS:
            hierarchy_labels[key] = {
                "enabled": self.cleaned_data.get(f"{key}_enabled", True),
                "label": self.cleaned_data[f"{key}_label"].strip(),
                "label_plural": self.cleaned_data[f"{key}_label_plural"].strip(),
            }
        denomination.hierarchy_labels = hierarchy_labels
        repo.save_model(denomination, update_fields=["hierarchy_labels", "updated_at"])
        return denomination


class DenominationSeedForm(forms.Form):
    """Edit default church seeds applied on onboarding."""

    enable_remittance = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=checkbox_attrs()))
    enable_payroll = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=checkbox_attrs()))
    payroll_jurisdiction = forms.ChoiceField(
        choices=(
            ("ghana", "Ghana (PAYE / SSNIT)"),
            ("none", "None — configure manually"),
        ),
        widget=forms.Select(attrs=select_attrs()),
    )
    remittance_preset = forms.ChoiceField(
        choices=(
            ("hierarchy_standard", "Hierarchy remittance (SDA-style)"),
            ("area_district", "Area / district split"),
            ("none", "Disabled"),
        ),
        widget=forms.Select(attrs=select_attrs()),
    )

    def __init__(self, denomination, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.denomination = denomination
        config = denomination.seed_config or {}
        self.fields["enable_remittance"].initial = config.get("enable_remittance", True)
        self.fields["enable_payroll"].initial = config.get("enable_payroll", True)
        self.fields["payroll_jurisdiction"].initial = config.get("payroll_jurisdiction", "ghana")
        self.fields["remittance_preset"].initial = config.get("remittance_preset", "hierarchy_standard")
        for code, label in OFFERING_CODES:
            existing = next(
                (o for o in config.get("offering_categories", []) if o.get("code") == code),
                {"name": label},
            )
            self.fields[f"offering_{code.lower()}"] = forms.CharField(
                label=label,
                max_length=100,
                initial=existing.get("name", label),
                widget=forms.TextInput(attrs=input_attrs()),
            )

    def save(self, denomination):
        offering_categories = []
        for code, _label in OFFERING_CODES:
            name = self.cleaned_data.get(f"offering_{code.lower()}", "").strip()
            offering_categories.append({"code": code, "name": name or code.title()})
        denomination.seed_config = {
            "offering_categories": offering_categories,
            "enable_remittance": self.cleaned_data.get("enable_remittance", False),
            "enable_payroll": self.cleaned_data.get("enable_payroll", False),
            "payroll_jurisdiction": self.cleaned_data["payroll_jurisdiction"],
            "remittance_preset": self.cleaned_data["remittance_preset"],
        }
        repo.save_model(denomination, update_fields=["seed_config", "updated_at"])
        return denomination


class DenominationBrandingForm(forms.ModelForm):
    class Meta:
        model = Denomination
        fields = (
            "display_name",
            "tagline",
            "logo",
            "primary_color",
            "accent_color",
            "highlight_color",
            "registration_intro",
            "allow_public_registration",
            "allow_institution_branding",
            "default_plan",
            "default_role",
        )
        widgets = {
            "display_name": forms.TextInput(attrs=input_attrs()),
            "tagline": forms.TextInput(attrs=input_attrs()),
            "registration_intro": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "primary_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
            "accent_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
            "highlight_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
            "allow_public_registration": forms.CheckboxInput(attrs=checkbox_attrs()),
            "allow_institution_branding": forms.CheckboxInput(attrs=checkbox_attrs()),
            "default_plan": forms.Select(attrs=select_attrs()),
            "default_role": forms.Select(attrs=select_attrs(), choices=UserRole.CHOICES),
        }
        help_texts = {
            "primary_color": "Navbar and chrome for this tenant.",
            "accent_color": "Buttons and primary links.",
            "highlight_color": "Secondary accent across dashboards and portal.",
            "allow_institution_branding": (
                "When enabled, institution Super Admins can update logo, "
                "display name, tagline, and colors from the staff app."
            ),
        }

    def clean_logo(self):
        from church_system.uploads import validate_upload

        logo = self.cleaned_data.get("logo")
        if logo:
            validate_upload(logo, kind="branding")
        return logo

    def save(self, commit=True):
        from sitecontrol.branding_services import apply_branding_to_form_instance

        instance = super().save(commit=False)
        apply_branding_to_form_instance(self, instance)
        if commit:
            instance.save()
        return instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_plan"].queryset = selectors.active_plans_ordered()
        self.fields["default_plan"].required = False
        self.fields["default_role"].choices = UserRole.CHOICES
