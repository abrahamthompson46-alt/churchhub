"""
ORM safety helpers.

Never annotate a queryset with the same name as a model @property.
Django tries to set annotated values on the instance and raises:
  AttributeError: property 'X' of 'Model' object has no setter

Prefer suffixes: *_total, *_annotated, search_name, etc.
"""

from __future__ import annotations

# Known property names that must not be used as annotate aliases.
FORBIDDEN_ANNOTATE_ALIASES = frozenset({
    "full_name",      # Member.full_name
    "member_count",   # Family.member_count
})


def assert_safe_annotate_alias(alias: str) -> None:
    if alias in FORBIDDEN_ANNOTATE_ALIASES:
        raise ValueError(
            f"Annotate alias '{alias}' clashes with a model @property. "
            f"Use a different name (e.g. members_total, search_name)."
        )
