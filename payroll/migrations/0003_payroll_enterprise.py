# Payroll enterprise: line source_ref + audit actions; idempotency actions.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0002_payrollrun_budget_warning_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrolllineitem",
            name="source_ref",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional source id (e.g. loan UUID) for recovery posting.",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="payrollrunauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("CREATE", "Created"),
                    ("CALCULATE", "Calculated"),
                    ("APPROVE", "Approved"),
                    ("REJECT", "Rejected"),
                    ("POST", "Posted"),
                    ("PAY", "Paid"),
                    ("VOID", "Voided"),
                    ("REOPEN", "Reopened"),
                    ("REVERSE", "Reversed"),
                    ("EXPORT", "Exported"),
                ],
                max_length=20,
            ),
        ),
    ]
