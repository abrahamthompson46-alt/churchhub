# Add PAYROLL_POST / PAYROLL_PAY idempotency actions.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0015_ledger_idempotency_action"),
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
                    ("PAYROLL_POST", "Payroll Post"),
                    ("PAYROLL_PAY", "Payroll Pay"),
                ],
                max_length=20,
            ),
        ),
    ]
