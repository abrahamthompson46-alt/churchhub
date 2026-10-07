"""In-app notifications for journals that need (or received) a checker."""

from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from accounts.models import User
from dashboard.services import notify_user, notify_users
from permissions.checks import can_approve_transactions
from permissions.scoping import get_manageable_churches


def _checkers_for_church(church, *, exclude_user=None):
    if church is None:
        return []
    exclude_id = getattr(exclude_user, "pk", None)
    qs = User.objects.filter(is_active=True, is_platform_user=False)
    district_id = getattr(church, "district_id", None)
    if district_id:
        qs = qs.filter(Q(church_id=church.pk) | Q(scope_district_id=district_id) | Q(church__district_id=district_id))
    else:
        qs = qs.filter(church_id=church.pk)
    recipients = []
    for user in qs.distinct():
        if exclude_id and user.pk == exclude_id:
            continue
        if not can_approve_transactions(user):
            continue
        if get_manageable_churches(user).filter(pk=church.pk).exists():
            recipients.append(user)
    return recipients


def notify_pending_journal(transaction):
    if transaction is None or getattr(transaction, "approval_status", "") != "PENDING":
        return []
    if getattr(transaction, "is_voided", False):
        return []
    church = transaction.church
    url = reverse("transactions:pending_approvals")
    recipients = _checkers_for_church(church, exclude_user=transaction.created_by)
    if not recipients:
        return []
    notify_users(
        recipients,
        f"Journal awaiting approval — {transaction.reference}",
        f"{transaction.description or transaction.transaction_type} needs a checker at {church.name}.",
        category="FINANCE",
        action_url=url,
        event_key=f"txn.pending.{transaction.pk}",
    )
    return recipients


def notify_journal_outcome(transaction, *, approved, actor=None):
    maker = getattr(transaction, "created_by", None)
    if not maker or not maker.is_active:
        return None
    actor_id = getattr(actor, "pk", None)
    if actor_id and maker.pk == actor_id:
        return None
    verb = "approved" if approved else "rejected"
    url = reverse("transactions:transaction_detail", args=[transaction.pk])
    return notify_user(
        maker,
        f"Transaction {verb}",
        f"{transaction.reference} was {verb}.",
        category="FINANCE",
        action_url=url,
        event_key=f"txn.{verb}.{transaction.pk}",
    )
