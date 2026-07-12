# Generated manually for remittance account types and fund dimension

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0004_ledger_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="account",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("TITHE", "Tithe"),
                    ("COMBINED", "Combined Offering"),
                    ("INCOME", "Income"),
                    ("EXPENSE", "Expense"),
                    ("DISTRICT_PAYABLE", "District Payable"),
                    ("TITHE_REMIT_PAYABLE", "Tithe Remittance Payable"),
                    ("COMBINED_REMIT_PAYABLE", "Combined Remittance Payable"),
                    ("COMBINED_RETENTION", "Combined Retention Income"),
                    ("WELFARE_FUND", "Welfare Fund"),
                    ("REMITTANCE_RECEIVABLE", "Remittance Receivable"),
                    ("BANK", "Bank"),
                    ("CASH", "Cash"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="transactionline",
            name="fund",
            field=models.CharField(
                blank=True,
                choices=[
                    ("OPERATIONAL", "Operational"),
                    ("TITHE_TRUST", "Tithe Trust"),
                    ("COMBINED_TRUST", "Combined Trust"),
                    ("COMBINED_RETENTION", "Combined Retention"),
                    ("WELFARE", "Welfare"),
                ],
                default="",
                max_length=30,
            ),
        ),
    ]
