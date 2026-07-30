"""Deadline reminder notifications and optional email for contribution campaigns."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from contributions import repositories as repo
from contributions import selectors
from dashboard.repositories import create_notification

User = get_user_model()

REMINDER_THRESHOLDS = (
    (7, "d7"),
    (3, "d3"),
    (1, "d1"),
    (0, "d0"),
)
OVERDUE_KEY = "overdue"


def _reminder_key_for_days(days: int) -> str | None:
    if days < 0:
        return OVERDUE_KEY
    for threshold, key in REMINDER_THRESHOLDS:
        if days == threshold:
            return key
    return None


def _reminder_message(campaign, days: int) -> tuple[str, str]:
    name = campaign.name
    deadline = campaign.deadline.strftime("%b %d, %Y")
    if days < 0:
        title = f"{name} — deadline passed"
        message = f"The deadline for {name} was {deadline}. View your history on the member portal."
    elif days == 0:
        title = f"{name} — due today"
        message = f"{name} closes today ({deadline})."
    elif days == 1:
        title = f"{name} — due tomorrow"
        message = f"Reminder: {name} deadline is tomorrow."
    else:
        title = f"{name} — {days} days left"
        message = f"Reminder: {name} deadline is in {days} days ({deadline})."
    return title, message


def _portal_action_url(campaign) -> str:
    return reverse("portal:contribution_campaign", kwargs={"pk": campaign.pk})


def _send_reminder_email(user, subject, text_body):
    if not user.email:
        return False
    from church_system.email_service import send_platform_email

    return send_platform_email(
        subject=subject,
        to=user.email,
        text_body=text_body,
        fail_silently=True,
    )


def deliver_campaign_reminder(campaign, user, reminder_key, *, send_email=False) -> bool:
    if repo.reminder_exists(campaign, user, reminder_key):
        return False
    days = campaign.days_until_deadline
    if days is None:
        return False
    title, message = _reminder_message(campaign, days if reminder_key != OVERDUE_KEY else -1)
    create_notification(
        user=user,
        title=title,
        message=message,
        category="FINANCE",
        action_url=_portal_action_url(campaign),
    )
    email_sent = False
    if send_email and campaign.send_email_reminders:
        email_sent = _send_reminder_email(user, title, message)
    repo.create_reminder_log(
        campaign,
        user,
        reminder_key,
        notification_sent=True,
        email_sent=email_sent,
    )
    return True


def ensure_portal_deadline_notifications(member) -> int:
    """Create in-app notifications for linked portal user on home visit."""
    if not member:
        return 0
    user = User.objects.filter(member=member, is_active=True).first()
    if not user:
        return 0
    sent = 0
    for campaign in selectors.open_portal_campaigns(member.church):
        days = campaign.days_until_deadline
        if days is None:
            continue
        key = _reminder_key_for_days(days)
        if not key:
            continue
        if deliver_campaign_reminder(campaign, user, key, send_email=False):
            sent += 1
    return sent


def send_all_deadline_reminders(*, include_email=True) -> dict:
    """Batch reminder dispatch for cron/scheduled tasks."""
    stats = {"campaigns": 0, "notifications": 0, "emails": 0}
    for campaign in selectors.open_campaigns_for_reminders():
        stats["campaigns"] += 1
        days = campaign.days_until_deadline
        if days is None:
            continue
        key = _reminder_key_for_days(days)
        if not key:
            continue
        users = User.objects.filter(
            is_active=True,
            member__church=campaign.church,
            member__is_deleted=False,
        ).select_related("member")
        for user in users:
            if repo.reminder_exists(campaign, user, key):
                continue
            if deliver_campaign_reminder(campaign, user, key, send_email=include_email):
                stats["notifications"] += 1
                log = campaign.deadline_reminders.filter(user=user, reminder_key=key).first()
                if log and log.email_sent:
                    stats["emails"] += 1
    return stats
