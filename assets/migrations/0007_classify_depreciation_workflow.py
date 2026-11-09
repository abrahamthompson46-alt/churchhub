"""Classify historical depreciation entries from the linked journal only.

0006 remains additive field defaults (POSTED / register_applied=True). Those
defaults do **not** establish historical register correctness or proven NBV.
This follow-on data step is a new migration because 0006 may already have been
applied on isolated test databases; rewriting it would diverge applied
migration history. 0006 was never a production deploy in the Phase 1 report.

Classification rules are frozen **in this file**. Do not import
``assets.depreciation_classification``; a later helper change must not alter
already-written migration history.

Does not create, delete, approve, or relink journals. Does not write
FixedAsset.accumulated_depreciation.

Reverse is a no-op: prior workflow_status / register_applied values are not
stored, so classification cannot be reconstructed.
"""

from django.db import migrations


def classify_from_linked_journal(*, approval_status, is_voided):
    """Frozen copy of Phase 1A FK-only rules. Return (status, applied) or None.

    None means leave the row unchanged (APPROVED non-voided). That is not proof
    the stored register was finalized.
    """
    if is_voided or approval_status == "REVERSED":
        return "RECOVERY_REQUIRED", True
    if approval_status == "PENDING":
        return "AWAITING_APPROVAL", False
    if approval_status == "REJECTED":
        return "REJECTED", False
    if approval_status == "APPROVED":
        return None
    return "RECOVERY_REQUIRED", True


def forwards(apps, schema_editor):
    AssetDepreciationEntry = apps.get_model("assets", "AssetDepreciationEntry")
    Transaction = apps.get_model("transactions", "Transaction")
    changed_pks = []
    qs = AssetDepreciationEntry.objects.exclude(transaction_id=None).iterator()
    for entry in qs:
        try:
            trx = Transaction.objects.get(pk=entry.transaction_id)
        except Transaction.DoesNotExist:
            continue
        result = classify_from_linked_journal(
            approval_status=trx.approval_status,
            is_voided=bool(getattr(trx, "is_voided", False)),
        )
        if result is None:
            continue
        workflow_status, register_applied = result
        if (
            entry.workflow_status == workflow_status
            and entry.register_applied is register_applied
        ):
            continue
        AssetDepreciationEntry.objects.filter(pk=entry.pk).update(
            workflow_status=workflow_status,
            register_applied=register_applied,
        )
        changed_pks.append(entry.pk)
    return len(changed_pks)


def backwards(apps, schema_editor):
    """Irreversible: original 0006-defaulted flags cannot be reconstructed."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_assetdepreciationentry_workflow"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
