"""Member-domain in-app notifications (transfers, visitor follow-up)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dashboard.services import notify_user, notify_users
from permissions.checks import can_manage_members, can_process_transfers, can_view_members
from permissions.scoping import get_manageable_churches


def _users_for_church(church, *checkers):
    if church is None:
        return []
    qs = User.objects.filter(is_active=True, is_platform_user=False)
    district_id = getattr(church, "district_id", None)
    if district_id:
        qs = qs.filter(Q(church_id=church.pk) | Q(scope_district_id=district_id))
    else:
        qs = qs.filter(church_id=church.pk)
    out = []
    for user in qs.distinct():
        if checkers and not any(fn(user) for fn in checkers):
            continue
        if get_manageable_churches(user).filter(pk=church.pk).exists():
            out.append(user)
    return out


def notify_transfer_requested(transfer):
    church = transfer.to_church
    url = reverse("members:transfer_detail", args=[transfer.pk])
    recipients = _users_for_church(church, can_process_transfers)
    notify_users(
        recipients,
        f"Transfer request — {transfer.member.full_name}",
        f"{transfer.from_church.name} requested a transfer in to {church.name}.",
        category="INFO",
        action_url=url,
        event_key=f"transfer.pending.{transfer.pk}",
    )
    return recipients


def notify_transfer_resolved(transfer, *, completed):
    requester = transfer.requested_by
    if not requester or not requester.is_active:
        return None
    verb = "completed" if completed else "rejected"
    url = reverse("members:transfer_detail", args=[transfer.pk])
    return notify_user(
        requester,
        f"Transfer {verb}",
        f"{transfer.member.full_name} transfer was {verb}.",
        category="INFO",
        action_url=url,
        event_key=f"transfer.{verb}.{transfer.pk}",
    )


def remind_stale_visitor_follow_ups(*, stale_days=14):
    """Notify clerks/pastors about visitors still open after stale_days."""
    from members.models import Visitor, VisitorFollowUpStatus

    cutoff = timezone.localdate() - timedelta(days=stale_days)
    open_statuses = (
        VisitorFollowUpStatus.NEW,
        VisitorFollowUpStatus.CONTACTED,
        VisitorFollowUpStatus.IN_PROGRESS,
    )
    visitors = Visitor.objects.filter(
        follow_up_status__in=open_statuses,
        visit_date__lte=cutoff,
    ).select_related("church")
    notified = 0
    by_church = {}
    for visitor in visitors:
        by_church.setdefault(visitor.church_id, {"church": visitor.church, "count": 0})
        by_church[visitor.church_id]["count"] += 1
    url = reverse("members:visitor_list")
    for row in by_church.values():
        church = row["church"]
        recipients = _users_for_church(church, can_manage_members, can_view_members)
        if not recipients:
            continue
        notify_users(
            recipients,
            f"Visitor follow-up overdue — {church.name}",
            f"{row['count']} visitor(s) still need follow-up (visited {stale_days}+ days ago).",
            category="INFO",
            action_url=url,
            event_key=f"visitors.stale.{church.pk}.{timezone.localdate().isoformat()}",
        )
        notified += len(recipients)
    return {"churches": len(by_church), "notified": notified}
