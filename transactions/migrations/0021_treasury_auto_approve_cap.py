"""Cap receipt auto-approval — no unlimited default."""

from decimal import Decimal

from django.db import migrations, models


CAP = Decimal("500.00")


def cap_null_auto_approve_limits(apps, schema_editor):
    TreasuryApprovalPolicy = apps.get_model("transactions", "TreasuryApprovalPolicy")
    TreasuryApprovalPolicy.objects.filter(default_receipt_auto_approve_limit__isnull=True).update(
        default_receipt_auto_approve_limit=CAP,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0020_treasury_receipt_auto_approve"),
    ]

    operations = [
        migrations.AlterField(
            model_name="treasuryapprovalpolicy",
            name="default_receipt_auto_approve_limit",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=Decimal("500.00"),
                help_text=(
                    "Church default: receipts up to this amount auto-approve. "
                    "Set 0 to require second approval for every receipt."
                ),
                max_digits=14,
                null=True,
            ),
        ),
        migrations.RunPython(cap_null_auto_approve_limits, migrations.RunPython.noop),
    ]
