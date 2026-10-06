"""In-app notifications for hierarchy remittance and welfare events."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.urls import reverse

from accounts.models import User
from dashboard.services import notify_user, notify_users
from permissions.checks import (
    can_approve_welfare,
    can_manage_settlements,
    can_manage_welfare_cases,
    can_view_remittance,
)
from permissions.scoping import get_manageable_churches


def recipients_for_district(district):
    """Users who may view incoming remittances for a district."""
    if district is None:
        return []
    qs = (
        User.objects.filter(is_active=True, is_platform_user=False)
        .filter(Q(scope_district_id=district.pk) | Q(church__district_id=district.pk))
        .distinct()
    )
    return [u for u in qs if can_manage_settlements(u) or can_view_remittance(u)]


def _welfare_officers_for_church(church, *, exclude_user=None):
    if church is None:
        return []
    exclude_id = getattr(exclude_user, "pk", None)
    qs = User.objects.filter(is_active=True, is_platform_user=False)
    district_id = getattr(church, "district_id", None)
    if district_id:
        qs = qs.filter(Q(church_id=church.pk) | Q(scope_district_id=district_id))
    else:
        qs = qs.filter(church_id=church.pk)
    out = []
    for user in qs.distinct():
        if exclude_id and user.pk == exclude_id:
            continue
        if not (can_approve_welfare(user) or can_manage_welfare_cases(user)):
            continue
        if get_manageable_churches(user).filter(pk=church.pk).exists():
            out.append(user)
    return out


def _remittance_amount(transaction) -> Decimal:
    total = Decimal("0")
    for line in transaction.lines.select_related("account").all():
        if line.account.account_type in ("CASH", "BANK") and line.amount < 0:
            total += abs(line.amount)
    return total


def notify_district_remittance_payment_approved(transaction, *, approved_by):
    """
    Notify district-scoped officers when a church remittance payment is approved
    (cash/bank has left the church).
    """
    from transactions.models import FinancialAuditLog

    church = transaction.church
    district = getattr(church, "district", None)
    if district is None:
        return []
    if not FinancialAuditLog.objects.filter(
        transaction=transaction, action="REMIT", church=church
    ).exists():
        return []

    amount = _remittance_amount(transaction)
    if amount <= 0:
        return []

    recipients = recipients_for_district(district)
    if not recipients:
        return []

    url = reverse("remittance:settlements") + "?incoming=1"
    month_label = transaction.date.strftime("%B %Y")
    notify_users(
        recipients,
        f"Remittance received — {church.name}",
        f"{church.name} completed a district remittance payment of {amount:.2f} "
        f"for {month_label} (approved by {approved_by.get_full_name() or approved_by.username}).",
        category="FINANCE",
        action_url=url,
        event_key=f"remittance.payment.{transaction.pk}",
    )
    return recipients


def notify_district_settlement_posted(batch, *, church):
    """Notify district when a church posts a settlement (ledger reclass, pre-cash)."""
    if batch.status != "POSTED" or batch.from_unit_type != "CHURCH":
        return []
    district = getattr(church, "district", None)
    if district is None or str(batch.to_unit_id) != str(district.pk):
        return []

    recipients = recipients_for_district(district)
    if not recipients:
        return []

    url = reverse("remittance:settlements") + "?incoming=1"
    notify_users(
        recipients,
        f"Settlement posted — {church.name}",
        f"{church.name} posted {batch.get_offering_type_display()} settlement "
        f"({batch.period_start} to {batch.period_end}): gross {batch.gross_received:.2f}. "
        f"Await bank remittance payment for cash to leave the church.",
        category="FINANCE",
        action_url=url,
        event_key=f"settlement.posted.{batch.pk}",
    )
    return recipients


def notify_hierarchy_settlement_posted(batch):
    """Notify conference-scoped officers when a district batch posts."""
    from organization.models import Church, Conference

    if batch.status != "POSTED" or batch.from_unit_type != "DISTRICT":
        return []
    if batch.to_unit_type != "CONFERENCE":
        return []
    conference = Conference.objects.filter(pk=batch.to_unit_id).first()
    if conference is None:
        return []
    church_ids = Church.objects.filter(district__zone__conference_id=conference.pk).values_list(
        "pk", flat=True
    )
    qs = (
        User.objects.filter(is_active=True, is_platform_user=False)
        .filter(Q(scope_conference_id=conference.pk) | Q(church_id__in=list(church_ids)))
        .distinct()
    )
    recipients = [u for u in qs if can_manage_settlements(u) or can_view_remittance(u)]
    if not recipients:
        return []
    url = reverse("remittance:settlements") + "?incoming=1"
    notify_users(
        recipients,
        "District settlement posted",
        f"{batch.get_offering_type_display()} district settlement "
        f"({batch.period_start} to {batch.period_end}) posted: gross {batch.gross_received:.2f}.",
        category="FINANCE",
        action_url=url,
        event_key=f"settlement.posted.{batch.pk}",
    )
    return recipients


def notify_welfare_case_submitted(case):
    url = reverse("remittance:welfare_case_detail", args=[case.pk])
    recipients = _welfare_officers_for_church(case.church, exclude_user=case.created_by)
    if not recipients:
        return []
    notify_users(
        recipients,
        f"Welfare case {case.case_number}",
        f"{case.member.full_name} requested assistance at {case.church.name}.",
        category="INFO",
        action_url=url,
        event_key=f"welfare.pending.{case.pk}",
    )
    return recipients


def notify_welfare_case_resolved(case, *, approved):
    maker = case.created_by
    if not maker or not maker.is_active:
        return None
    verb = "approved" if approved else "rejected"
    url = reverse("remittance:welfare_case_detail", args=[case.pk])
    return notify_user(
        maker,
        f"Welfare case {verb}",
        f"{case.case_number} was {verb}.",
        category="INFO",
        action_url=url,
        event_key=f"welfare.{verb}.{case.pk}",
    )
