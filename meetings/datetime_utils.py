"""Timezone helpers for meeting datetimes (datetime-local forms, dashboard display)."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Return an aware datetime in the current timezone; pass through aware values."""
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def format_local_datetime(dt: datetime | None, fmt: str) -> str:
    """Safe strftime for meeting timestamps stored with or without tzinfo."""
    if dt is None:
        return ""
    return timezone.localtime(ensure_aware(dt)).strftime(fmt)