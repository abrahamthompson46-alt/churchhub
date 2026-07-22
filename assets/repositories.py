"""
Persistence helpers for the assets domain.

Services own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from .models import (
    AssetAuditLog,
    AssetCategory,
    AssetCategoryTemplate,
    AssetDepreciationEntry,
    AssetMaintenanceLog,
    AssetPolicyAuditLog,
    DepreciationPolicy,
    FixedAsset,
)


def create_asset_audit(*, asset, action, user, notes=""):
    return AssetAuditLog.objects.create(
        asset=asset, action=action, user=user, notes=notes
    )


def create_policy_audit(
    *, church, action, user, target_label="", notes="", details=None
):
    return AssetPolicyAuditLog.objects.create(
        church=church,
        action=action,
        user=user,
        target_label=target_label,
        notes=notes,
        details=details or {},
    )


def update_or_create_template(*, code, defaults):
    return AssetCategoryTemplate.objects.update_or_create(
        code=code,
        defaults=defaults,
    )


def get_or_create_depreciation_policy(church):
    return DepreciationPolicy.objects.get_or_create(church=church)


def update_or_create_category(*, church, code, defaults):
    return AssetCategory.objects.update_or_create(
        church=church,
        code=code,
        defaults=defaults,
    )


def save_asset(asset, *, update_fields=None):
    if update_fields is not None:
        asset.save(update_fields=update_fields)
    else:
        asset.save()
    return asset


def update_or_create_depreciation_entry(*, asset, period_year, period_month, defaults):
    return AssetDepreciationEntry.objects.update_or_create(
        asset=asset,
        period_year=period_year,
        period_month=period_month,
        defaults=defaults,
    )


def save_maintenance_log(log):
    log.save()
    return log


def save_category(category):
    category.save()
    return category


def save_policy(policy):
    policy.save()
    return policy
