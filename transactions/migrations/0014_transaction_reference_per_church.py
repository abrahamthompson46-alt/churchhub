from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0013_transactions_enterprise"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="reference",
            field=models.CharField(blank=True, editable=False, max_length=40, null=True),
        ),
        migrations.AddConstraint(
            model_name="transaction",
            constraint=models.UniqueConstraint(
                fields=("church", "reference"),
                name="uniq_txn_reference_per_church",
            ),
        ),
    ]
