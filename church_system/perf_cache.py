"""Shared Redis/LocMem cache helpers for performance-sensitive reads.

Invalidation is intentional and narrow — never cache books-of-record
without church + as-of-date keys and clear invalidation hooks.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.core.cache import cache

CACHE_VERSION = getattr(settings, "CACHE_VERSION", 1)


def _v(key: str) -> str:
    return f"v{CACHE_VERSION}:{key}"


def dash_financial_key(church_id, year: int, month: int) -> str:
    return _v(f"dash:fin:{church_id}:{year:04d}-{month:02d}")


def dash_exec_key(user_id, scope_hash: str, year: int, month: int) -> str:
    return _v(f"dash:exec:{user_id}:{scope_hash}:{year:04d}-{month:02d}")


def giving_leaders_key(church_id, year: int | None) -> str:
    y = year if year is not None else "all"
    return _v(f"giving:leaders:{church_id}:{y}")


def notif_unread_key(user_id) -> str:
    return _v(f"notif:unread:{user_id}")


def perm_role_key(role: str, codename: str) -> str:
    return _v(f"perm:role:{role}:{codename}")


def scope_hash_for_church_ids(church_ids) -> str:
    raw = ",".join(str(pk) for pk in sorted(church_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_get(key: str) -> Any:
    return cache.get(key)


def cache_set(key: str, value: Any, timeout: int | None = None) -> None:
    if timeout is None:
        timeout = getattr(settings, "CACHE_DEFAULT_TIMEOUT", 300)
    cache.set(key, value, timeout)


def cache_delete(*keys: str) -> None:
    for key in keys:
        cache.delete(key)


def invalidate_church_finance_caches(church_id, *, year: int | None = None, month: int | None = None) -> None:
    """Drop dashboard MTD + giving leaderboard caches for a church."""
    from django.utils import timezone

    now = timezone.localdate()
    y = year or now.year
    m = month or now.month
    cache_delete(
        dash_financial_key(church_id, y, m),
        giving_leaders_key(church_id, y),
        giving_leaders_key(church_id, None),
    )


def invalidate_permission_role_cache(role: str | None = None, codename: str | None = None) -> None:
    """Delete cached matrix grant(s). Prefer role+codename; role-only clears nothing without pattern support."""
    if role and codename:
        cache_delete(perm_role_key(role, codename))


def invalidate_unread_notifications(user_id) -> None:
    cache_delete(notif_unread_key(user_id))
