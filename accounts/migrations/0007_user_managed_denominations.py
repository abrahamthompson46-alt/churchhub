# Platform operator denomination scoping (M2M)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_denomination"),
        ("sitecontrol", "0005_denomination_saas"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="managed_denominations",
            field=models.ManyToManyField(
                blank=True,
                help_text="Platform operators: leave empty for global access (super operators).",
                related_name="platform_operators",
                to="sitecontrol.denomination",
            ),
        ),
    ]
