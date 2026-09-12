"""
Persistence helpers for the dashboard domain.

Services/views own authorization and call repositories for ORM writes.
Selectors own read querysets. Do not put KPI or role rules here.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import Notification


def create_notification(
    *,
    user,
    title,
    message,
    category="INFO",
    action_url="",
    severity="INFO",
    event_key="",
):
    from church_system.perf_cache import invalidate_unread_notifications

    key = (event_key or "").strip()[:120]
    if key:
        existing = (
            Notification.objects.filter(user=user, event_key=key, read=False)
            .order_by("-last_event_at", "-pk")
            .first()
        )
        if existing:
            existing.title = title
            existing.message = message
            existing.category = category
            existing.severity = severity
            existing.action_url = action_url
            existing.occurrence_count = (existing.occurrence_count or 1) + 1
            existing.last_event_at = timezone.now()
            existing.save(
                update_fields=[
                    "title",
                    "message",
                    "category",
                    "severity",
                    "action_url",
                    "occurrence_count",
                    "last_event_at",
                ]
            )
            invalidate_unread_notifications(user.pk)
            return existing

    note = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        category=category,
        action_url=action_url,
        severity=severity,
        event_key=key,
    )
    invalidate_unread_notifications(user.pk)
    return note


def mark_notification_read(notification):
    from church_system.perf_cache import invalidate_unread_notifications

    if not notification.read:
        notification.read = True
        notification.save(update_fields=["read"])
        invalidate_unread_notifications(notification.user_id)
    return notification


def mark_all_notifications_read(user):
    from church_system.perf_cache import invalidate_unread_notifications

    updated = Notification.objects.filter(user=user, read=False).update(read=True)
    invalidate_unread_notifications(user.pk)
    return updated


def delete_notification(notification):
    from church_system.perf_cache import invalidate_unread_notifications

    user_id = notification.user_id
    notification.delete()
    invalidate_unread_notifications(user_id)


def delete_old_read_notifications(*, older_than_days=90):
    cutoff = timezone.now() - timedelta(days=older_than_days)
    deleted, _ = Notification.objects.filter(read=True, created_at__lt=cutoff).delete()
    return deleted


def purge_aged_notifications(*, read_days=90, unread_days=180, dry_run=False):
    from django.db.models import Q

    now = timezone.now()
    read_cutoff = now - timedelta(days=read_days)
    unread_cutoff = now - timedelta(days=unread_days)
    qs = Notification.objects.filter(
        Q(read=True, created_at__lt=read_cutoff)
        | Q(read=False, created_at__lt=unread_cutoff)
    )
    count = qs.count()
    if dry_run:
        return count
    deleted, _ = qs.delete()
    return deleted
