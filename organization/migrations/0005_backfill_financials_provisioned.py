from django.db import migrations


def backfill_financials_provisioned(apps, schema_editor):
    Church = apps.get_model("organization", "Church")
    Account = apps.get_model("transactions", "Account")
    church_ids = Account.objects.values_list("church_id", flat=True).distinct()
    Church.objects.filter(pk__in=church_ids, financials_provisioned=False).update(
        financials_provisioned=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0004_organization_enterprise"),
        ("transactions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_financials_provisioned, migrations.RunPython.noop),
    ]
