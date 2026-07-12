# Generated manually for multi-denomination SaaS

import django.db.models.deletion
from django.db import migrations, models


def assign_default_denomination(apps, schema_editor):
    Denomination = apps.get_model("sitecontrol", "Denomination")
    Conference = apps.get_model("organization", "Conference")
    default = Denomination.objects.filter(is_default=True).first()
    if default:
        Conference.objects.filter(denomination__isnull=True).update(denomination_id=default.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0002_generalconference_union_conference_union"),
        ("sitecontrol", "0005_denomination_saas"),
    ]

    operations = [
        migrations.AddField(
            model_name="conference",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="conferences",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.RunPython(assign_default_denomination, migrations.RunPython.noop),
    ]
