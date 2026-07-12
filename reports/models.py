"""Async report export jobs and access audit trail."""

import uuid

from django.conf import settings
from django.db import models


class ReportExportJob(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_COMPLETE = "COMPLETE"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETE, "Complete"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_export_jobs",
    )
    report_key = models.SlugField(max_length=60)
    export_format = models.CharField(max_length=10)  # csv, excel, pdf
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    export_file = models.FileField(upload_to="exports/reports/", blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.report_key} ({self.export_format}) — {self.status}"

    @property
    def is_ready(self):
        return self.status == self.STATUS_COMPLETE and bool(self.export_file)


class ReportAccessAuditLog(models.Model):
    """Who ran or exported which report (compliance trail)."""

    ACTION_RUN = "RUN"
    ACTION_EXPORT = "EXPORT"

    ACTION_CHOICES = [
        (ACTION_RUN, "Run"),
        (ACTION_EXPORT, "Export"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_access_logs",
    )
    report_key = models.SlugField(max_length=60)
    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
    export_format = models.CharField(max_length=10, blank=True)
    params = models.JSONField(default=dict, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_access_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="rpt_audit_user_idx"),
            models.Index(fields=["report_key", "-created_at"], name="rpt_audit_key_idx"),
        ]

    def __str__(self):
        return f"{self.report_key} {self.action} by {self.user_id}"
