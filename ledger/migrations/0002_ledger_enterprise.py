# Generated manually for ledger enterprise constraints and help text.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0001_ledger_category"),
        ("transactions", "0004_ledger_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ledgercategory",
            name="remit_to_district",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When set on a receipt category, posting uses remittance policy splits "
                    "(retain + remit payables) instead of a flat credit to the template account."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgercategory",
            constraint=models.CheckConstraint(
                condition=~models.Q(
                    default_debit_account=models.F("default_credit_account")
                ),
                name="ledger_category_debit_ne_credit",
            ),
        ),
    ]
