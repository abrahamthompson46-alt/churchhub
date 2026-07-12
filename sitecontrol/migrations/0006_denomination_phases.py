# Platform audit log denomination FK + extended action choices

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0005_denomination_saas"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformauditlog",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.AlterField(
            model_name="platformauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("SETTINGS_UPDATE", "Settings Updated"),
                    ("PLAN_UPDATE", "Plan Updated"),
                    ("SUBSCRIPTION_UPDATE", "Subscription Updated"),
                    ("TENANT_UPDATE", "Tenant Updated"),
                    ("OPERATOR_CREATE", "Platform Operator Created"),
                    ("OPERATOR_UPDATE", "Platform Operator Updated"),
                    ("OPERATOR_DEACTIVATE", "Platform Operator Deactivated"),
                    ("ANNOUNCEMENT_UPDATE", "Announcement Updated"),
                    ("FEATURE_UPDATE", "Feature Registry Updated"),
                    ("MAINTENANCE_TOGGLE", "Maintenance Mode Toggled"),
                    ("REGISTRATION_UPDATE", "Registration Settings Updated"),
                    ("APPLICATION_SUBMIT", "Tenant Application Submitted"),
                    ("APPLICATION_APPROVE", "Tenant Application Approved"),
                    ("APPLICATION_REJECT", "Tenant Application Rejected"),
                    ("DENOMINATION_CREATE", "Denomination Created"),
                    ("DENOMINATION_UPDATE", "Denomination Updated"),
                    ("DENOMINATION_SEED", "Denomination Profiles Seeded"),
                    ("DENOMINATION_TERMINOLOGY", "Denomination Terminology Updated"),
                    ("DENOMINATION_SEEDS_CONFIG", "Denomination Seed Config Updated"),
                    ("DENOMINATION_BILLING_VIEW", "Denomination Billing Viewed"),
                ],
                max_length=40,
            ),
        ),
    ]
