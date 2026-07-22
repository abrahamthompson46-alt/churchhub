"""
Persistence helpers for the announcements / communications domain.

Services own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put visibility or approval rules here.
"""

from __future__ import annotations

from .models import Announcement, AnnouncementAuditLog, AnnouncementView


def create_audit_log(*, announcement=None, church=None, action, performed_by=None, details=None):
    return AnnouncementAuditLog.objects.create(
        announcement=announcement,
        church=church,
        action=action,
        performed_by=performed_by,
        details=details or {},
    )


def save_announcement(announcement, *, update_fields=None):
    if update_fields is not None:
        announcement.save(update_fields=update_fields)
    else:
        announcement.save()
    return announcement


def create_announcement_instance(**fields):
    ann = Announcement(**fields)
    ann.full_clean()
    ann.save()
    return ann


def get_or_create_announcement_view(*, user, announcement):
    return AnnouncementView.objects.get_or_create(user=user, announcement=announcement)


def save_image_formset(formset):
    """Persist inline AnnouncementImage formset (create/update/delete)."""
    return formset.save()
