"""
Persistence helpers for the dashboard domain.

Services/views own authorization and call repositories for ORM writes.
Selectors own read querysets. Do not put KPI or role rules here.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import Notification


def create_notification(*, user, title, message, category="INFO", action_url=""):
    from church_system.perf_cache import invalidate_unread_notifications

    note = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        category=category,
        action_url=action_url,
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
