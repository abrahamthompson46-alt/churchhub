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


def asset_depreciation_total(asset) -> Decimal:
    total = asset.depreciation_entries.aggregate(t=Sum("amount"))["t"]
    return total or Decimal("0")


def depreciation_entries_for_churches(churches):
    return AssetDepreciationEntry.objects.filter(
        asset__church__in=churches,
    ).select_related("asset__church", "asset")


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
