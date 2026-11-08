# Additive denomination wall for General Conference (empty GC/Union isolation).

import django.db.models.deletion
from django.db import migrations, models


def backfill_gc_denomination(apps, schema_editor):
    GeneralConference = apps.get_model("organization", "GeneralConference")
    Conference = apps.get_model("organization", "Conference")
    for gc in GeneralConference.objects.all():
        denom_ids = list(
            Conference.objects.filter(union__general_conference_id=gc.pk)
            .exclude(denomination_id__isnull=True)
            .values_list("denomination_id", flat=True)
            .distinct()
        )
        if len(denom_ids) == 1:
            gc.denomination_id = denom_ids[0]
            gc.save(update_fields=["denomination_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0006_church_history_entry"),
        ("sitecontrol", "0005_denomination_saas"),
    ]

    operations = [
        migrations.AddField(
            model_name="generalconference",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="general_conferences",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.RunPython(backfill_gc_denomination, migrations.RunPython.noop),
    ]
