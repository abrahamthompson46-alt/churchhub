"""Persistence for enterprise audit events."""

from __future__ import annotations

from audit.models import AuditEvent


def create_audit_event(**kwargs):
    return AuditEvent.objects.create(**kwargs)


def last_event_for_church(church_id, *, lock=False):
    qs = AuditEvent.objects.filter(church_id=church_id).order_by("-occurred_at", "-id")
    if lock:
        qs = qs.select_for_update()
    return qs.first()
