"""Church-scoped risk policy and explainable, idempotent alerts."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class RiskPolicy(models.Model):
    """Per-church detection thresholds. Does not replace TreasuryApprovalPolicy."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.OneToOneField(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="risk_policy",
    )
    is_active = models.BooleanField(default=True)
    block_auto_approve_on_high = models.BooleanField(
        default=False,
        help_text="Reserved. Receipt auto-approve is never blocked by this flag.",
    )
    large_multiplier = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("20.00"))
    large_absolute = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"))
    large_min_sample = models.PositiveSmallIntegerField(default=8)
    near_duplicate_minutes = models.PositiveIntegerField(default=15)
    near_duplicate_min_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("100.00")
    )
    repeat_count = models.PositiveSmallIntegerField(default=5)
    repeat_hours = models.PositiveIntegerField(default=24)
    expense_absolute = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("5000.00"))
    reversal_count = models.PositiveSmallIntegerField(default=3)
    reversal_days = models.PositiveIntegerField(default=7)
    velocity_count = models.PositiveSmallIntegerField(default=30)
    velocity_minutes = models.PositiveIntegerField(default=60)
    step_change_ratio = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("3.00"))
    bunching_last_days = models.PositiveSmallIntegerField(default=3)
    bunching_share = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.50"))
    bunching_min_count = models.PositiveSmallIntegerField(default=6)
    baseline_min_sample = models.PositiveSmallIntegerField(default=10)
    baseline_z = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("3.00"))
    lookback_days = models.PositiveIntegerField(default=90)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Financial risk policy"
        verbose_name_plural = "Financial risk policies"

    def __str__(self):
        return f"Risk policy {self.church}"


class RiskAlert(models.Model):
    SEVERITY_LOW = "LOW"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_HIGH = "HIGH"
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, "Low"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_HIGH, "High"),
    ]

    STATUS_OPEN = "OPEN"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_DISMISSED = "DISMISSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="risk_alerts",
    )
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
    )
    approval_case = models.ForeignKey(
        "approvals.ApprovalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
    )
    rule_code = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    fingerprint = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    explanation = models.TextField()
    observed = models.JSONField(default=dict, blank=True)
    threshold = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_risk_alerts",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "rule_code", "fingerprint"],
                name="intelligence_alert_idempotent",
            ),
        ]
        indexes = [
            models.Index(fields=["church", "status", "severity"]),
            models.Index(fields=["church", "rule_code"]),
        ]

    def __str__(self):
        return f"{self.rule_code} {self.severity} ({self.church})"
