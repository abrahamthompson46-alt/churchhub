from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0021_denomination_allow_institution_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="auto_provision_public_trials",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When public registration is open, provision a church, first user, and "
                    "30-day TRIAL immediately. No operator approval. Disable only to restore "
                    "the queued application workflow."
                ),
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="public_demo_trial_days",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text=(
                    "Hard public demo length in days (max 30). Frozen onto the subscription "
                    "as expires_at at provision time; changing this later does not extend "
                    "existing demos."
                ),
                validators=[MinValueValidator(1), MaxValueValidator(30)],
            ),
        ),
        migrations.AddField(
            model_name="tenantapplication",
            name="contact_phone_normalized",
            field=models.CharField(blank=True, db_index=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="allow_church_self_registration",
            field=models.BooleanField(
                default=False,
                help_text="Allow public church self-registration at /apply/.",
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="registration_intro",
            field=models.TextField(
                blank=True,
                default=(
                    "Create your church workspace and start a 30-day demo. "
                    "Access ends automatically when the trial expires."
                ),
            ),
        ),
    ]
