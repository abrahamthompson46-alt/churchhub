"""Fixed asset register — models."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class AssetCategoryTemplate(models.Model):
    """Platform-wide asset category templates (GRA-aligned defaults)."""

    GRA_CLASSES = [
        ("1", "Class 1 — Buildings & structures"),
        ("2", "Class 2 — Vehicles, plant & heavy equipment"),
        ("3", "Class 3 — IT, office equipment, fixtures"),
        ("4", "Class 4 — Low-value / short-life items"),
    ]
    DEPRECIATION_METHODS = [
        ("STRAIGHT_LINE", "Straight-line"),
        ("DECLINING_BALANCE", "Declining balance (150% DB)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    gra_asset_class = models.CharField(max_length=1, choices=GRA_CLASSES, default="3")
    default_useful_life_months = models.PositiveIntegerField(default=48)
    default_depreciation_method = models.CharField(
        max_length=20,
        choices=DEPRECIATION_METHODS,
        default="STRAIGHT_LINE",
    )
    default_salvage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class AssetCategory(models.Model):
    """Church asset category — from platform template or custom."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="asset_categories",
    )
    template = models.ForeignKey(
        AssetCategoryTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="church_categories",
    )
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    gra_asset_class = models.CharField(max_length=1, choices=AssetCategoryTemplate.GRA_CLASSES, default="3")
    useful_life_months = models.PositiveIntegerField(default=48)
    depreciation_method = models.CharField(
        max_length=20,
        choices=AssetCategoryTemplate.DEPRECIATION_METHODS,
        default="STRAIGHT_LINE",
    )
    salvage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
    )
    is_active = models.BooleanField(default=True)
    is_custom = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "code")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.church.code})"


class DepreciationPolicy(models.Model):
    """Per-church depreciation and capitalization options (admin-configurable)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.OneToOneField(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="depreciation_policy",
    )
    allow_straight_line = models.BooleanField(default=True)
    allow_declining_balance = models.BooleanField(default=True)
    default_method = models.CharField(
        max_length=20,
        choices=AssetCategoryTemplate.DEPRECIATION_METHODS,
        default="STRAIGHT_LINE",
    )
    auto_run_monthly = models.BooleanField(
        default=False,
        help_text="Automatically post depreciation on the run day each month.",
    )
    run_day_of_month = models.PositiveSmallIntegerField(
        default=28,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
    )
    post_depreciation_to_ledger = models.BooleanField(default=True)
    post_disposal_to_ledger = models.BooleanField(
        default=True,
        help_text="Write off net book value when an asset is disposed.",
    )
    capitalize_on_approval = models.BooleanField(
        default=True,
        help_text="Post acquisition entry when an asset is approved.",
    )
    default_payment_account_type = models.CharField(
        max_length=10,
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        default="BANK",
    )
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Depreciation policy — {self.church.name}"


class FixedAsset(models.Model):
    """Church fixed asset with approval workflow."""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING_APPROVAL", "Pending Approval"),
        ("ACTIVE", "Active"),
        ("UNDER_REPAIR", "Under Repair"),
        ("DISPOSED", "Disposed"),
        ("REJECTED", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="fixed_assets",
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    asset_code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    gra_asset_class = models.CharField(max_length=1, choices=AssetCategoryTemplate.GRA_CLASSES, default="3")

    purchase_date = models.DateField()
    acquisition_cost = models.DecimalField(max_digits=14, decimal_places=2)
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    useful_life_months = models.PositiveIntegerField(default=48)
    depreciation_method = models.CharField(
        max_length=20,
        choices=AssetCategoryTemplate.DEPRECIATION_METHODS,
        default="STRAIGHT_LINE",
    )

    custodian_member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custodied_assets",
    )
    custodian_name = models.CharField(max_length=120, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=200, blank=True)
    invoice_reference = models.CharField(max_length=120, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets_submitted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets_rejected",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    acquisition_transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capitalized_assets",
    )
    disposal_transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disposed_assets",
    )
    accumulated_depreciation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    disposed_at = models.DateField(null=True, blank=True)
    disposal_notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("church", "asset_code")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "status"]),
            models.Index(fields=["church", "asset_code"]),
        ]

    def __str__(self):
        return f"{self.asset_code} — {self.name}"

    @property
    def net_book_value(self):
        return self.acquisition_cost - self.accumulated_depreciation

    @property
    def depreciable_base(self):
        base = self.acquisition_cost - self.salvage_value
        return base if base > 0 else Decimal("0.00")

    @property
    def is_editable(self):
        return self.status in ("DRAFT", "REJECTED")

    @property
    def pending_approval(self):
        return self.status == "PENDING_APPROVAL"


class AssetDepreciationEntry(models.Model):
    """Monthly depreciation posted for an asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        FixedAsset,
        on_delete=models.CASCADE,
        related_name="depreciation_entries",
    )
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method_used = models.CharField(max_length=20)
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_depreciation_entries",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("asset", "period_year", "period_month")
        ordering = ["-period_year", "-period_month"]


class AssetMaintenanceLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="maintenance_logs")
    service_date = models.DateField(default=timezone.now)
    description = models.TextField()
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vendor = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-service_date"]


class AssetAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=40)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["asset", "-created_at"]),
        ]


class AssetPolicyAuditLog(models.Model):
    """Audit trail for depreciation policy and category configuration changes."""

    ACTION_CHOICES = [
        ("POLICY_UPDATE", "Policy Updated"),
        ("CATEGORY_CREATE", "Category Created"),
        ("CATEGORY_UPDATE", "Category Updated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="asset_policy_audit_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_label = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.church.code}"
