# Add LEDGER action to FinancialIdempotencyKey.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0014_transaction_reference_per_church"),
    ]

    operations = [
        migrations.AlterField(
            model_name="financialidempotencykey",
            name="action",
            field=models.CharField(
                choices=[
                    ("RECEIPT", "Receipt"),
                    ("EXPENSE", "Expense"),
                    ("REMITTANCE", "Remittance"),
                    ("LEDGER", "Ledger Entry"),
                ],
                max_length=20,
            ),
        ),
    ]
