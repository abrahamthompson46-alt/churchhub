"""Additive maker-checker cases, steps, policy, and bounded delegation."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ApprovalPolicy(models.Model):
    """Per-church step count. Default one checker — does not replace TreasuryApprovalPolicy."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.OneToOneField(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="journal_approval_policy",
    )
    required_steps = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Journal approval policy"
        verbose_name_plural = "Journal approval policies"

    def __str__(self):
        return f"{self.church} ({self.required_steps} step(s))"


class ApprovalCase(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CORRECTION = "CORRECTION_REQUESTED"
    STATUS_ESCALATED = "ESCALATED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CORRECTION, "Correction requested"),
        (STATUS_ESCALATED, "Escalated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="approval_cases",
    )
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_cases",
    )
    transaction = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="approval_case",
    )
    maker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_cases_made",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_OPEN)
    required_steps = models.PositiveSmallIntegerField(default=1)
    current_step = models.PositiveSmallIntegerField(default=1)
    correction_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "status"], name="appr_case_church_st_idx"),
        ]

    def __str__(self):
        return f"Case {self.transaction_id} ({self.status})"


class ApprovalStep(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_SKIPPED = "SKIPPED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    ACTION_APPROVE = "APPROVE"
    ACTION_REJECT = "REJECT"
    ACTION_CORRECT = "CORRECT"
    ACTION_ESCALATE = "ESCALATE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(ApprovalCase, on_delete=models.CASCADE, related_name="steps")
    step_number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    action = models.CharField(max_length=16, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_steps_acted",
    )
    notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["step_number"]
        constraints = [
            models.UniqueConstraint(fields=["case", "step_number"], name="appr_step_case_num_uniq"),
        ]

    def __str__(self):
        return f"Step {self.step_number} of {self.case_id}"


class ApprovalDelegation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grantor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_delegations_granted",
    )
    grantee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_delegations_received",
    )
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="approval_delegations",
    )
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_delegations",
    )
    permission_codename = models.CharField(max_length=64, default="approve_transactions")
    valid_from = models.DateField()
    valid_until = models.DateField()
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["grantee", "church", "is_revoked"], name="appr_del_grantee_idx"),
        ]

    def __str__(self):
        return f"{self.grantor} → {self.grantee} @ {self.church}"


class ApprovalEscalation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(ApprovalCase, on_delete=models.CASCADE, related_name="escalations")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_escalations",
    )
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Escalation {self.case_id}"
