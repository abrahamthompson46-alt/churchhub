"""Denomination profile helpers, seeding, and terminology resolution."""

from django.db import transaction

from sitecontrol import repositories as repo
from sitecontrol.denomination_defaults import BUILTIN_DENOMINATIONS, DEFAULT_LEVEL_LABELS


def merge_hierarchy_labels(custom=None):
    base = {k: dict(v) for k, v in DEFAULT_LEVEL_LABELS.items()}
    if custom:
        for key, values in custom.items():
            if key in base and isinstance(values, dict):
                base[key].update(values)
    return base


def get_level_label(denomination, level_key, *, plural=False):
    labels = merge_hierarchy_labels(denomination.hierarchy_labels if denomination else None)
    level = labels.get(level_key, {})
    if not level.get("enabled", True):
        return ""
    if plural:
        return level.get("label_plural") or level.get("label", level_key.replace("_", " ").title())
    return level.get("label", level_key.replace("_", " ").title())


def level_enabled(denomination, level_key):
    if not denomination:
        return True
    labels = merge_hierarchy_labels(denomination.hierarchy_labels)
    return labels.get(level_key, {}).get("enabled", True)


def get_terminology_context(denomination):
    if not denomination:
        denomination = None
    keys = (
        "general_conference",
        "union",
        "conference",
        "zone",
        "district",
        "church",
    )
    labels = {}
    labels_plural = {}
    enabled = {}
    for key in keys:
        labels[key] = get_level_label(denomination, key)
        labels_plural[key] = get_level_label(denomination, key, plural=True)
        enabled[key] = level_enabled(denomination, key)
    return {
        "labels": labels,
        "labels_plural": labels_plural,
        "levels_enabled": enabled,
    }


def apply_seed_config_to_church(church, denomination):
    """Apply denomination-specific financial seeds when a church is created."""
    if not denomination:
        return
    config = denomination.seed_config or {}
    from transactions.models import OfferingCategory
    from transactions.services import create_default_accounts, create_default_offering_categories

    create_default_accounts(church)
    create_default_offering_categories(church)

    for item in config.get("offering_categories", []):
        repo.update_offering_category_names(
            church=church,
            code=item["code"],
            name=item.get("name", item["code"]),
        )

    if config.get("enable_remittance", True) and denomination.feature_remittance:
        from remittance.services import ensure_default_policies_for_church

        ensure_default_policies_for_church(church)

    if config.get("enable_payroll", True) and denomination.feature_payroll:
        from payroll.services import ensure_payroll_defaults_for_church

        ensure_payroll_defaults_for_church(church)

    if denomination.feature_ledger:
        from ledger.services import seed_ledger

        seed_ledger(church)

    if denomination.feature_assets:
        from assets.services import ensure_asset_defaults_for_church

        ensure_asset_defaults_for_church(church)


@transaction.atomic
def ensure_builtin_denominations():
    created = []
    for spec in BUILTIN_DENOMINATIONS:
        obj, was_created = repo.update_or_create_denomination(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "display_name": spec.get("display_name", spec["name"]),
                "tagline": spec.get("tagline", ""),
                "hierarchy_labels": merge_hierarchy_labels(spec.get("hierarchy_labels")),
                "seed_config": spec.get("seed_config", {}),
                "allow_public_registration": spec.get("allow_public_registration", True),
                "is_default": spec.get("is_default", False),
                "is_active": True,
            },
        )
        if was_created:
            created.append(obj)
    return created


def hierarchy_chain_description(denomination):
    keys = (
        "general_conference",
        "union",
        "conference",
        "zone",
        "district",
        "church",
    )
    parts = [get_level_label(denomination, key) for key in keys if level_enabled(denomination, key)]
    return " → ".join(parts) if parts else "Church"


def assign_orphan_conferences_to_default():
    from sitecontrol.models import Denomination

    default = Denomination.get_default()
    if not default:
        return 0
    return repo.assign_orphan_conferences_to_denomination(default)
