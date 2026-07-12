# Generated manually for multi-denomination SaaS

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_user_member"),
        ("sitecontrol", "0005_denomination_saas"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                help_text="Required for hierarchy admins without a church; must match church denomination.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="institution_users",
                to="sitecontrol.denomination",
            ),
        ),
    ]
