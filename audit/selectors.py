"""Read helpers for enterprise audit (authorization stays in views/services)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from audit.models import AuditEvent
from church_system.church_scope import filter_by_church
from permissions.scoping import get_manageable_churches


def scoped_events_qs(user, request=None):
    """Events for churches the user may manage. Empty if none."""
    churches = get_manageable_churches(user)
    qs = AuditEvent.objects.select_related("actor", "church", "denomination").filter(
        church__in=churches
    )
    if request is not None:
        qs = filter_by_church(qs, request)
    return qs


def event_for_user(user, pk):
    return scoped_events_qs(user).filter(pk=pk).first()


def summary_counts(user, *, days=7, request=None):
    since = timezone.now() - timedelta(days=days)
    qs = scoped_events_qs(user, request=request).filter(occurred_at__gte=since)
    by_action = list(qs.values("action").annotate(total=Count("id")).order_by("-total")[:12])
    return {
        "days": days,
        "total": qs.count(),
        "by_action": by_action,
        "church_count": get_manageable_churches(user).count(),
    }
