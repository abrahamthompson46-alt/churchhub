import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class RemittancePolicy(models.Model):
    """Configurable retain/remit percentages per financial unit and offering type."""

    OFFERING_TYPES = [
        ("TITHE", "Tithe"),
        ("COMBINED", "Combined Offering"),
        ("WELFARE", "Welfare"),
    ]

    APPLICATION_SCOPES = [
        ("GROSS_COLLECTION", "Gross Collection"),
        ("SETTLEMENT_FROM_BELOW", "Settlement from Below"),
    ]

    UNIT_TYPES = [
        ("CHURCH", "Church"),
        ("DISTRICT", "District"),
        ("CONFERENCE", "Conference"),
        ("UNION", "Union"),
        ("GENERAL_CONFERENCE", "General Conference"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offering_type = models.CharField(max_length=20, choices=OFFERING_TYPES)
    application_scope = models.CharField(max_length=30, choices=APPLICATION_SCOPES)
    unit_type = models.CharField(max_length=30, choices=UNIT_TYPES)
    unit_id = models.UUIDField(db_index=True)

    retain_percent = models.DecimalField(max_digits=5, decimal_places=2)
    remit_percent = models.DecimalField(max_digits=5, decimal_places=2)

    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remittance_policies_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "remittance policies"
        ordering = ["unit_type", "offering_type", "-effective_from"]
        indexes = [
            models.Index(fields=["unit_type", "unit_id", "offering_type", "application_scope"]),
        ]

    def __str__(self):
        return (
            f"{self.get_unit_type_display()} {self.get_offering_type_display()} "
            f"({self.retain_percent}% retain / {self.remit_percent}% remit)"
        )

    def clean(self):
        total = self.retain_percent + self.remit_percent
        if total != 100:
            raise ValidationError("Retain and remit percentages must sum to 100.")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("Effective end date must be on or after the start date.")


class RemittancePolicyAuditLog(models.Model):
    ACTIONS = [
        ("CREATE", "Created"),
        ("UPDATE", "Updated"),
        ("DEACTIVATE", "Deactivated"),
        ("SCOPE_VIOLATION", "Scope violation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(
        RemittancePolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTIONS)
    snapshot = models.JSONField(default=dict)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class SettlementBatch(models.Model):
    """Monthly settlement between hierarchy levels (Option B)."""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("POSTED", "Posted"),
        ("VOID", "Void"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offering_type = models.CharField(max_length=20, choices=RemittancePolicy.OFFERING_TYPES)
    from_unit_type = models.CharField(max_length=30, choices=RemittancePolicy.UNIT_TYPES)
    from_unit_id = models.UUIDField()
    to_unit_type = models.CharField(max_length=30, choices=RemittancePolicy.UNIT_TYPES)
    to_unit_id = models.UUIDField()

    period_start = models.DateField()
    period_end = models.DateField()
    gross_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    retain_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "from_unit_type",
                    "from_unit_id",
                    "offering_type",
                    "period_start",
                    "period_end",
                ],
                condition=models.Q(status__in=["DRAFT", "POSTED"]),
                name="uniq_settlement_active_period_obligation",
            ),
        ]


class SettlementLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(SettlementBatch, on_delete=models.CASCADE, related_name="lines")
    source_transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.CharField(max_length=200, blank=True)


class WelfareContribution(models.Model):
    """Per-member welfare pool contribution at church level."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="welfare_contributions",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_contributions",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_contributions",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    contribution_date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=200, blank=True)
    is_anonymous = models.BooleanField(
        default=False,
        help_text="Contribution recorded without a named member.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contribution_date", "-created_at"]
        indexes = [
            models.Index(fields=["church", "contribution_date"]),
            models.Index(fields=["member", "contribution_date"]),
        ]


class WelfareAssistanceCase(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("UNDER_REVIEW", "Under Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("DISBURSED", "Disbursed"),
        ("CANCELLED", "Cancelled"),
    ]

    ASSISTANCE_TYPES = [
        ("MEDICAL", "Medical"),
        ("BEREAVEMENT", "Bereavement"),
        ("EDUCATION", "Education"),
        ("EMERGENCY", "Emergency"),
        ("OTHER", "Other"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("NORMAL", "Normal"),
        ("HIGH", "High"),
        ("URGENT", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="welfare_cases",
    )
    case_number = models.CharField(max_length=24, blank=True, db_index=True)
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="welfare_cases",
    )
    assistance_type = models.CharField(
        max_length=20,
        choices=ASSISTANCE_TYPES,
        default="OTHER",
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="NORMAL",
    )
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    amount_approved = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default="PENDING")
    reason = models.TextField()
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_cases_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_cases_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    disbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_cases_disbursed",
    )
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disbursement_transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_assistance_cases",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_cases_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "case_number"],
                name="remittance_welfare_case_number_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["church", "status"]),
            models.Index(fields=["member", "status"]),
        ]

    def __str__(self):
        return f"{self.case_number or self.pk} — {self.member}"


class WelfareCaseAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        WelfareAssistanceCase,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    label = models.CharField(max_length=120, blank=True)
    file = models.FileField(upload_to="welfare/cases/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def clean(self):
        from django.core.exceptions import ValidationError
        from church_system.uploads import validate_upload

        super().clean()
        if not self.file:
            return
        try:
            validate_upload(self.file, kind="document")
        except ValidationError as exc:
            raise ValidationError({"file": exc.messages}) from exc

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WelfareMemberLedger(models.Model):
    """Authoritative per-member welfare activity ledger."""

    ENTRY_TYPES = [
        ("CONTRIBUTION", "Contribution"),
        ("REQUEST", "Assistance Request"),
        ("DISBURSEMENT", "Disbursement"),
        ("ADJUSTMENT", "Adjustment"),
    ]

    DIRECTIONS = [
        ("IN", "In"),
        ("OUT", "Out"),
        ("NEUTRAL", "Neutral"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="welfare_ledger_entries",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="welfare_ledger_entries",
    )
    entry_type = models.CharField(max_length=16, choices=ENTRY_TYPES)
    direction = models.CharField(max_length=8, choices=DIRECTIONS, default="NEUTRAL")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    entry_date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=40, blank=True)
    contribution = models.ForeignKey(
        WelfareContribution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    case = models.ForeignKey(
        WelfareAssistanceCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_ledger_entries",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welfare_ledger_entries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        indexes = [
            models.Index(fields=["church", "member", "entry_date"]),
            models.Index(fields=["member", "entry_type"]),
        ]
