"""Enable MFA for privileged roles by default (security hardening)."""

from django.db import migrations, models


def enable_mfa_policy(apps, schema_editor):
    SiteSettings = apps.get_model("sitecontrol", "SiteSettings")
    SiteSettings.objects.filter(singleton_id=1).update(mfa_required_for_privileged=True)


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0017_denomination_feature_contribution_campaigns_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="mfa_required_for_privileged",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When enabled, require MFA (TOTP / email OTP / recovery) for the audiences "
                    "selected below. Recommended for production — treasury and platform roles."
                ),
                verbose_name="Require MFA for selected audiences",
            ),
        ),
        migrations.RunPython(enable_mfa_policy, migrations.RunPython.noop),
    ]
