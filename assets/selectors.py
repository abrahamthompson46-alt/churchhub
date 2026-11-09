"""
Read/query helpers for the assets domain.

Views and services call selectors for church-scoped querysets.
Business rules stay in services; persistence writes stay in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from .models import (
    AssetAuditLog,
    AssetCategory,
    AssetCategoryTemplate,
    AssetDepreciationEntry,
    DepreciationPolicy,
    FixedAsset,
)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


def assets_for_church(church, *, status="", q=""):
    qs = FixedAsset.objects.filter(church=church).select_related("category")
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(asset_code__icontains=q)
            | Q(name__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(location__icontains=q)
        )
    return qs


def asset_for_church(church, pk):
    return get_object_or_404(FixedAsset, pk=pk, church=church)


def active_assets_for_church(church, *, with_category=False):
    qs = FixedAsset.objects.filter(church=church, status="ACTIVE")
    if with_category:
        qs = qs.select_related("category")
    return qs


def assets_register_qs(church, status=None):
    qs = FixedAsset.objects.filter(church=church).select_related("category")
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("asset_code")


def assets_for_churches(churches):
    return FixedAsset.objects.filter(church__in=churches).select_related(
        "church", "category"
    )


def active_assets_rollup_agg(churches):
    return (
        FixedAsset.objects.filter(church__in=churches, status="ACTIVE")
        .values("church__name", "church__district__name")
        .annotate(
            asset_count=Count("id"),
            total_cost=Sum("acquisition_cost"),
            total_accum=Sum("accumulated_depreciation"),
        )
        .order_by("church__district__name", "church__name")
    )


def church_assets_qs(church):
    return FixedAsset.objects.filter(church=church)


def last_asset_code_for_prefix(church, pattern):
    return (
        FixedAsset.objects.filter(church=church, asset_code__startswith=pattern)
        .select_for_update()
        .order_by("-asset_code")
        .values_list("asset_code", flat=True)
        .first()
    )


def asset_count_for_church(church):
    return FixedAsset.objects.filter(church=church).count()


def asset_depreciation_entries(asset, limit=None):
    qs = asset.depreciation_entries.all()
    if limit is not None:
        return qs[:limit]
    return qs


def asset_audit_logs(asset, limit=20):
    return asset.audit_logs.all()[:limit]


def asset_maintenance_logs(asset, limit=20):
    return asset.maintenance_logs.all()[:limit]


# ---------------------------------------------------------------------------
# Categories / policy / templates
# ---------------------------------------------------------------------------


def categories_for_church(church):
    return AssetCategory.objects.filter(church=church).select_related("template")


def category_for_church(church, pk):
    return get_object_or_404(AssetCategory, pk=pk, church=church)


def active_templates():
    return AssetCategoryTemplate.objects.filter(is_active=True)


def depreciation_policy_for_church(church):
    return DepreciationPolicy.objects.filter(church=church).first()


# ---------------------------------------------------------------------------
# Depreciation entries
# ---------------------------------------------------------------------------


def depreciation_entry_exists(asset, period_year, period_month):
    return AssetDepreciationEntry.objects.filter(
        asset=asset, period_year=period_year, period_month=period_month
    ).exists()


def depreciation_entry_for_period(asset, period_year, period_month):
    return (
        AssetDepreciationEntry.objects.filter(
            asset=asset, period_year=period_year, period_month=period_month
        )
        .select_related("transaction")
        .first()
    )


def pending_depreciation_journals(asset, period_year, period_month):
    from transactions.models import Transaction

    description = (
        f"Depreciation {asset.asset_code} {period_year}-{period_month:02d}"
    )
    return Transaction.objects.filter(
        church_id=asset.church_id,
        transaction_type="CAPITAL",
        description=description,
        approval_status="PENDING",
        is_voided=False,
    ).order_by("created_at")


def register_contributing_q():
    """Rows that may contribute to stored NBV / schedule totals.

    ``register_applied`` is required. Linked PENDING or REJECTED journals are
    excluded via the existing transaction FK (HEAD wrote those rows without
    updating accumulated depreciation). Voided/REVERSED journals stay in the
    total so NBV is not silently unwound.
    """
    return Q(register_applied=True) & ~Q(
        transaction__approval_status__in=("PENDING", "REJECTED")
    )


def unresolved_register_history_q():
    """FK-only rows that must not be absorbed by a full-sum register rewrite.

    Includes explicit recovery/failed workflow and linked voided/REVERSED
    journals. Does not match description, amount, date, or church.

    Null-FK legacy rows are intentionally omitted here. HEAD no-ledger posts
    wrote ``accumulated_depreciation`` in the same operation as the period row;
    migration 0007 left those POSTED/applied. They keep contributing. They only
    fail the recompute guard when the contributing sum disagrees with stored
    accum (checked separately in services).
    """
    return (
        Q(workflow_status__in=("RECOVERY_REQUIRED", "FAILED"))
        | Q(transaction__is_voided=True)
        | Q(transaction__approval_status="REVERSED")
    )


def asset_has_unresolved_register_history(asset) -> bool:
    return asset.depreciation_entries.filter(unresolved_register_history_q()).exists()


def asset_depreciation_total(asset) -> Decimal:
    """Sum of amounts that contribute to the posted depreciation register."""
    total = asset.depreciation_entries.filter(register_contributing_q()).aggregate(
        t=Sum("amount")
    )["t"]
    return total or Decimal("0")


def depreciation_entries_for_churches(churches, *, register_applied=None):
    qs = AssetDepreciationEntry.objects.filter(
        asset__church__in=churches,
    ).select_related("asset__church", "asset")
    if register_applied is True:
        qs = qs.filter(register_contributing_q())
    elif register_applied is not None:
        qs = qs.filter(register_applied=register_applied)
    return qs


# ---------------------------------------------------------------------------
# Audit / activity
# ---------------------------------------------------------------------------


def asset_audit_logs_for_church(church, action=""):
    qs = AssetAuditLog.objects.filter(asset__church=church).select_related(
        "asset", "user"
    )
    if action:
        qs = qs.filter(action=action)
    return qs


def policy_audit_logs_for_church(church, action=""):
    from .models import AssetPolicyAuditLog

    qs = AssetPolicyAuditLog.objects.filter(church=church).select_related("user")
    if action:
        qs = qs.filter(action=action)
    return qs
