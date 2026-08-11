"""Platform-wide settings, subscription plans, and tenant entitlements."""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def default_mfa_institution_roles():
    return ["SUPER_ADMIN", "TREASURY"]


def default_mfa_platform_roles():
    return ["OWNER", "SECURITY"]


class SiteSettings(models.Model):
    """Singleton platform configuration (site owner)."""

    singleton_id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField(max_length=120, default="ChurchHub")
    site_tagline = models.CharField(max_length=200, blank=True, default="Enterprise Church Management")
    login_highlights = models.TextField(
        blank=True,
        default=(
            "Role-based access & audit trails\n"
            "Conference → church hierarchy\n"
            "Financial integrity & reporting"
        ),
        help_text="Login page highlights — one per line. Leave blank to hide the list.",
    )
    support_email = models.EmailField(blank=True, default="support@churchhub.local")
    admin_primary_color = models.CharField(
        max_length=7,
        default="#1e3a5f",
        help_text="Brand/chrome color (navbar, table headers). Navy recommended.",
    )
    accent_color = models.CharField(
        max_length=7,
        default="#1d4ed8",
        help_text="Action color for primary buttons and links.",
    )
    highlight_color = models.CharField(
        max_length=7,
        default="#0e7490",
        help_text="Secondary accent (KPI highlights, portal accents).",
    )
    logo = models.ImageField(upload_to="platform/branding/", blank=True, null=True)
    favicon = models.ImageField(upload_to="platform/branding/", blank=True, null=True)
    footer_text = models.CharField(max_length=200, blank=True, default="Enterprise Church Management")
    session_timeout_minutes = models.PositiveIntegerField(
        default=240,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text="Idle session length before re-login is required.",
    )
    login_max_attempts = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(20)],
    )
    login_lockout_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    mfa_required_for_privileged = models.BooleanField(
        default=True,
        help_text=(
            "When enabled, require MFA (TOTP / email OTP / recovery) for the audiences "
            "selected below. Recommended for production — treasury and platform roles."
        ),
        verbose_name="Require MFA for selected audiences",
    )
    mfa_institution_roles = models.JSONField(
        default=default_mfa_institution_roles,
        blank=True,
        help_text=(
            "Institution User.role codes that must use MFA when enforcement is on. "
            "Recommended starter set: SUPER_ADMIN, TREASURY."
        ),
    )
    mfa_platform_roles = models.JSONField(
        default=default_mfa_platform_roles,
        blank=True,
        help_text=(
            "Platform operator roles that must use MFA when enforcement is on. "
            "Recommended starter set: OWNER, SECURITY."
        ),
    )
    mfa_include_django_superusers = models.BooleanField(
        default=True,
        help_text="When MFA enforcement is on, also require MFA for Django superusers.",
    )
    maintenance_mode = models.BooleanField(
        default=False,
        help_text="When enabled, only platform operators may sign in.",
    )
    maintenance_block_apply = models.BooleanField(
        default=True,
        help_text="When maintenance mode is on, also block public /apply/ registration.",
    )
    maintenance_message = models.CharField(
        max_length=300,
        blank=True,
        default="The system is undergoing scheduled maintenance. Please try again later.",
    )
    platform_ip_allowlist = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Optional. Newline-separated public IPs allowed for /platform/. "
            "Empty = allow any IP (recommended when using MFA on a dynamic home ISP). "
            "Do not list residential IPs that change daily — use a static/VPN IP later if needed."
        ),
    )
    allow_church_self_registration = models.BooleanField(
        default=False,
        help_text="Allow public church registration applications at /apply/.",
    )
    allow_institution_user_invites = models.BooleanField(
        default=True,
        help_text="Allow church admins to invite institution users.",
    )
    allow_institution_church_onboarding = models.BooleanField(
        default=True,
        help_text="Allow hierarchy admins to onboard churches from the institution app.",
    )
    registration_intro = models.TextField(
        blank=True,
        default="Apply to register your church on ChurchHub. A platform administrator will review your request.",
    )
    application_default_plan = models.ForeignKey(
        "SubscriptionPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Plan assigned when an application is approved (default plan if empty).",
    )
    application_default_role = models.CharField(
        max_length=30,
        default="LOCAL_PASTOR",
        help_text="Role for the first user invited when an application is approved.",
    )
    enforce_subscription_limits = models.BooleanField(
        default=True,
        help_text="Apply plan user/branch limits and feature flags.",
    )
    smtp_host = models.CharField(max_length=200, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=200, blank=True)
    smtp_password = models.CharField(
        max_length=200,
        blank=True,
        help_text="Plaintext SMTP password (legacy). Prefer smtp_password_encrypted when available.",
    )
    smtp_password_encrypted = models.TextField(
        blank=True,
        default="",
        help_text="Optional encrypted SMTP password storage (Phase 2).",
    )
    smtp_use_tls = models.BooleanField(default=True)
    default_from_email = models.EmailField(blank=True)
    password_min_length = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(6), MaxValueValidator(128)],
    )
    password_require_uppercase = models.BooleanField(default=False)
    platform_banner_enabled = models.BooleanField(default=False)
    platform_banner_message = models.CharField(max_length=500, blank=True)
    global_enable_payroll = models.BooleanField(default=True)
    global_enable_remittance = models.BooleanField(default=True)
    global_enable_ledger = models.BooleanField(default=True)
    global_enable_meetings = models.BooleanField(default=True)
    global_enable_giving = models.BooleanField(default=True)
    global_enable_budgets = models.BooleanField(default=True)
    global_enable_advanced_reports = models.BooleanField(default=True)
    global_enable_assets = models.BooleanField(default=True)
    global_enable_contributions = models.BooleanField(default=True)
    default_billing_currency = models.CharField(max_length=3, default="GHS")
    billing_payment_instructions = models.TextField(
        blank=True,
        default="",
        help_text="Default payment instructions shown during tenant provisioning and billing.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        super().save(*args, **kwargs)
        try:
            from sitecontrol.services import clear_settings_cache

            clear_settings_cache()
        except Exception:
            pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.site_name


class SubscriptionPlan(models.Model):
    """Feature pack and limits sold to a church tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Annual price (optional). Leave blank to derive from monthly × 12.",
    )
    currency = models.CharField(max_length=3, default="GHS")
    trial_days = models.PositiveSmallIntegerField(
        default=14,
        help_text="Default trial length when this plan is assigned as TRIAL.",
    )
    setup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_users = models.PositiveIntegerField(default=10, help_text="Max active users per church.")
    max_branches = models.PositiveIntegerField(
        default=1,
        help_text="Max churches/branches under one district subscription anchor.",
    )
    feature_payroll = models.BooleanField(default=False)
    feature_remittance = models.BooleanField(default=True)
    feature_ledger = models.BooleanField(default=True)
    feature_meetings = models.BooleanField(default=True)
    feature_advanced_reports = models.BooleanField(default=False)
    feature_budgets = models.BooleanField(default=True)
    feature_giving_portal = models.BooleanField(default=True)
    feature_assets = models.BooleanField(default=True)
    feature_contribution_campaigns = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def effective_yearly_price(self):
        if self.price_yearly is not None:
            return self.price_yearly
        return self.price_monthly * 12

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            SubscriptionPlan.objects.exclude(pk=self.pk).update(is_default=False)


class PlatformPaymentMethod(models.Model):
    """Payment methods platform owners offer for subscription billing."""

    METHOD_TYPES = [
        ("BANK_TRANSFER", "Bank Transfer"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("CARD", "Card / Online Gateway"),
        ("CASH", "Cash / Cheque"),
        ("INVOICE", "Invoice / Purchase Order"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES, default="BANK_TRANSFER")
    instructions = models.TextField(
        blank=True,
        help_text="Bank details, mobile money number, or payment instructions shown to operators.",
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            PlatformPaymentMethod.objects.exclude(pk=self.pk).update(is_default=False)


class TenantSubscription(models.Model):
    """Links a church to a subscription plan."""

    STATUS_CHOICES = [
        ("TRIAL", "Trial"),
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
        ("EXPIRED", "Expired"),
    ]
    BILLING_INTERVALS = [
        ("MONTHLY", "Monthly"),
        ("YEARLY", "Yearly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.OneToOneField(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ACTIVE")
    billing_interval = models.CharField(
        max_length=10,
        choices=BILLING_INTERVALS,
        default="MONTHLY",
    )
    payment_method = models.ForeignKey(
        PlatformPaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    payment_reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="Bank transfer reference, receipt number, or gateway transaction ID.",
    )
    price_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Locked plan pricing at assignment time.",
    )
    last_payment_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateField(null=True, blank=True)
    started_at = models.DateField(default=timezone.now)
    expires_at = models.DateField(null=True, blank=True)
    override_max_users = models.PositiveIntegerField(null=True, blank=True)
    override_max_branches = models.PositiveIntegerField(null=True, blank=True)
    feature_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text='Per-feature overrides of the plan, e.g. {"payroll": true}.',
    )
    notes = models.TextField(blank=True)
    lifecycle_notes = models.TextField(blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions_suspended",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.church.name} — {self.plan.name} ({self.status})"

    @property
    def is_operational(self):
        if self.status in ("SUSPENDED", "EXPIRED"):
            return False
        if self.expires_at and self.expires_at < timezone.now().date():
            return False
        return True

    def effective_max_users(self):
        if self.override_max_users is not None:
            return self.override_max_users
        return self.plan.max_users

    def effective_max_branches(self):
        if self.override_max_branches is not None:
            return self.override_max_branches
        return self.plan.max_branches


class PlatformAuditLog(models.Model):
    """Immutable audit trail for platform control room actions."""

    ACTION_CHOICES = [
        ("SETTINGS_UPDATE", "Settings Updated"),
        ("PLAN_UPDATE", "Plan Updated"),
        ("SUBSCRIPTION_UPDATE", "Subscription Updated"),
        ("SUBSCRIPTION_PAYMENT", "Subscription Payment Recorded"),
        ("TENANT_UPDATE", "Tenant Updated"),
        ("TENANT_SUSPEND", "Tenant Suspended"),
        ("TENANT_REACTIVATE", "Tenant Reactivated"),
        ("TENANT_OFFBOARD", "Tenant Offboarded"),
        ("OPERATOR_CREATE", "Platform Operator Created"),
        ("OPERATOR_UPDATE", "Platform Operator Updated"),
        ("OPERATOR_DEACTIVATE", "Platform Operator Deactivated"),
        ("ANNOUNCEMENT_UPDATE", "Announcement Updated"),
        ("FEATURE_UPDATE", "Feature Registry Updated"),
        ("MAINTENANCE_TOGGLE", "Maintenance Mode Toggled"),
        ("REGISTRATION_UPDATE", "Registration Settings Updated"),
        ("APPLICATION_SUBMIT", "Tenant Application Submitted"),
        ("APPLICATION_APPROVE", "Tenant Application Approved"),
        ("APPLICATION_REJECT", "Tenant Application Rejected"),
        ("TENANT_PROVISION", "Tenant Provisioned"),
        ("TENANT_REPROVISION", "Tenant Financials Re-provisioned"),
        ("PAYMENT_METHOD_UPDATE", "Payment Method Updated"),
        ("SUBSCRIPTIONS_EXPIRED", "Subscriptions Expired (batch)"),
        ("DENOMINATION_CREATE", "Denomination Created"),
        ("DENOMINATION_UPDATE", "Denomination Updated"),
        ("DENOMINATION_SEED", "Denomination Profiles Seeded"),
        ("DENOMINATION_TERMINOLOGY", "Denomination Terminology Updated"),
        ("DENOMINATION_SEEDS_CONFIG", "Denomination Seed Config Updated"),
        ("DENOMINATION_BILLING_VIEW", "Denomination Billing Viewed"),
        ("DENOMINATION_PURGE", "Denomination Permanently Deleted"),
        ("AUDIT_EXPORT", "Audit Log Exported"),
        ("OPS_EMAIL_TEST", "Ops Email Test Sent"),
        ("IMPERSONATE_START", "Impersonation Started"),
        ("IMPERSONATE_END", "Impersonation Ended"),
        ("BREAKGLASS_GRANT", "Break-glass Access Granted"),
        ("MEMBER_IMPORT", "Member Bulk Import"),
        ("TRANSACTION_IMPORT", "Receipt Bulk Import"),
        ("MARKETING_SETTINGS", "Marketing Settings Updated"),
        ("MARKETING_CAMPAIGN_CREATE", "Marketing Campaign Created"),
        ("MARKETING_CAMPAIGN_UPDATE", "Marketing Campaign Updated"),
        ("MARKETING_CAMPAIGN_ARCHIVE", "Marketing Campaign Archived"),
        ("MARKETING_LEAD_SUBMIT", "Marketing Lead Submitted"),
        ("MARKETING_LEAD_UPDATE", "Marketing Lead Updated"),
        ("MARKETING_ASSET_CREATE", "Marketing Asset Created"),
        ("MARKETING_ASSET_UPDATE", "Marketing Asset Updated"),
        ("MARKETING_ASSET_ARCHIVE", "Marketing Asset Archived"),
        ("MARKETING_LEAD_NOTIFY", "Marketing Lead Notification Updated"),
        ("MARKETING_LEAD_EXPORT", "Marketing Leads Exported"),
        ("MARKETING_LEAD_ANONYMIZE", "Marketing Lead Anonymized"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="platform_audit_logs",
    )
    denomination = models.ForeignKey(
        "Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    target_model = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=300)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.summary}"

    def save(self, *args, **kwargs):
        if self.pk and PlatformAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("PlatformAuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("PlatformAuditLog entries cannot be deleted.")


class PlatformAnnouncement(models.Model):
    """Platform-wide banner shown to institution users."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    show_on_login = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_announcements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_current(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class MarketingSettings(models.Model):
    """Singleton settings for public marketing inquiry intake."""

    singleton_id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    public_inquiry_enabled = models.BooleanField(
        default=False,
        help_text="Enable only after sales email, consent, and privacy settings are reviewed.",
    )
    sales_notification_email = models.EmailField(blank=True)
    marketing_site_url = models.URLField(blank=True)
    privacy_policy_url = models.URLField(blank=True)
    consent_text = models.TextField(
        default=(
            "I agree that ChurchHub may use these details to respond to my inquiry. "
            "I can request deletion by contacting the platform."
        )
    )
    notify_on_new_lead = models.BooleanField(default=True)
    lead_retention_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(30), MaxValueValidator(2555)],
        help_text="Closed leads older than this may be anonymized (30–2555 days).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "marketing settings"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Marketing settings"


class MarketingCampaign(models.Model):
    """Owner-managed attribution campaign for public inquiries."""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("ACTIVE", "Active"),
        ("ARCHIVED", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")
    source = models.CharField(max_length=80, blank=True)
    medium = models.CharField(max_length=80, blank=True)
    campaign_tag = models.CharField(max_length=100, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_campaigns_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return self.name

    @property
    def is_live(self):
        if self.status != "ACTIVE":
            return False
        now = timezone.now()
        return not ((self.starts_at and now < self.starts_at) or (self.ends_at and now > self.ends_at))


class MarketingLead(models.Model):
    """A consented platform-level sales inquiry; never church operational data."""

    STATUS_CHOICES = [
        ("NEW", "New"),
        ("CONTACTED", "Contacted"),
        ("QUALIFIED", "Qualified"),
        ("CONVERTED", "Converted"),
        ("CLOSED", "Closed"),
    ]
    NOTIFICATION_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
        ("DISABLED", "Disabled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="NEW")
    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True)
    organization_name = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    denomination = models.ForeignKey(
        "Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_leads",
    )
    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    utm_source = models.CharField(max_length=80, blank=True)
    utm_medium = models.CharField(max_length=80, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    consent_given = models.BooleanField(default=False)
    consent_text = models.TextField()
    consented_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_leads_assigned",
    )
    internal_notes = models.TextField(blank=True)
    notification_status = models.CharField(
        max_length=10,
        choices=NOTIFICATION_STATUS_CHOICES,
        default="DISABLED",
    )
    notification_attempts = models.PositiveSmallIntegerField(default=0)
    notification_error_code = models.CharField(max_length=80, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    anonymized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_leads_anonymized",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["contact_email"]),
            models.Index(fields=["campaign", "-created_at"]),
            models.Index(fields=["denomination", "status"]),
        ]

    def __str__(self):
        return f"{self.contact_name} ({self.get_status_display()})"


class MarketingAsset(models.Model):
    """Approved link to collateral hosted on the owner's public website."""

    TYPE_CHOICES = [
        ("BROCHURE", "Brochure"),
        ("PRESENTATION", "Presentation"),
        ("VIDEO", "Video"),
        ("SCREENSHOT", "Screenshot"),
        ("DATASHEET", "Datasheet"),
        ("OTHER", "Other"),
    ]
    STATUS_CHOICES = [
        ("INTERNAL", "Internal"),
        ("REVIEW", "Review Required"),
        ("APPROVED", "Approved for External Use"),
        ("ARCHIVED", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    asset_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="OTHER")
    audience = models.CharField(max_length=120, blank=True)
    public_url = models.URLField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="REVIEW")
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_assets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]
        indexes = [
            models.Index(fields=["status", "sort_order"]),
        ]

    def __str__(self):
        return self.title


class TenantApplication(models.Model):
    """Public church registration request — reviewed by platform owner."""

    STATUS_CHOICES = [
        ("PENDING", "Pending Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("WITHDRAWN", "Withdrawn"),
    ]
    TYPE_CHOICES = [
        ("EXISTING_DISTRICT", "Existing district"),
        ("NEW_HIERARCHY", "New organization path"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PENDING")
    application_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="EXISTING_DISTRICT")

    church_name = models.CharField(max_length=200)
    church_code = models.CharField(max_length=20)
    address = models.TextField(blank=True)

    district = models.ForeignKey(
        "organization.District",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_applications",
    )
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tenant_applications",
    )
    conference_name = models.CharField(max_length=200, blank=True)
    conference_code = models.CharField(max_length=20, blank=True)
    zone_name = models.CharField(max_length=200, blank=True)
    zone_code = models.CharField(max_length=20, blank=True)
    district_name = models.CharField(max_length=200, blank=True)
    district_code = models.CharField(max_length=20, blank=True)

    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    applicant_username = models.CharField(max_length=150)
    applicant_notes = models.TextField(blank=True)

    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_applications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_application",
    )
    invitation = models.ForeignKey(
        "accounts.UserInvitation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_application",
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["contact_email"]),
        ]

    def __str__(self):
        return f"{self.church_name} ({self.get_status_display()})"

    @property
    def is_pending(self):
        return self.status == "PENDING"


class Denomination(models.Model):
    """
    Top-level SaaS tenant boundary — isolates org trees, branding, and seeds.
    All conferences (and churches beneath them) belong to exactly one denomination.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=120, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Fallback denomination for legacy data and ambiguous context.",
    )
    logo = models.ImageField(upload_to="denominations/branding/", blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#1e3a5f")
    accent_color = models.CharField(max_length=7, default="#1d4ed8")
    highlight_color = models.CharField(max_length=7, default="#0e7490")
    hierarchy_labels = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-level enabled flag and display labels for UI terminology.",
    )
    seed_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Default offering categories, remittance, and payroll seeds for new churches.",
    )
    allow_public_registration = models.BooleanField(
        default=True,
        help_text="Allow /apply/ registrations scoped to this denomination.",
    )
    allow_institution_branding = models.BooleanField(
        default=True,
        help_text="Allow institution Super Admins to update logo and brand colors.",
    )
    registration_intro = models.TextField(blank=True)
    default_plan = models.ForeignKey(
        "SubscriptionPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="denominations_default",
    )
    default_role = models.CharField(max_length=30, default="LOCAL_PASTOR")
    feature_payroll = models.BooleanField(default=True)
    feature_remittance = models.BooleanField(default=True)
    feature_ledger = models.BooleanField(default=True)
    feature_meetings = models.BooleanField(default=True)
    feature_advanced_reports = models.BooleanField(default=True)
    feature_budgets = models.BooleanField(default=True)
    feature_giving_portal = models.BooleanField(default=True)
    feature_assets = models.BooleanField(default=True)
    feature_contribution_campaigns = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "code"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name
        super().save(*args, **kwargs)
        if self.is_default:
            Denomination.objects.exclude(pk=self.pk).update(is_default=False)

    @classmethod
    def get_default(cls):
        return cls.objects.filter(is_active=True, is_default=True).first() or cls.objects.filter(is_active=True).first()

    def label(self, level_key, plural=False):
        from sitecontrol.denomination_services import get_level_label

        return get_level_label(self, level_key, plural=plural)

