# Generated manually for optional MFA audience policy

from django.db import migrations, models

import sitecontrol.models


def seed_mfa_audiences(apps, schema_editor):
    SiteSettings = apps.get_model("sitecontrol", "SiteSettings")
    for row in SiteSettings.objects.all():
        changed = False
        if not row.mfa_institution_roles:
            row.mfa_institution_roles = ["SUPER_ADMIN", "TREASURY"]
            changed = True
        if not row.mfa_platform_roles:
            row.mfa_platform_roles = ["OWNER", "SECURITY"]
            changed = True
        if changed:
            row.save(
                update_fields=["mfa_institution_roles", "mfa_platform_roles"]
            )


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0011_mfa_enforcement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="mfa_required_for_privileged",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, require MFA (TOTP / email OTP / recovery) for the audiences "
                    "selected below. Off by default — platform owners decide when to enforce."
                ),
                verbose_name="Require MFA for selected audiences",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mfa_institution_roles",
            field=models.JSONField(
                blank=True,
                default=sitecontrol.models.default_mfa_institution_roles,
                help_text=(
                    "Institution User.role codes that must use MFA when enforcement is on. "
                    "Recommended starter set: SUPER_ADMIN, TREASURY."
                ),
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mfa_platform_roles",
            field=models.JSONField(
                blank=True,
                default=sitecontrol.models.default_mfa_platform_roles,
                help_text=(
                    "Platform operator roles that must use MFA when enforcement is on. "
                    "Recommended starter set: OWNER, SECURITY."
                ),
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mfa_include_django_superusers",
            field=models.BooleanField(
                default=True,
                help_text="When MFA enforcement is on, also require MFA for Django superusers.",
            ),
        ),
        migrations.RunPython(seed_mfa_audiences, migrations.RunPython.noop),
    ]
