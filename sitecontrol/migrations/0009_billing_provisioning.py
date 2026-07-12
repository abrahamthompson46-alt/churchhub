# Generated manually for billing and provisioning fields

import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0008_control_tower_enterprise"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="billing_payment_instructions",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Default payment instructions shown during tenant provisioning and billing.",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="default_billing_currency",
            field=models.CharField(default="GHS", max_length=3),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="currency",
            field=models.CharField(default="GHS", max_length=3),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="price_yearly",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Annual price (optional). Leave blank to derive from monthly × 12.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="setup_fee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="trial_days",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="Default trial length when this plan is assigned as TRIAL.",
            ),
        ),
        migrations.CreateModel(
            name="PlatformPaymentMethod",
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
                ("name", models.CharField(max_length=120)),
                (
                    "method_type",
                    models.CharField(
                        choices=[
                            ("BANK_TRANSFER", "Bank Transfer"),
                            ("MOBILE_MONEY", "Mobile Money"),
                            ("CARD", "Card / Online Gateway"),
                            ("CASH", "Cash / Cheque"),
                            ("INVOICE", "Invoice / Purchase Order"),
                        ],
                        default="BANK_TRANSFER",
                        max_length=20,
                    ),
                ),
                (
                    "instructions",
                    models.TextField(
                        blank=True,
                        help_text="Bank details, mobile money number, or payment instructions shown to operators.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="billing_interval",
            field=models.CharField(
                choices=[("MONTHLY", "Monthly"), ("YEARLY", "Yearly")],
                default="MONTHLY",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="last_payment_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="next_billing_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="payment_reference",
            field=models.CharField(
                blank=True,
                help_text="Bank transfer reference, receipt number, or gateway transaction ID.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="price_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Locked plan pricing at assignment time.",
            ),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="payment_method",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subscriptions",
                to="sitecontrol.platformpaymentmethod",
            ),
        ),
        migrations.AlterField(
            model_name="platformauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("SETTINGS_UPDATE", "Site Settings Updated"),
                    ("PLAN_UPDATE", "Subscription Plan Updated"),
                    ("SUBSCRIPTION_UPDATE", "Tenant Subscription Updated"),
                    ("FEATURE_UPDATE", "Feature Registry Updated"),
                    ("TENANT_SUSPEND", "Tenant Suspended"),
                    ("TENANT_REACTIVATE", "Tenant Reactivated"),
                    ("TENANT_OFFBOARD", "Tenant Offboarded"),
                    ("TENANT_UPDATE", "Tenant Updated"),
                    ("OPERATOR_CREATE", "Platform Operator Created"),
                    ("OPERATOR_UPDATE", "Platform Operator Updated"),
                    ("OPERATOR_DEACTIVATE", "Platform Operator Deactivated"),
                    ("ANNOUNCEMENT_UPDATE", "Announcement Updated"),
                    ("REGISTRATION_UPDATE", "Registration Settings Updated"),
                    ("APPLICATION_SUBMIT", "Tenant Application Submitted"),
                    ("APPLICATION_APPROVE", "Tenant Application Approved"),
                    ("APPLICATION_REJECT", "Tenant Application Rejected"),
                    ("TENANT_PROVISION", "Tenant Provisioned"),
                    ("TENANT_REPROVISION", "Tenant Financials Re-provisioned"),
                    ("PAYMENT_METHOD_UPDATE", "Payment Method Updated"),
                    ("SUBSCRIPTIONS_EXPIRED", "Subscriptions Expired (batch)"),
                    ("DENOMINATION_UPDATE", "Denomination Updated"),
                    ("DENOMINATION_SEED", "Denomination Seeds Updated"),
                    ("IMPERSONATE_START", "Impersonation Started"),
                    ("IMPERSONATE_END", "Impersonation Ended"),
                    ("AUDIT_EXPORT", "Audit Log Exported"),
                    ("OPS_EMAIL_TEST", "Operations Email Test"),
                ],
                max_length=40,
            ),
        ),
    ]
