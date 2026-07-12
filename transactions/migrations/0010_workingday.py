# Generated migration for WorkingDay model

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0003_conference_denomination"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("transactions", "0009_financialidempotencykey"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkingDay",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("date", models.DateField(help_text="Business date for receipts, offerings, and expenses.")),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("CLOSED", "Closed")], default="OPEN", max_length=8)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "church",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="working_days",
                        to="organization.church",
                    ),
                ),
                (
                    "closed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="working_days_closed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "opened_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="working_days_opened",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
        migrations.AddIndex(
            model_name="workingday",
            index=models.Index(fields=["church", "status"], name="transaction_church__a8f4c2_idx"),
        ),
        migrations.AddIndex(
            model_name="workingday",
            index=models.Index(fields=["church", "-date"], name="transaction_church__b1e9d3_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="workingday",
            unique_together={("church", "date")},
        ),
    ]
