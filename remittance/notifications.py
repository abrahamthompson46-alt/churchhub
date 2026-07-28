"""In-app notifications for hierarchy remittance events."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from accounts.models import User
from dashboard.services import notify_users
from permissions.checks import can_manage_settlements, can_view_remittance


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
    from django.urls import reverse

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
    )
    return recipients


def notify_district_settlement_posted(batch, *, church):
    """Notify district when a church posts a settlement (ledger reclass, pre-cash)."""
    from django.urls import reverse

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
    )
    return recipients
