"""Contribution campaigns and per-member gift tracking."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class CampaignStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    ARCHIVED = "ARCHIVED", "Archived"


class ContributionCampaign(models.Model):
    """Time-bound church giving drive (harvest, rent, building, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="contribution_campaigns",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=40)
    purpose = models.TextField(
        blank=True,
        default="",
        help_text="Shown to members on the portal — describe why this drive exists.",
    )
    deadline = models.DateField()
    status = models.CharField(
        max_length=12,
        choices=CampaignStatus.choices,
        default=CampaignStatus.DRAFT,
    )
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional church-wide fundraising goal.",
    )
    default_member_target = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional default pledge/target amount suggested for each member.",
    )
    send_email_reminders = models.BooleanField(
        default=True,
        help_text="Send deadline reminder emails to portal members when SMTP is configured.",
    )
    offering_category = models.ForeignKey(
        "transactions.OfferingCategory",
        on_delete=models.PROTECT,
        related_name="contribution_campaigns",
    )
    portal_visible = models.BooleanField(
        default=True,
        help_text="When open, show this campaign on the member portal.",
    )
    show_church_progress = models.BooleanField(
        default=True,
        help_text="Members may see church-wide totals and progress on the portal.",
    )
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_campaigns_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_campaigns_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-deadline", "name"]
        unique_together = ("church", "code")
        indexes = [
            models.Index(fields=["church", "status"]),
            models.Index(fields=["church", "deadline"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.church.name})"

    def clean(self):
        errors = {}
        if self.offering_category_id and self.church_id:
            if self.offering_category.church_id != self.church_id:
                errors["offering_category"] = "Offering category must belong to this church."
        if self.target_amount is not None and self.target_amount < 0:
            errors["target_amount"] = "Target amount cannot be negative."
        if self.default_member_target is not None and self.default_member_target < 0:
            errors["default_member_target"] = "Member target cannot be negative."
        if errors:
            raise ValidationError(errors)

    @property
    def is_open(self) -> bool:
        return self.status == CampaignStatus.OPEN

    @property
    def days_until_deadline(self) -> int | None:
        if not self.deadline:
            return None
        return (self.deadline - timezone.localdate()).days

    @property
    def is_past_deadline(self) -> bool:
        days = self.days_until_deadline
        return days is not None and days < 0


class MemberContribution(models.Model):
    """Member gift recorded against a contribution campaign."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        ContributionCampaign,
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="campaign_contributions",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    contribution_date = models.DateField(default=timezone.now)
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.PROTECT,
        related_name="member_contributions",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_contributions_recorded",
    )
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contribution_date", "-created_at"]
        indexes = [
            models.Index(fields=["campaign", "member"]),
            models.Index(fields=["campaign", "contribution_date"]),
            models.Index(fields=["member", "contribution_date"]),
        ]

    def __str__(self):
        return f"{self.member.full_name} — {self.campaign.name}"

    def clean(self):
        if self.campaign_id and self.member_id:
            if self.member.church_id != self.campaign.church_id:
                raise ValidationError({"member": "Member must belong to the campaign church."})
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})


class MemberCampaignTarget(models.Model):
    """Optional per-member pledge/target override for a campaign."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        ContributionCampaign,
        on_delete=models.CASCADE,
        related_name="member_targets",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="campaign_targets",
    )
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_campaign_targets_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("campaign", "member")
        indexes = [models.Index(fields=["campaign", "member"])]

    def clean(self):
        if self.campaign_id and self.member_id and self.member.church_id != self.campaign.church_id:
            raise ValidationError({"member": "Member must belong to the campaign church."})
        if self.target_amount is not None and self.target_amount <= 0:
            raise ValidationError({"target_amount": "Target must be greater than zero."})


class CampaignDeadlineReminder(models.Model):
    """Tracks deadline reminders already sent (in-app and/or email)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        ContributionCampaign,
        on_delete=models.CASCADE,
        related_name="deadline_reminders",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaign_deadline_reminders",
    )
    reminder_key = models.CharField(max_length=16)
    notification_sent = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("campaign", "user", "reminder_key")
        indexes = [models.Index(fields=["campaign", "reminder_key"])]

