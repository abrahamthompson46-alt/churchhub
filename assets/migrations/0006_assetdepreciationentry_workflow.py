"""Additive depreciation workflow fields on AssetDepreciationEntry.

Existing rows have always represented posted register lines. Defaults keep
that interpretation: workflow_status=POSTED, register_applied=True.
posted_at stays populated for historical rows; auto_now_add is removed so
future unapplied rows can remain without a posted timestamp.

No journal backfill by description or amount. No unique constraint on
transaction_id in this migration (duplicate links are not known without a
database-backed preflight).
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("assets", "0005_merge_rc1_and_rename"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetdepreciationentry",
            name="initiated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="depreciation_entries_initiated",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="assetdepreciationentry",
            name="register_applied",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="assetdepreciationentry",
            name="workflow_status",
            field=models.CharField(
                choices=[
                    ("AWAITING_APPROVAL", "Awaiting approval"),
                    ("POSTED", "Posted"),
                    ("REJECTED", "Rejected"),
                    ("FAILED", "Failed"),
                    ("RECOVERY_REQUIRED", "Recovery required"),
                ],
                default="POSTED",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="assetdepreciationentry",
            name="posted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
