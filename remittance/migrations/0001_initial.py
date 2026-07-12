# Generated manually for remittance policy engine

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organization", "0002_generalconference_union_conference_union"),
        ("transactions", "0005_remittance_accounts_and_fund"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("members", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RemittancePolicy",
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
                    "offering_type",
                    models.CharField(
                        choices=[
                            ("TITHE", "Tithe"),
                            ("COMBINED", "Combined Offering"),
                            ("WELFARE", "Welfare"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "application_scope",
                    models.CharField(
                        choices=[
                            ("GROSS_COLLECTION", "Gross Collection"),
                            ("SETTLEMENT_FROM_BELOW", "Settlement from Below"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "unit_type",
                    models.CharField(
                        choices=[
                            ("CHURCH", "Church"),
                            ("DISTRICT", "District"),
                            ("CONFERENCE", "Conference"),
                            ("UNION", "Union"),
                            ("GENERAL_CONFERENCE", "General Conference"),
                        ],
                        max_length=30,
                    ),
                ),
                ("unit_id", models.UUIDField(db_index=True)),
                ("retain_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("remit_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("effective_from", models.DateField(default=django.utils.timezone.now)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="remittance_policies_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "remittance policies",
                "ordering": ["unit_type", "offering_type", "-effective_from"],
            },
        ),
        migrations.CreateModel(
            name="RemittancePolicyAuditLog",
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
                            ("CREATE", "Created"),
                            ("UPDATE", "Updated"),
                            ("DEACTIVATE", "Deactivated"),
                        ],
                        max_length=20,
                    ),
                ),
                ("snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="remittance.remittancepolicy",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SettlementBatch",
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
                    "offering_type",
                    models.CharField(
                        choices=[
                            ("TITHE", "Tithe"),
                            ("COMBINED", "Combined Offering"),
                            ("WELFARE", "Welfare"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "from_unit_type",
                    models.CharField(
                        choices=[
                            ("CHURCH", "Church"),
                            ("DISTRICT", "District"),
                            ("CONFERENCE", "Conference"),
                            ("UNION", "Union"),
                            ("GENERAL_CONFERENCE", "General Conference"),
                        ],
                        max_length=30,
                    ),
                ),
                ("from_unit_id", models.UUIDField()),
                (
                    "to_unit_type",
                    models.CharField(
                        choices=[
                            ("CHURCH", "Church"),
                            ("DISTRICT", "District"),
                            ("CONFERENCE", "Conference"),
                            ("UNION", "Union"),
                            ("GENERAL_CONFERENCE", "General Conference"),
                        ],
                        max_length=30,
                    ),
                ),
                ("to_unit_id", models.UUIDField()),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                (
                    "gross_received",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "retain_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "remit_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("POSTED", "Posted"),
                            ("VOID", "Void"),
                        ],
                        default="DRAFT",
                        max_length=10,
                    ),
                ),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-period_end", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SettlementLine",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("notes", models.CharField(blank=True, max_length=200)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="remittance.settlementbatch",
                    ),
                ),
                (
                    "source_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="transactions.transaction",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="WelfareContribution",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("contribution_date", models.DateField(default=django.utils.timezone.now)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "church",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="welfare_contributions",
                        to="organization.church",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="welfare_contributions",
                        to="members.member",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="welfare_contributions",
                        to="transactions.transaction",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="WelfareAssistanceCase",
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
                ("amount_requested", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "amount_approved",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("DISBURSED", "Disbursed"),
                        ],
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("reason", models.TextField()),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="welfare_cases_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "church",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="welfare_cases",
                        to="organization.church",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="welfare_cases_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="welfare_cases",
                        to="members.member",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="remittancepolicy",
            index=models.Index(
                fields=["unit_type", "unit_id", "offering_type", "application_scope"],
                name="remittance__unit_ty_8a0f0d_idx",
            ),
        ),
    ]
