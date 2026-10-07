"""In-app notifications for announcement pending / approve / reject."""

from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from accounts.models import User
from dashboard.services import notify_user, notify_users
from permissions.checks import can_approve_announcements
from permissions.scoping import get_manageable_churches


def notify_announcement_pending(announcement):
    if announcement is None or announcement.is_approved or announcement.is_rejected:
        return []
    church = announcement.church
    url = reverse("announcements:pending_approvals")
    qs = User.objects.filter(is_active=True, is_platform_user=False)
    if church is not None:
        district_id = getattr(church, "district_id", None)
        if district_id:
            qs = qs.filter(Q(church_id=church.pk) | Q(scope_district_id=district_id))
        else:
            qs = qs.filter(church_id=church.pk)
    else:
        qs = qs.filter(is_active=True)
    recipients = []
    exclude_id = getattr(announcement.created_by, "pk", None)
    for user in qs.distinct():
        if exclude_id and user.pk == exclude_id:
            continue
        if not can_approve_announcements(user):
            continue
        if church is not None and not get_manageable_churches(user).filter(pk=church.pk).exists():
            continue
        from announcements.services import can_approve_announcement

        if not can_approve_announcement(user, announcement):
            continue
        recipients.append(user)
    if not recipients:
        return []
    notify_users(
        recipients,
        f"Announcement awaiting approval — {announcement.title}",
        "A new announcement is waiting in the approval queue.",
        category="INFO",
        action_url=url,
        event_key=f"announcement.pending.{announcement.pk}",
    )
    return recipients


def notify_announcement_outcome(announcement, *, approved, actor=None, reason=""):
    maker = getattr(announcement, "created_by", None)
    if not maker or not maker.is_active:
        return None
    actor_id = getattr(actor, "pk", None)
    if actor_id and maker.pk == actor_id:
        return None
    verb = "approved" if approved else "rejected"
    url = reverse("announcements:announcement_detail", args=[announcement.pk]) if approved else ""
    message = f'Your announcement "{announcement.title}" was {verb}.'
    if reason and not approved:
        message = f'{message} Reason: {reason}'
    return notify_user(
        maker,
        f"Announcement {verb}",
        message,
        category="INFO",
        action_url=url,
        event_key=f"announcement.{verb}.{announcement.pk}",
    )
