"""In-app notifications for new portal spiritual submissions."""

from __future__ import annotations

from django.db.models import Q

from accounts.models import User
from dashboard.services import notify_users
from permissions.checks import can_view_portal_submissions


def pastoral_inbox_recipients_for_church(church):
    """Active staff users who may view portal submissions for this church."""
    from permissions.scoping import get_manageable_churches

    if church is None:
        return []
    recipients = []
    candidates = User.objects.filter(is_active=True, is_platform_user=False).only(
        "pk", "church_id", "role", "is_superuser"
    )
    for user in candidates:
        if not can_view_portal_submissions(user):
            continue
        if get_manageable_churches(user).filter(pk=church.pk).exists():
            recipients.append(user)
    return recipients


def notify_pastoral_team_new_submission(submission):
    from django.urls import reverse

    from portal.models import SpiritualSubmissionKind

    church = submission.church
    recipients = pastoral_inbox_recipients_for_church(church)
    if not recipients:
        return []

    kind_label = submission.get_kind_display()
    if submission.kind == SpiritualSubmissionKind.PRAYER and submission.is_anonymous:
        who = "A member (anonymous)"
    elif submission.member_id:
        who = submission.member.full_name
    else:
        who = "A member"

    url = reverse("portal:staff_submissions")
    if submission.kind == SpiritualSubmissionKind.PRAYER:
        url += "?kind=PRAYER&status=NEW"
    else:
        url += "?kind=THANKSGIVING&status=NEW"

    notify_users(
        recipients,
        f"New {kind_label} — {church.name}",
        f"{who} shared a {kind_label.lower()} via the member portal.",
        category="INFO",
        action_url=url,
    )
    return recipients
