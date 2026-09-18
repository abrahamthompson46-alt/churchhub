from django.db import migrations, models


def close_non_demo_public_registration(apps, schema_editor):
    Denomination = apps.get_model("sitecontrol", "Denomination")
    Denomination.objects.exclude(code="demo").update(allow_public_registration=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sitecontrol", "0026_denomination_system_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="denomination",
            name="allow_public_registration",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow /apply/ trial registrations scoped to this denomination. "
                    "Keep off for live churches; DEMO may stay on."
                ),
            ),
        ),
        migrations.RunPython(close_non_demo_public_registration, noop),
    ]
