# Generated manually for reports enterprise upgrade

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportAccessAuditLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("report_key", models.SlugField(max_length=60)),
                (
                    "action",
                    models.CharField(
                        choices=[("RUN", "Run"), ("EXPORT", "Export")],
                        max_length=12,
                    ),
                ),
                ("export_format", models.CharField(blank=True, max_length=10)),
                ("params", models.JSONField(blank=True, default=dict)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "church",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_access_logs",
                        to="organization.church",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_access_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportaccessauditlog",
            index=models.Index(fields=["user", "-created_at"], name="rpt_audit_user_idx"),
        ),
        migrations.AddIndex(
            model_name="reportaccessauditlog",
            index=models.Index(fields=["report_key", "-created_at"], name="rpt_audit_key_idx"),
        ),
    ]
