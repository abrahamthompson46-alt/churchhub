from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0012_budget_enterprise"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="transactionline",
            index=models.Index(fields=["account"], name="txn_line_account_idx"),
        ),
        migrations.AddIndex(
            model_name="transactionline",
            index=models.Index(
                fields=["transaction", "account"],
                name="txn_line_txn_acct_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="financialauditlog",
            index=models.Index(
                fields=["church", "created_at"],
                name="fin_audit_church_dt_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="financialauditlog",
            index=models.Index(
                fields=["church", "action"],
                name="fin_audit_church_act_idx",
            ),
        ),
    ]
