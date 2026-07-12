# Generated manually for assets enterprise upgrade

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0002_seed_category_templates"),
        ("organization", "0002_generalconference_union_conference_union"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("transactions", "0008_alter_account_account_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="depreciationpolicy",
            name="post_disposal_to_ledger",
            field=models.BooleanField(
                default=True,
                help_text="Write off net book value when an asset is disposed.",
            ),
        ),
        migrations.AddField(
            model_name="fixedasset",
            name="disposal_transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="disposed_assets",
                to="transactions.transaction",
            ),
        ),
        migrations.CreateModel(
            name="AssetPolicyAuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("POLICY_UPDATE", "Policy Updated"),
                            ("CATEGORY_CREATE", "Category Created"),
                            ("CATEGORY_UPDATE", "Category Updated"),
                        ],
                        max_length=40,
                    ),
                ),
                ("target_label", models.CharField(blank=True, max_length=200)),
                ("notes", models.TextField(blank=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "church",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_policy_audit_logs",
                        to="organization.church",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="assetauditlog",
            index=models.Index(
                fields=["asset", "-created_at"],
                name="assets_asse_asset_i_6f2c0d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="assetpolicyauditlog",
            index=models.Index(
                fields=["church", "-created_at"],
                name="assets_asse_church__a8e4b1_idx",
            ),
        ),
    ]
