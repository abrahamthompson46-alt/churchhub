"""Read-only depreciation register reconciliation inventory.

Classifies rows using durable foreign keys and existing selector predicates.
Does not post, approve, void, relink, or write stored accumulated depreciation.
Does not treat description, asset code, date, or amount as identity.
"""

from __future__ import annotations

from django.db.models import Q

from church_system.money import quantize_money

from . import selectors
from .models import AssetDepreciationEntry, FixedAsset


# Frozen understood statuses. Do not derive this from live CHOICES: a newly
# added choice must remain visible as unfamiliar until inventory is updated.
UNDERSTOOD_WORKFLOW_STATUSES = frozenset(
    {
        AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
        AssetDepreciationEntry.WORKFLOW_POSTED,
        AssetDepreciationEntry.WORKFLOW_REJECTED,
        AssetDepreciationEntry.WORKFLOW_FAILED,
        AssetDepreciationEntry.WORKFLOW_RECOVERY_REQUIRED,
    }
)

ENTRY_ORDER = ("asset__church_id", "asset_id", "period_year", "period_month", "pk")
JOURNAL_ORDER = ("church_id", "created_at", "pk")
ASSET_ORDER = ("church_id", "pk")

# Summary counts unique ids per category. Records may appear in more than one
# category list; ``overlaps`` reports those intersections. Categories are not a
# partition of all rows. The three unlinked-CAPITAL journal categories are
# disjoint by approval_status / is_voided.
CATEGORY_KEYS = (
    "linked_entries",
    "null_fk_entries",
    "unclassified_pending_capital_candidates",
    "unclassified_approved_capital_candidates",
    "unclassified_other_capital_candidates",
    "recovery_required_entries",
    "unexpected_workflow_entries",
    "approved_unproven_entries",
    "aggregate_mismatch_assets",
    "matching_unproven_assets",
)


def _church_filter(churches):
    if churches is None:
        return Q()
    return Q(church__in=churches)


def _entry_church_filter(churches):
    if churches is None:
        return Q()
    return Q(asset__church__in=churches)


def _normalize_identifier_limit(identifier_limit):
    if identifier_limit is None:
        return 0
    try:
        value = int(identifier_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("identifier_limit must be an integer >= 0") from exc
    if value < 0:
        raise ValueError("identifier_limit must be >= 0")
    return value


def _limited_view(all_ids, records, identifier_limit):
    limit = _normalize_identifier_limit(identifier_limit)
    shown_ids = all_ids[:limit]
    shown_records = records[:limit]
    count = len(all_ids)
    shown = len(shown_ids)
    return {
        "count": count,
        "shown": shown,
        "omitted": max(0, count - shown),
        "truncated": shown < count,
        "ids": shown_ids,
        "records": shown_records,
    }


def _asset_fk_transaction_ids():
    """Global relationship detectors. Do not church-scope these exclusions."""
    dep_ids = AssetDepreciationEntry.objects.exclude(transaction_id=None).values(
        "transaction_id"
    )
    acq_ids = FixedAsset.objects.exclude(acquisition_transaction_id=None).values(
        "acquisition_transaction_id"
    )
    disp_ids = FixedAsset.objects.exclude(disposal_transaction_id=None).values(
        "disposal_transaction_id"
    )
    return dep_ids, acq_ids, disp_ids


def linked_depreciation_entries_qs(churches=None):
    return (
        AssetDepreciationEntry.objects.filter(_entry_church_filter(churches))
        .exclude(transaction_id=None)
        .select_related("transaction", "asset", "asset__church")
        .order_by(*ENTRY_ORDER)
    )


def null_fk_depreciation_entries_qs(churches=None):
    return (
        AssetDepreciationEntry.objects.filter(_entry_church_filter(churches))
        .filter(transaction_id=None)
        .select_related("asset", "asset__church")
        .order_by(*ENTRY_ORDER)
    )


def recovery_required_entries_qs(churches=None):
    return (
        AssetDepreciationEntry.objects.filter(_entry_church_filter(churches))
        .filter(selectors.unresolved_register_history_q())
        .select_related("transaction", "asset", "asset__church")
        .order_by(*ENTRY_ORDER)
    )


def unexpected_workflow_entries_qs(churches=None):
    """Statuses outside the frozen understood set, including new CHOICES values."""
    return (
        AssetDepreciationEntry.objects.filter(_entry_church_filter(churches))
        .exclude(workflow_status__in=UNDERSTOOD_WORKFLOW_STATUSES)
        .select_related("transaction", "asset", "asset__church")
        .order_by(*ENTRY_ORDER)
    )


def _unlinked_capital_base_qs(churches):
    from transactions.models import Transaction

    dep_ids, acq_ids, disp_ids = _asset_fk_transaction_ids()
    return (
        Transaction.objects.filter(_church_filter(churches))
        .filter(transaction_type="CAPITAL")
        .exclude(pk__in=dep_ids)
        .exclude(pk__in=acq_ids)
        .exclude(pk__in=disp_ids)
        .select_related("church")
        .order_by(*JOURNAL_ORDER)
    )


def unclassified_pending_capital_candidates_qs(churches=None):
    """PENDING non-voided CAPITAL with no depreciation, acquisition, or disposal FK."""
    return _unlinked_capital_base_qs(churches).filter(
        approval_status="PENDING",
        is_voided=False,
    )


def unclassified_approved_capital_candidates_qs(churches=None):
    """APPROVED non-voided CAPITAL with no asset-module FK. Not confirmed depreciation."""
    return _unlinked_capital_base_qs(churches).filter(
        approval_status="APPROVED",
        is_voided=False,
    )


def unclassified_other_capital_candidates_qs(churches=None):
    """Unlinked REJECTED, REVERSED, or voided CAPITAL.

    Identity-gap review items only. Not confirmed depreciation. Listing here
    does not make a row recoverable or change unresolved-history semantics.
    """
    return _unlinked_capital_base_qs(churches).filter(
        Q(is_voided=True) | Q(approval_status__in=("REJECTED", "REVERSED"))
    )


def approved_unproven_entries_qs(churches=None):
    """Linked APPROVED non-voided entries. Schema cannot prove NBV was finalized."""
    return (
        linked_depreciation_entries_qs(churches)
        .filter(transaction__approval_status="APPROVED")
        .exclude(transaction__is_voided=True)
    )


def _entry_ref(entry):
    church = entry.asset.church
    return {
        "kind": "entry",
        "id": str(entry.pk),
        "church_id": str(church.pk),
        "church_code": church.code,
        "asset_id": str(entry.asset_id),
        "period": f"{entry.period_year:04d}-{entry.period_month:02d}",
        "workflow_status": entry.workflow_status,
        "register_applied": entry.register_applied,
        "transaction_id": str(entry.transaction_id) if entry.transaction_id else None,
        "journal_status": getattr(entry.transaction, "approval_status", None),
        "journal_voided": bool(getattr(entry.transaction, "is_voided", False)),
    }


def _journal_ref(trx, *, kind):
    return {
        "kind": kind,
        "id": str(trx.pk),
        "church_id": str(trx.church_id),
        "church_code": trx.church.code,
        "reference": trx.reference,
        "approval_status": trx.approval_status,
        "is_voided": bool(trx.is_voided),
        "confirmed_depreciation": False,
        "source_module_known": False,
    }


def _asset_ref(asset, *, stored, contributing, outcome):
    return {
        "kind": "asset",
        "id": str(asset.pk),
        "church_id": str(asset.church_id),
        "church_code": asset.church.code,
        "stored_accumulated_depreciation": str(stored),
        "contributing_total": str(contributing),
        "outcome": outcome,
    }


def _materialize_entries(qs):
    rows = list(qs)
    return [str(row.pk) for row in rows], [_entry_ref(row) for row in rows]


def _materialize_journals(qs, *, kind):
    rows = list(qs)
    return [str(row.pk) for row in rows], [
        _journal_ref(row, kind=kind) for row in rows
    ]


def _category_block(all_ids, records, definition, identifier_limit, *, outcome=None):
    block = {
        "definition": definition,
        **_limited_view(all_ids, records, identifier_limit),
    }
    if outcome:
        block["outcome"] = outcome
    return block


def build_depreciation_register_inventory(churches=None, *, identifier_limit=50):
    """Return a read-only inventory dict. Performs no writes."""
    linked_ids, linked_records = _materialize_entries(
        linked_depreciation_entries_qs(churches)
    )
    null_ids, null_records = _materialize_entries(
        null_fk_depreciation_entries_qs(churches)
    )
    recovery_ids, recovery_records = _materialize_entries(
        recovery_required_entries_qs(churches)
    )
    unexpected_ids, unexpected_records = _materialize_entries(
        unexpected_workflow_entries_qs(churches)
    )
    pending_ids, pending_records = _materialize_journals(
        unclassified_pending_capital_candidates_qs(churches),
        kind="unclassified_pending_capital_candidate",
    )
    approved_gap_ids, approved_gap_records = _materialize_journals(
        unclassified_approved_capital_candidates_qs(churches),
        kind="unclassified_approved_capital_candidate",
    )
    other_ids, other_records = _materialize_journals(
        unclassified_other_capital_candidates_qs(churches),
        kind="unclassified_other_capital_candidate",
    )
    approved_unproven_ids, approved_unproven_records = _materialize_entries(
        approved_unproven_entries_qs(churches)
    )

    assets = (
        FixedAsset.objects.filter(_church_filter(churches))
        .select_related("church")
        .order_by(*ASSET_ORDER)
    )
    mismatch_assets = []
    matching_unproven_assets = []
    for asset in assets.iterator():
        stored = quantize_money(asset.accumulated_depreciation)
        contributing = quantize_money(selectors.asset_depreciation_total(asset))
        has_null = asset.depreciation_entries.filter(transaction_id=None).exists()
        has_recovery = asset.depreciation_entries.filter(
            selectors.unresolved_register_history_q()
        ).exists()
        has_approved = (
            asset.depreciation_entries.filter(
                ~Q(transaction_id=None),
                transaction__approval_status="APPROVED",
            )
            .exclude(transaction__is_voided=True)
            .exists()
        )
        if stored != contributing:
            mismatch_assets.append(
                _asset_ref(
                    asset,
                    stored=stored,
                    contributing=contributing,
                    outcome="mismatch",
                )
            )
            continue
        if has_null or has_recovery or has_approved:
            matching_unproven_assets.append(
                _asset_ref(
                    asset,
                    stored=stored,
                    contributing=contributing,
                    outcome="unproven",
                )
            )

    pending_id_set = set(pending_ids)
    approved_gap_set = set(approved_gap_ids)
    other_id_set = set(other_ids)
    linked_id_set = set(linked_ids)
    recovery_id_set = set(recovery_ids)
    unexpected_id_set = set(unexpected_ids)
    approved_unproven_set = set(approved_unproven_ids)
    null_id_set = set(null_ids)

    inventory = {
        "categories": {
            "linked_entries": _category_block(
                linked_ids,
                linked_records,
                "AssetDepreciationEntry rows with a non-null transaction FK.",
                identifier_limit,
            ),
            "null_fk_entries": _category_block(
                null_ids,
                null_records,
                "AssetDepreciationEntry rows with transaction_id null.",
                identifier_limit,
            ),
            "unclassified_pending_capital_candidates": _category_block(
                pending_ids,
                pending_records,
                "PENDING non-voided CAPITAL journals not referenced by "
                "depreciation-entry, acquisition, or disposal FKs. Not "
                "confirmed as depreciation. Disjoint from approved and other "
                "unlinked CAPITAL categories.",
                identifier_limit,
                outcome="identity_gap",
            ),
            "unclassified_approved_capital_candidates": _category_block(
                approved_gap_ids,
                approved_gap_records,
                "APPROVED non-voided CAPITAL journals not referenced by "
                "depreciation-entry, acquisition, or disposal FKs. Unclassified "
                "candidates: source module cannot be established from available "
                "relationships. May include stranded depreciation or ordinary "
                "capital. Not confirmed as depreciation. Disjoint from PENDING "
                "and other unlinked CAPITAL categories.",
                identifier_limit,
                outcome="identity_gap",
            ),
            "unclassified_other_capital_candidates": _category_block(
                other_ids,
                other_records,
                "REJECTED, REVERSED, or voided CAPITAL journals not referenced "
                "by depreciation-entry, acquisition, or disposal FKs. "
                "Identity-gap review items only; not confirmed depreciation. "
                "Listing does not mark a row recoverable. Disjoint from "
                "PENDING and APPROVED unlinked CAPITAL categories.",
                identifier_limit,
                outcome="identity_gap",
            ),
            "recovery_required_entries": _category_block(
                recovery_ids,
                recovery_records,
                "Entries matching unresolved_register_history_q "
                "(RECOVERY_REQUIRED, FAILED, voided, or REVERSED journal).",
                identifier_limit,
            ),
            "unexpected_workflow_entries": _category_block(
                unexpected_ids,
                unexpected_records,
                "Entries whose workflow_status is outside the frozen understood "
                "set (AWAITING_APPROVAL, POSTED, REJECTED, FAILED, "
                "RECOVERY_REQUIRED), including new model choices not yet "
                "reviewed for inventory.",
                identifier_limit,
            ),
            "approved_unproven_entries": _category_block(
                approved_unproven_ids,
                approved_unproven_records,
                "Linked APPROVED non-voided entries. Matching stored NBV is "
                "not proof the register was finalized for that row.",
                identifier_limit,
                outcome="unproven",
            ),
            "aggregate_mismatch_assets": _category_block(
                [row["id"] for row in mismatch_assets],
                mismatch_assets,
                "Assets whose contributing depreciation total differs from "
                "stored accumulated_depreciation.",
                identifier_limit,
                outcome="mismatch",
            ),
            "matching_unproven_assets": _category_block(
                [row["id"] for row in matching_unproven_assets],
                matching_unproven_assets,
                "Assets whose totals match but null-FK rows, unresolved "
                "history, or linked APPROVED journals prevent a reliable "
                "historical conclusion.",
                identifier_limit,
                outcome="unproven",
            ),
        },
        "overlaps": {
            "linked_and_recovery": sorted(linked_id_set & recovery_id_set),
            "linked_and_approved_unproven": sorted(
                linked_id_set & approved_unproven_set
            ),
            "recovery_and_unexpected": sorted(recovery_id_set & unexpected_id_set),
            "null_fk_and_linked": sorted(null_id_set & linked_id_set),
            "pending_candidates_and_approved_candidates": sorted(
                pending_id_set & approved_gap_set
            ),
            "pending_candidates_and_other_candidates": sorted(
                pending_id_set & other_id_set
            ),
            "approved_candidates_and_other_candidates": sorted(
                approved_gap_set & other_id_set
            ),
            "mismatch_and_matching_unproven_assets": [],
        },
        "notes": [
            "Category lists may overlap; summary counts are unique ids per category.",
            "identifier_limit restricts displayed ids/records only; count is the full population.",
            "Unlinked PENDING CAPITAL journals are candidates only.",
            "Unlinked APPROVED CAPITAL journals are unclassified candidates, not confirmed depreciation; source module cannot be established.",
            "Unlinked REJECTED, REVERSED, or voided CAPITAL journals are a separate review category; listing them does not make them recoverable.",
            "The three unlinked CAPITAL categories are disjoint by approval_status and is_voided.",
            "No category uses description, asset code, date, or amount as identity.",
            "APPROVED linked entries are never labeled historically finalized.",
            "This command does not enforce RBAC; output contains tenant identifiers and totals.",
        ],
    }
    mismatch_ids = {row["id"] for row in mismatch_assets}
    matching_ids = {row["id"] for row in matching_unproven_assets}
    inventory["overlaps"]["mismatch_and_matching_unproven_assets"] = sorted(
        mismatch_ids & matching_ids
    )
    return inventory
