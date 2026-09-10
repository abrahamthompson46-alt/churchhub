"""Enterprise append-only audit events (dual-write alongside domain logs)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Immutable tenant-scoped audit event. Do not update or delete rows."""

    DOMAIN_FINANCE = "finance"
    DOMAIN_CHOICES = [
        (DOMAIN_FINANCE, "Finance"),
        ("members", "Members"),
        ("payroll", "Payroll"),
        ("organization", "Organization"),
        ("permissions", "Permissions"),
        ("platform", "Platform"),
        ("other", "Other"),
    ]

    OUTCOME_SUCCESS = "success"
    OUTCOME_DENIED = "denied"
    OUTCOME_ERROR = "error"
    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS, "Success"),
        (OUTCOME_DENIED, "Denied"),
        (OUTCOME_ERROR, "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    business_date = models.DateField(null=True, blank=True)
    domain = models.CharField(max_length=32, choices=DOMAIN_CHOICES, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES, default=OUTCOME_SUCCESS)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enterprise_audit_events",
    )
    actor_role = models.CharField(max_length=30, blank=True)

    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enterprise_audit_events",
    )
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enterprise_audit_events",
    )

    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_label = models.CharField(max_length=200, blank=True)

    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    source = models.CharField(max_length=64, blank=True)
    source_id = models.CharField(max_length=64, blank=True)

    prev_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["church", "occurred_at"], name="audit_evt_church_dt_idx"),
            models.Index(fields=["domain", "action", "occurred_at"], name="audit_evt_dom_act_dt_idx"),
            models.Index(fields=["object_type", "object_id"], name="audit_evt_object_idx"),
        ]

    def __str__(self):
        return f"{self.action} @ {self.occurred_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("AuditEvent rows are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditEvent rows cannot be deleted.")
