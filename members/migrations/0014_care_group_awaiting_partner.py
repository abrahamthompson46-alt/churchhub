from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0013_care_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="caregroupmembership",
            name="awaiting_partner",
            field=models.BooleanField(
                default=False,
                help_text="Odd member out: waiting for a one-to-one partner in this group.",
            ),
        ),
    ]
