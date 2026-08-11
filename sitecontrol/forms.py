"""Platform owner forms."""

from django import forms
from django.contrib.auth import get_user_model

from church_system.widgets import checkbox_attrs, input_attrs, select_attrs, textarea_attrs
from organization.models import Church
from permissions.roles import UserRole
from sitecontrol import repositories as repo
from sitecontrol import selectors

from .models import (
    Denomination,
    PlatformAnnouncement,
    PlatformAuditLog,
    PlatformPaymentMethod,
    SiteSettings,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)
from .services import FEATURE_FIELDS

User = get_user_model()


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "support_email",
            "footer_text",
            "session_timeout_minutes",
            "login_max_attempts",
            "login_lockout_minutes",
            "maintenance_mode",
            "maintenance_block_apply",
            "maintenance_message",
            "enforce_subscription_limits",
            "platform_banner_enabled",
            "platform_banner_message",
        )
        widgets = {
            "support_email": forms.EmailInput(attrs=input_attrs()),
            "footer_text": forms.TextInput(attrs=input_attrs()),
            "session_timeout_minutes": forms.NumberInput(attrs=input_attrs(min="5", max="1440")),
            "login_max_attempts": forms.NumberInput(attrs=input_attrs(min="3", max="20")),
            "login_lockout_minutes": forms.NumberInput(attrs=input_attrs(min="1", max="120")),
            "maintenance_message": forms.Textarea(attrs=textarea_attrs(rows=2)),
            "platform_banner_message": forms.Textarea(attrs=textarea_attrs(rows=2)),
        }


class RegistrationSettingsForm(forms.ModelForm):
    application_default_role = forms.ChoiceField(
        choices=UserRole.CHOICES,
        widget=forms.Select(attrs=select_attrs()),
    )

    class Meta:
        model = SiteSettings
        fields = (
            "allow_church_self_registration",
            "allow_institution_user_invites",
            "allow_institution_church_onboarding",
            "registration_intro",
            "application_default_plan",
            "application_default_role",
        )
        widgets = {
            "registration_intro": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "application_default_plan": forms.Select(attrs=select_attrs()),
            "allow_church_self_registration": forms.CheckboxInput(attrs=checkbox_attrs()),
            "allow_institution_user_invites": forms.CheckboxInput(attrs=checkbox_attrs()),
            "allow_institution_church_onboarding": forms.CheckboxInput(attrs=checkbox_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application_default_plan"].queryset = selectors.active_plans_ordered()
        self.fields["application_default_plan"].required = False


class TenantApplicationForm(forms.Form):
    denomination = forms.ModelChoiceField(
        queryset=selectors.public_registration_denominations(),
        widget=forms.Select(attrs=select_attrs()),
    )
    application_type = forms.ChoiceField(
        choices=TenantApplication.TYPE_CHOICES,
        widget=forms.RadioSelect,
        initial="EXISTING_DISTRICT",
    )
    church_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    church_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=2)))
    district = forms.ModelChoiceField(
        queryset=selectors.districts_for_public_registration(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    conference_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    conference_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    zone_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    zone_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    district_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    district_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    contact_name = forms.CharField(max_length=120, widget=forms.TextInput(attrs=input_attrs()))
    contact_email = forms.EmailField(widget=forms.EmailInput(attrs=input_attrs()))
    contact_phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    applicant_username = forms.CharField(max_length=150, widget=forms.TextInput(attrs=input_attrs()))
    applicant_notes = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=3)))

    def __init__(self, *args, denomination=None, **kwargs):
        super().__init__(*args, **kwargs)
        denom = denomination
        if not denom and self.is_bound:
            denom_id = self.data.get("denomination")
            if denom_id:
                denom = selectors.denomination_by_pk(denom_id)
        if denom:
            self.fields["denomination"].initial = denom.pk
            self.fields["district"].queryset = selectors.districts_for_denomination(denom)
        else:
            self.fields["district"].queryset = selectors.empty_districts()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("denomination"):
            self.add_error("denomination", "Select your denomination.")
        app_type = cleaned.get("application_type")
        if app_type == "EXISTING_DISTRICT" and not cleaned.get("district"):
            self.add_error("district", "Select the district your church belongs to.")
        if app_type == "NEW_HIERARCHY":
            required = (
                "conference_name", "conference_code", "zone_name", "zone_code",
                "district_name", "district_code",
            )
            for field in required:
                if not cleaned.get(field):
                    self.add_error(field, "Required for a new organization path.")
        code = cleaned.get("church_code", "")
        if code:
            cleaned["church_code"] = code.strip().upper()
        return cleaned


class ApplicationReviewForm(forms.Form):
    review_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs=textarea_attrs(rows=3)),
        label="Review notes",
    )
    plan = forms.ModelChoiceField(
        queryset=selectors.empty_plans(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
        label="Subscription plan",
        help_text="Leave blank to use denomination or site default.",
    )
    status = forms.ChoiceField(
        choices=[("TRIAL", "Trial"), ("ACTIVE", "Active")],
        initial="ACTIVE",
        widget=forms.Select(attrs=select_attrs()),
    )
    billing_interval = forms.ChoiceField(
        choices=TenantSubscription.BILLING_INTERVALS,
        initial="MONTHLY",
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_method = forms.ModelChoiceField(
        queryset=selectors.empty_payment_methods(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs=input_attrs()),
        label="Payment reference",
    )
    trial_days = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs=input_attrs(min="1", max="365")),
        help_text="Override plan trial length when status is Trial.",
    )
    admin_role = forms.ChoiceField(
        choices=UserRole.CHOICES,
        required=False,
        widget=forms.Select(attrs=select_attrs()),
        label="First user role",
        help_text="Leave blank to use denomination or site default.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = selectors.active_plans_ordered()
        self.fields["payment_method"].queryset = selectors.active_payment_methods_ordered()


class BillingSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "default_billing_currency",
            "billing_payment_instructions",
        )
        widgets = {
            "default_billing_currency": forms.TextInput(attrs=input_attrs(maxlength="3")),
            "billing_payment_instructions": forms.Textarea(attrs=textarea_attrs(rows=4)),
        }


class PlatformPaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PlatformPaymentMethod
        fields = (
            "name",
            "method_type",
            "instructions",
            "is_active",
            "is_default",
            "sort_order",
        )
        widgets = {
            "name": forms.TextInput(attrs=input_attrs()),
            "method_type": forms.Select(attrs=select_attrs()),
            "instructions": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "is_active": forms.CheckboxInput(attrs=checkbox_attrs()),
            "is_default": forms.CheckboxInput(attrs=checkbox_attrs()),
            "sort_order": forms.NumberInput(attrs=input_attrs(min="0")),
        }


class PlatformTenantSetupForm(forms.Form):
    SETUP_MODES = [
        ("EXISTING_DISTRICT", "Add church to existing district"),
        ("NEW_HIERARCHY", "Create new conference / zone / district path"),
    ]

    denomination = forms.ModelChoiceField(
        queryset=selectors.active_denominations_ordered(),
        widget=forms.Select(attrs=select_attrs()),
    )
    setup_mode = forms.ChoiceField(
        choices=SETUP_MODES,
        widget=forms.RadioSelect,
        initial="EXISTING_DISTRICT",
    )
    church_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    church_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=2)))
    district = forms.ModelChoiceField(
        queryset=selectors.empty_districts(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    conference_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    conference_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    zone_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    zone_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    district_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs=input_attrs()))
    district_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs=input_attrs()))
    admin_email = forms.EmailField(widget=forms.EmailInput(attrs=input_attrs()))
    admin_username = forms.CharField(max_length=150, widget=forms.TextInput(attrs=input_attrs()))
    admin_first_name = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs=input_attrs()))
    admin_role = forms.ChoiceField(
        choices=UserRole.CHOICES,
        widget=forms.Select(attrs=select_attrs()),
        initial=UserRole.LOCAL_PASTOR,
    )
    plan = forms.ModelChoiceField(
        queryset=selectors.empty_plans(),
        widget=forms.Select(attrs=select_attrs()),
    )
    status = forms.ChoiceField(
        choices=[("TRIAL", "Trial"), ("ACTIVE", "Active")],
        initial="TRIAL",
        widget=forms.Select(attrs=select_attrs()),
    )
    billing_interval = forms.ChoiceField(
        choices=TenantSubscription.BILLING_INTERVALS,
        initial="MONTHLY",
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_method = forms.ModelChoiceField(
        queryset=selectors.empty_payment_methods(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs=input_attrs()),
    )
    trial_days = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs=input_attrs(min="1", max="365")),
    )
    send_invite = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs=checkbox_attrs()),
        label="Send admin invitation email",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = selectors.active_plans_ordered()
        self.fields["payment_method"].queryset = selectors.active_payment_methods_ordered()
        denom = None
        if self.is_bound:
            denom_id = self.data.get("denomination")
            if denom_id:
                denom = selectors.denomination_by_pk(denom_id)
        elif self.initial.get("denomination"):
            denom = self.initial.get("denomination")
        if denom:
            self.fields["district"].queryset = selectors.districts_for_denomination(denom)
        else:
            self.fields["district"].queryset = selectors.districts_with_parents_limited()

    def clean(self):
        cleaned = super().clean()
        setup_mode = cleaned.get("setup_mode")
        if setup_mode == "EXISTING_DISTRICT" and not cleaned.get("district"):
            self.add_error("district", "Select the district for this church.")
        if setup_mode == "NEW_HIERARCHY":
            for field in (
                "conference_name", "conference_code", "zone_name", "zone_code",
                "district_name", "district_code",
            ):
                if not cleaned.get(field):
                    self.add_error(field, "Required when creating a new organization path.")
        code = cleaned.get("church_code", "")
        if code:
            cleaned["church_code"] = code.strip().upper()
        for code_field in ("conference_code", "zone_code", "district_code"):
            val = cleaned.get(code_field, "")
            if val:
                cleaned[code_field] = val.strip().upper()
        return cleaned


class BrandingSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "site_name",
            "site_tagline",
            "login_highlights",
            "footer_text",
            "logo",
            "favicon",
            "admin_primary_color",
            "accent_color",
            "highlight_color",
        )
        widgets = {
            "site_name": forms.TextInput(attrs=input_attrs()),
            "site_tagline": forms.TextInput(attrs=input_attrs()),
            "login_highlights": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "footer_text": forms.TextInput(attrs=input_attrs()),
            "admin_primary_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
            "accent_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
            "highlight_color": forms.TextInput(attrs={**input_attrs(), "type": "color"}),
        }
        help_texts = {
            "site_name": "Platform product name shown on login and footers.",
            "site_tagline": "Short line under the platform name on the login page.",
            "login_highlights": "One highlight per line on the staff login brand panel.",
            "footer_text": "Shown in the application footer when signed in.",
            "admin_primary_color": "Brand chrome (navbar). Overridden per denomination when set.",
            "accent_color": "Primary buttons and links.",
            "highlight_color": "Secondary accent (KPIs, highlights).",
        }

    def save(self, commit=True):
        from sitecontrol.branding_services import apply_branding_to_form_instance

        instance = super().save(commit=False)
        apply_branding_to_form_instance(self, instance)
        if commit:
            instance.save()
        return instance

    def clean_logo(self):
        from church_system.uploads import validate_upload

        logo = self.cleaned_data.get("logo")
        if logo:
            validate_upload(logo, kind="branding")
        return logo

    def clean_favicon(self):
        from church_system.uploads import validate_upload

        favicon = self.cleaned_data.get("favicon")
        if favicon:
            validate_upload(favicon, kind="branding")
        return favicon


class EmailSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "smtp_use_tls",
            "default_from_email",
        )
        widgets = {
            "smtp_host": forms.TextInput(attrs=input_attrs()),
            "smtp_port": forms.NumberInput(attrs=input_attrs(min="1", max="65535")),
            "smtp_username": forms.TextInput(attrs=input_attrs()),
            "smtp_password": forms.PasswordInput(attrs=input_attrs(render_value=False)),
            "default_from_email": forms.EmailInput(attrs=input_attrs()),
            "smtp_use_tls": forms.CheckboxInput(attrs=checkbox_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["smtp_host"].help_text = "e.g. smtp.gmail.com or smtp.office365.com"
        self.fields["smtp_port"].help_text = "587 with TLS (recommended) or 465 with SSL"
        self.fields["smtp_username"].help_text = "Usually your full email address"
        self.fields["default_from_email"].help_text = (
            "Must be allowed by your SMTP provider (often the same as the username)."
        )
        self.fields["smtp_use_tls"].help_text = "Use for port 587. Leave unchecked for port 465 (SSL)."
        self.fields["smtp_password"].required = False
        self.fields["smtp_password"].help_text = (
            "Leave blank to keep the current password. New values are stored encrypted. "
            "For Gmail, use an App Password (not your normal login password)."
        )

    def save(self, commit=True):
        from sitecontrol.crypto import encrypt_secret

        instance = super().save(commit=False)
        raw = self.cleaned_data.get("smtp_password") or ""
        if raw:
            instance.smtp_password_encrypted = encrypt_secret(raw)
            instance.smtp_password = ""  # clear legacy plaintext
        if commit:
            repo.save_model(instance)
        return instance


class SecuritySettingsForm(forms.ModelForm):
    PLATFORM_ROLE_CHOICES = [
        ("OWNER", "Platform Owner"),
        ("SECURITY", "Security Admin"),
        ("BILLING", "Billing Admin"),
        ("SUPPORT", "Support Operator"),
        ("READONLY", "Read Only"),
    ]

    mfa_institution_roles = forms.MultipleChoiceField(
        choices=UserRole.CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Institution roles requiring MFA",
        help_text="Applied only when MFA enforcement is enabled.",
    )
    mfa_platform_roles = forms.MultipleChoiceField(
        choices=PLATFORM_ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Platform roles requiring MFA",
        help_text="Applied only when MFA enforcement is enabled.",
    )

    class Meta:
        model = SiteSettings
        fields = (
            "password_min_length",
            "password_require_uppercase",
            "mfa_required_for_privileged",
            "mfa_include_django_superusers",
            "platform_ip_allowlist",
            "maintenance_block_apply",
        )
        widgets = {
            "password_min_length": forms.NumberInput(attrs=input_attrs(min="6", max="128")),
            "password_require_uppercase": forms.CheckboxInput(attrs=checkbox_attrs()),
            "mfa_required_for_privileged": forms.CheckboxInput(attrs=checkbox_attrs()),
            "mfa_include_django_superusers": forms.CheckboxInput(attrs=checkbox_attrs()),
            "platform_ip_allowlist": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "maintenance_block_apply": forms.CheckboxInput(attrs=checkbox_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance and instance.pk:
            inst_roles = list(instance.mfa_institution_roles or [])
            plat_roles = list(instance.mfa_platform_roles or [])
            if not inst_roles:
                from sitecontrol.models import default_mfa_institution_roles

                inst_roles = default_mfa_institution_roles()
            if not plat_roles:
                from sitecontrol.models import default_mfa_platform_roles

                plat_roles = default_mfa_platform_roles()
            self.fields["mfa_institution_roles"].initial = inst_roles
            self.fields["mfa_platform_roles"].initial = plat_roles

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.mfa_institution_roles = list(
            self.cleaned_data.get("mfa_institution_roles") or []
        )
        instance.mfa_platform_roles = list(self.cleaned_data.get("mfa_platform_roles") or [])
        if commit:
            repo.save_model(instance)
        return instance


class FeatureRegistryForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "global_enable_payroll",
            "global_enable_remittance",
            "global_enable_ledger",
            "global_enable_meetings",
            "global_enable_giving",
            "global_enable_budgets",
            "global_enable_advanced_reports",
            "global_enable_assets",
            "global_enable_contributions",
        )
        widgets = {
            "global_enable_payroll": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_remittance": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_ledger": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_meetings": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_giving": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_budgets": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_advanced_reports": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_assets": forms.CheckboxInput(attrs=checkbox_attrs()),
            "global_enable_contributions": forms.CheckboxInput(attrs=checkbox_attrs()),
        }


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = (
            "name",
            "code",
            "description",
            "currency",
            "price_monthly",
            "price_yearly",
            "setup_fee",
            "trial_days",
            "max_users",
            "max_branches",
            "feature_payroll",
            "feature_remittance",
            "feature_ledger",
            "feature_meetings",
            "feature_advanced_reports",
            "feature_budgets",
            "feature_giving_portal",
            "feature_assets",
            "feature_contribution_campaigns",
            "is_default",
            "is_active",
            "sort_order",
        )
        widgets = {
            "description": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "currency": forms.TextInput(attrs=input_attrs(maxlength="3")),
            "price_monthly": forms.NumberInput(attrs=input_attrs(step="0.01", min="0")),
            "price_yearly": forms.NumberInput(attrs=input_attrs(step="0.01", min="0")),
            "setup_fee": forms.NumberInput(attrs=input_attrs(step="0.01", min="0")),
            "trial_days": forms.NumberInput(attrs=input_attrs(min="0", max="365")),
            "max_users": forms.NumberInput(attrs=input_attrs(min="1")),
            "max_branches": forms.NumberInput(attrs=input_attrs(min="1")),
            "sort_order": forms.NumberInput(attrs=input_attrs(min="0")),
        }


class TenantSubscriptionForm(forms.ModelForm):
    class Meta:
        model = TenantSubscription
        fields = (
            "church",
            "plan",
            "status",
            "billing_interval",
            "payment_method",
            "payment_reference",
            "started_at",
            "expires_at",
            "next_billing_at",
            "last_payment_at",
            "override_max_users",
            "override_max_branches",
            "notes",
        )
        widgets = {
            "church": forms.Select(attrs=select_attrs()),
            "plan": forms.Select(attrs=select_attrs()),
            "status": forms.Select(attrs=select_attrs()),
            "billing_interval": forms.Select(attrs=select_attrs()),
            "payment_method": forms.Select(attrs=select_attrs()),
            "payment_reference": forms.TextInput(attrs=input_attrs()),
            "started_at": forms.DateInput(attrs=input_attrs(type="date")),
            "expires_at": forms.DateInput(attrs=input_attrs(type="date")),
            "next_billing_at": forms.DateInput(attrs=input_attrs(type="date")),
            "last_payment_at": forms.DateTimeInput(attrs=input_attrs(type="datetime-local")),
            "override_max_users": forms.NumberInput(attrs=input_attrs(min="1")),
            "override_max_branches": forms.NumberInput(attrs=input_attrs(min="1")),
            "notes": forms.Textarea(attrs=textarea_attrs(rows=2)),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["church"].queryset = selectors.churches_ordered_with_district()
        self.fields["plan"].queryset = selectors.active_plans_ordered()
        self.fields["payment_method"].queryset = selectors.active_payment_methods_ordered()
        for feature in FEATURE_FIELDS:
            field_name = f"override_{feature}"
            self.fields[field_name] = forms.BooleanField(
                required=False,
                label=f"Override: enable {feature.replace('_', ' ')}",
                widget=forms.CheckboxInput(attrs=checkbox_attrs()),
            )
            if self.instance and self.instance.pk:
                overrides = self.instance.feature_overrides or {}
                if feature in overrides:
                    self.fields[field_name].initial = overrides[feature]

    def save(self, commit=True):
        instance = super().save(commit=False)
        overrides = dict(instance.feature_overrides or {})
        for feature in FEATURE_FIELDS:
            field_name = f"override_{feature}"
            if field_name in self.cleaned_data:
                if self.cleaned_data[field_name]:
                    overrides[feature] = True
                elif feature in overrides:
                    del overrides[feature]
        instance.feature_overrides = overrides
        if commit:
            repo.save_subscription(instance)
            self.save_m2m()
        return instance


class RecordSubscriptionPaymentForm(forms.Form):
    """Record a SaaS subscription payment and advance billing dates."""

    payment_method = forms.ModelChoiceField(
        queryset=selectors.empty_payment_methods(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs=input_attrs()),
        label="Payment reference",
        help_text="Bank transfer reference, receipt number, or gateway ID.",
    )
    paid_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs=input_attrs(type="datetime-local")),
        label="Paid at",
        help_text="Defaults to now if left blank.",
    )
    reactivate = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs=checkbox_attrs()),
        label="Reactivate if expired or suspended",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
        help_text="Optional note appended to subscription lifecycle notes.",
    )

    def __init__(self, *args, **kwargs):
        subscription = kwargs.pop("subscription", None)
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].queryset = selectors.active_payment_methods_ordered()
        if subscription and subscription.payment_method_id:
            self.fields["payment_method"].initial = subscription.payment_method_id
        if subscription and subscription.payment_reference:
            self.fields["payment_reference"].initial = subscription.payment_reference


class TenantChurchForm(forms.ModelForm):
    class Meta:
        model = Church
        fields = ("name", "code", "address", "district")
        widgets = {
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
            "address": forms.Textarea(attrs=textarea_attrs(rows=2)),
            "district": forms.Select(attrs=select_attrs()),
        }


class PlatformOperatorForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs=input_attrs()),
        required=False,
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs=input_attrs()),
        required=False,
    )
    is_breakglass = forms.BooleanField(
        label="Break-glass Django admin access",
        required=False,
        help_text="Allows /admin/ for emergency database operations.",
        widget=forms.CheckboxInput(attrs=checkbox_attrs()),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "platform_role",
            "managed_denominations",
        )
        widgets = {
            "username": forms.TextInput(attrs=input_attrs()),
            "email": forms.EmailInput(attrs=input_attrs()),
            "first_name": forms.TextInput(attrs=input_attrs()),
            "last_name": forms.TextInput(attrs=input_attrs()),
            "is_active": forms.CheckboxInput(attrs=checkbox_attrs()),
            "platform_role": forms.Select(attrs=select_attrs()),
            "managed_denominations": forms.SelectMultiple(attrs=select_attrs()),
        }

    def __init__(self, *args, **kwargs):
        self.is_create = kwargs.pop("is_create", False)
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        from sitecontrol.rbac import CAP_GRANT_BREAKGLASS, ROLE_OWNER, operator_has_capability

        self.fields["managed_denominations"].queryset = selectors.active_denominations_ordered()
        self.fields["managed_denominations"].required = False
        self.fields["managed_denominations"].help_text = (
            "Assign denominations this operator may manage. Required unless role is Owner."
        )
        self.fields["platform_role"].required = True
        if self.is_create:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
            self.fields["platform_role"].initial = "SUPPORT"
        if self.instance.pk and self.instance.is_superuser:
            self.fields["is_breakglass"].initial = True

        can_grant = (
            self.actor
            and operator_has_capability(self.actor, CAP_GRANT_BREAKGLASS)
        )
        if not can_grant:
            self.fields["is_breakglass"].disabled = True
            self.fields["is_breakglass"].help_text = (
                "Only Security Admins / Owners can grant break-glass access."
            )

    def clean(self):
        from sitecontrol.rbac import CAP_GRANT_BREAKGLASS, ROLE_OWNER, operator_has_capability

        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 or p2 or self.is_create:
            if p1 != p2:
                raise forms.ValidationError("Passwords do not match.")
            if not p1:
                raise forms.ValidationError("Password is required.")

        role = cleaned.get("platform_role") or ""
        denoms = cleaned.get("managed_denominations")
        if role != ROLE_OWNER and (not denoms or len(denoms) == 0):
            self.add_error(
                "managed_denominations",
                "Non-owner operators must be assigned at least one denomination.",
            )

        want_breakglass = cleaned.get("is_breakglass")
        if want_breakglass:
            if not self.actor or not operator_has_capability(self.actor, CAP_GRANT_BREAKGLASS):
                self.add_error("is_breakglass", "You cannot grant break-glass access.")
            # Preserve existing breakglass if actor cannot change it was already handled by disabled
        elif self.fields["is_breakglass"].disabled and self.instance.pk:
            cleaned["is_breakglass"] = self.instance.is_superuser

        return cleaned

    def save(self, commit=True):
        from sitecontrol.rbac import CAP_GRANT_BREAKGLASS, operator_has_capability

        user = super().save(commit=False)
        user.is_platform_user = True
        user.church = None
        can_grant = self.actor and operator_has_capability(self.actor, CAP_GRANT_BREAKGLASS)
        if can_grant:
            user.is_staff = bool(self.cleaned_data.get("is_breakglass"))
            user.is_superuser = bool(self.cleaned_data.get("is_breakglass"))
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            repo.save_model(user)
            self.save_m2m()
        return user


class PlatformAnnouncementForm(forms.ModelForm):
    class Meta:
        model = PlatformAnnouncement
        fields = (
            "title",
            "message",
            "is_active",
            "show_on_login",
            "starts_at",
            "ends_at",
        )
        widgets = {
            "title": forms.TextInput(attrs=input_attrs()),
            "message": forms.Textarea(attrs=textarea_attrs(rows=4)),
            "is_active": forms.CheckboxInput(attrs=checkbox_attrs()),
            "show_on_login": forms.CheckboxInput(attrs=checkbox_attrs()),
            "starts_at": forms.DateTimeInput(attrs=input_attrs(type="datetime-local")),
            "ends_at": forms.DateTimeInput(attrs=input_attrs(type="datetime-local")),
        }


class DenominationForm(forms.ModelForm):
    class Meta:
        model = Denomination
        fields = (
            "code",
            "name",
            "display_name",
            "tagline",
            "is_active",
            "is_default",
            "logo",
            "primary_color",
            "accent_color",
            "allow_public_registration",
            "allow_institution_branding",
            "registration_intro",
            "default_plan",
            "default_role",
            "feature_payroll",
            "feature_remittance",
            "feature_ledger",
            "feature_meetings",
            "feature_advanced_reports",
            "feature_budgets",
            "feature_giving_portal",
            "feature_assets",
            "feature_contribution_campaigns",
        )
        widgets = {
            "code": forms.TextInput(attrs=input_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "display_name": forms.TextInput(attrs=input_attrs()),
            "tagline": forms.TextInput(attrs=input_attrs()),
            "registration_intro": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "default_plan": forms.Select(attrs=select_attrs()),
            "default_role": forms.Select(attrs=select_attrs(), choices=UserRole.CHOICES),
            "primary_color": forms.TextInput(attrs=input_attrs(type="color")),
            "accent_color": forms.TextInput(attrs=input_attrs(type="color")),
            "is_active": forms.CheckboxInput(attrs=checkbox_attrs()),
            "is_default": forms.CheckboxInput(attrs=checkbox_attrs()),
            "allow_public_registration": forms.CheckboxInput(attrs=checkbox_attrs()),
            "allow_institution_branding": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_payroll": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_remittance": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_ledger": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_meetings": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_advanced_reports": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_budgets": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_giving_portal": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_assets": forms.CheckboxInput(attrs=checkbox_attrs()),
            "feature_contribution_campaigns": forms.CheckboxInput(attrs=checkbox_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_plan"].queryset = selectors.active_plans_ordered()
        self.fields["default_plan"].required = False
        self.fields["default_role"].choices = UserRole.CHOICES

    def clean_logo(self):
        from church_system.uploads import validate_upload

        logo = self.cleaned_data.get("logo")
        if logo:
            validate_upload(logo, kind="branding")
        return logo
