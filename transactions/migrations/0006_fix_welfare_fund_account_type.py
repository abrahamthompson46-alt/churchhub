"""Restore Welfare Fund account type after ledger seed overwrote it."""

from django.db import migrations

CORE_ACCOUNTS = [
    ("Tithe", "TITHE"),
    ("Combined Offering", "COMBINED"),
    ("General Income", "INCOME"),
    ("General Expense", "EXPENSE"),
    ("District Payable", "DISTRICT_PAYABLE"),
    ("Tithe Remittance Payable", "TITHE_REMIT_PAYABLE"),
    ("Combined Remittance Payable", "COMBINED_REMIT_PAYABLE"),
    ("Combined Retention Income", "COMBINED_RETENTION"),
    ("Welfare Fund", "WELFARE_FUND"),
    ("Remittance Receivable", "REMITTANCE_RECEIVABLE"),
    ("Main Bank", "BANK"),
    ("Cash", "CASH"),
]


def restore_core_account_types(apps, schema_editor):
    Account = apps.get_model("transactions", "Account")
    for name, account_type in CORE_ACCOUNTS:
        Account.objects.filter(name=name).exclude(account_type=account_type).update(
            account_type=account_type
        )


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0005_remittance_accounts_and_fund"),
    ]

    operations = [
        migrations.RunPython(restore_core_account_types, migrations.RunPython.noop),
    ]
