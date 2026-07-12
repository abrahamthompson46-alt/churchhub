# Generated manually for multi-denomination SaaS

import uuid

from django.db import migrations, models


def seed_denominations(apps, schema_editor):
    Denomination = apps.get_model("sitecontrol", "Denomination")

    sda, _ = Denomination.objects.get_or_create(
        code="sda",
        defaults={
            "name": "Seventh-day Adventist",
            "display_name": "SDA ChurchHub",
            "is_default": True,
            "is_active": True,
        },
    )
    Denomination.objects.exclude(pk=sda.pk).update(is_default=False)

    for spec in (
        ("methodist", "Methodist Church", "Methodist ChurchHub"),
        ("cop", "Church of Pentecost", "CoP ChurchHub"),
        ("generic", "Independent / Other", "ChurchHub"),
    ):
        Denomination.objects.get_or_create(
            code=spec[0],
            defaults={"name": spec[1], "display_name": spec[2], "is_active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0004_sitesettings_global_enable_assets_and_more"),
        ("organization", "0002_generalconference_union_conference_union"),
    ]

    operations = [
        migrations.CreateModel(
            name="Denomination",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=200)),
                ("display_name", models.CharField(blank=True, max_length=120)),
                ("tagline", models.CharField(blank=True, max_length=200)),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False, help_text="Fallback denomination for legacy data and ambiguous context.")),
                ("logo", models.ImageField(blank=True, null=True, upload_to="denominations/branding/")),
                ("primary_color", models.CharField(default="#1e3a5f", max_length=7)),
                ("accent_color", models.CharField(default="#1d4ed8", max_length=7)),
                ("hierarchy_labels", models.JSONField(blank=True, default=dict, help_text="Per-level enabled flag and display labels for UI terminology.")),
                ("seed_config", models.JSONField(blank=True, default=dict, help_text="Default offering categories, remittance, and payroll seeds for new churches.")),
                ("allow_public_registration", models.BooleanField(default=True, help_text="Allow /apply/ registrations scoped to this denomination.")),
                ("registration_intro", models.TextField(blank=True)),
                ("default_role", models.CharField(default="LOCAL_PASTOR", max_length=30)),
                ("feature_payroll", models.BooleanField(default=True)),
                ("feature_remittance", models.BooleanField(default=True)),
                ("feature_ledger", models.BooleanField(default=True)),
                ("feature_meetings", models.BooleanField(default=True)),
                ("feature_advanced_reports", models.BooleanField(default=True)),
                ("feature_budgets", models.BooleanField(default=True)),
                ("feature_giving_portal", models.BooleanField(default=True)),
                ("feature_assets", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "default_plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="denominations_default",
                        to="sitecontrol.subscriptionplan",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="denomination",
            index=models.Index(fields=["is_active", "code"], name="sitecontrol_is_acti_0a8f2a_idx"),
        ),
        migrations.AddField(
            model_name="tenantapplication",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="tenant_applications",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.RunPython(seed_denominations, migrations.RunPython.noop),
    ]
