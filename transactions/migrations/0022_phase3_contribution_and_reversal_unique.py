"""Phase 3: CONTRIBUTION idempotency action + one reversal per original.

Quarantines historical duplicate reversals before adding the unique constraint.
Never deletes financial history.
"""

from django.db import migrations, models


def quarantine_duplicate_reversals(apps, schema_editor):
    Transaction = apps.get_model("transactions", "Transaction")
    FinancialAuditLog = apps.get_model("transactions", "FinancialAuditLog")

    seen = {}
    duplicates = (
        Transaction.objects.filter(reversal_of__isnull=False)
        .order_by("reversal_of_id", "created_at", "id")
    )
    for trx in duplicates.iterator():
        original_id = trx.reversal_of_id
        if original_id not in seen:
            seen[original_id] = trx.pk
            continue
        # Keep the earliest reversal; quarantine extras without deleting rows.
        # Transaction.description max_length=200 (PostgreSQL varchar limit).
        kept = seen[original_id]
        prefix = f"[QUARANTINED_DUPLICATE_REVERSAL kept={kept}] "
        trx.description = (prefix + (trx.description or ""))[:200]
        trx.reversal_of_id = None
        trx.is_voided = True
        trx.save(update_fields=["description", "reversal_of", "is_voided"])
        FinancialAuditLog.objects.create(
            church_id=trx.church_id,
            action="UPDATE",
            performed_by=None,
            transaction_id=trx.pk,
            details={
                "type": "QUARANTINE_DUPLICATE_REVERSAL",
                "original_reversal_of": str(original_id),
                "kept_reversal_id": str(seen[original_id]),
                "quarantined_transaction_id": str(trx.pk),
            },
        )


def noop_reverse(apps, schema_editor):
    # Quarantine is intentionally not undone (would reintroduce uniqueness violations).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0021_treasury_auto_approve_cap"),
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
                    ("CONTRIBUTION", "Member Contribution"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(quarantine_duplicate_reversals, noop_reverse),
        migrations.AddConstraint(
            model_name="transaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(reversal_of__isnull=False),
                fields=("reversal_of",),
                name="uniq_txn_one_reversal_per_original",
            ),
        ),
    ]
