"""FK-only historical classification for AssetDepreciationEntry workflow fields.

Uses the existing entry.transaction link and journal approval/void flags only.
Does not match description, amount, date, or church. Does not write journals,
lines, audit rows, or FixedAsset.accumulated_depreciation.

Migration ``0007`` embeds a frozen copy of these rules. Changing this module
does not change already-applied migration history. Keep tests of live
classification here; keep 0007 self-contained.
"""

from __future__ import annotations

STATUS_AWAITING = "AWAITING_APPROVAL"
STATUS_POSTED = "POSTED"
STATUS_REJECTED = "REJECTED"
STATUS_RECOVERY = "RECOVERY_REQUIRED"


def classify_from_linked_journal(*, approval_status, is_voided):
    """Return (workflow_status, register_applied) or None to leave the row unchanged.

    Historical HEAD (2ec9c3f) wrote a period row when the CAPITAL journal stayed
    PENDING and did not update accumulated depreciation. Reject of that journal
    also left the register unapplied. Void is only allowed on APPROVED journals,
    after the register was applied; void does not unwind NBV.
    """
    if is_voided or approval_status == "REVERSED":
        return STATUS_RECOVERY, True
    if approval_status == "PENDING":
        return STATUS_AWAITING, False
    if approval_status == "REJECTED":
        return STATUS_REJECTED, False
    if approval_status == "APPROVED":
        return None
    return STATUS_RECOVERY, True


def classify_historical_depreciation_entries(entry_model):
    """Idempotent update of workflow fields. Returns number of rows changed."""
    changed = 0
    qs = (
        entry_model.objects.exclude(transaction_id=None)
        .select_related("transaction")
        .iterator()
    )
    for entry in qs:
        trx = entry.transaction
        if trx is None:
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
        entry_model.objects.filter(pk=entry.pk).update(
            workflow_status=workflow_status,
            register_applied=register_applied,
        )
        changed += 1
    return changed
