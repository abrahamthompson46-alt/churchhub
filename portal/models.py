"""Portal domain models — member spiritual submissions."""

import uuid

from django.conf import settings
from django.db import models

from organization.models import Church


class SpiritualSubmissionStatus(models.TextChoices):
    NEW = "NEW", "New"
    REVIEWED = "REVIEWED", "Reviewed"
    ARCHIVED = "ARCHIVED", "Archived"


class SpiritualSubmissionKind(models.TextChoices):
    PRAYER = "PRAYER", "Prayer request"
    THANKSGIVING = "THANKSGIVING", "Thanksgiving"
    TESTIMONY = "TESTIMONY", "Testimony"


class SpiritualSubmission(models.Model):
    """Prayer requests and thanksgiving/testimony shared from the member portal."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="spiritual_submissions",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spiritual_submissions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="spiritual_submissions_submitted",
    )
    kind = models.CharField(max_length=20, choices=SpiritualSubmissionKind.choices)
    title = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField()
    is_anonymous = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=SpiritualSubmissionStatus.choices,
        default=SpiritualSubmissionStatus.NEW,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spiritual_submissions_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "kind", "status"], name="portal_spirit_ch_k_st_idx"),
            models.Index(fields=["church", "created_at"], name="portal_spirit_ch_cr_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.church_id}"


class SpiritualSubmissionAuditLog(models.Model):
    """Immutable audit trail for pastoral inbox actions."""

    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        REVIEWED = "REVIEWED", "Reviewed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        SpiritualSubmission,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="spiritual_submission_audits",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk and SpiritualSubmissionAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("SpiritualSubmissionAuditLog entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("SpiritualSubmissionAuditLog entries cannot be deleted.")
