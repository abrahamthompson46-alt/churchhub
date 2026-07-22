"""Guards against dual church→district remittance paths (cutoff bank vs settlement).

Both paths debit TITHE_REMIT_PAYABLE / COMBINED_REMIT_PAYABLE. Running both for the
same church and overlapping calendar month over-clears liability. These helpers
hard-gate the second path without removing either UI.
"""

from calendar import monthrange
from datetime import date

# Offerings cleared by both MonthlyCutoff bank remit and church settlement posts.
_PAYABLE_OFFERING_TYPES = ("TITHE", "COMBINED")


def month_start(value):
    return value.replace(day=1)


def month_end(value):
    last = monthrange(value.year, value.month)[1]
    return date(value.year, value.month, last)


def iter_month_starts(period_start, period_end):
    """Yield first-of-month dates overlapping [period_start, period_end] inclusive."""
    current = month_start(period_start)
    last = month_start(period_end)
    while current <= last:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def period_overlaps_month(period_start, period_end, month_date):
    start = month_start(month_date)
    end = month_end(month_date)
    return period_start <= end and period_end >= start


def bank_cutoff_remittance_active(church, month_date):
    """
    True when the MonthlyCutoff bank-remit path already remitted (or has a live
    pending/approved REMIT) for this church and calendar month.
    """
    from transactions.models import FinancialAuditLog, MonthlyCutoff

    month = month_start(month_date)
    cutoff = MonthlyCutoff.objects.filter(church=church, month=month).first()
    if cutoff is None:
        return False
    if cutoff.transferred:
        return True
    return (
        FinancialAuditLog.objects.filter(
            church=church,
            action="REMIT",
            details__cutoff_id=str(cutoff.pk),
        )
        .exclude(transaction__isnull=True)
        .exclude(transaction__approval_status="REJECTED")
        .exclude(transaction__is_voided=True)
        .exists()
    )


def posted_church_settlement_overlaps_month(church, month_date, offering_types=None):
    """True when a POSTED church SettlementBatch overlaps this calendar month."""
    from remittance import selectors

    offering_types = offering_types or _PAYABLE_OFFERING_TYPES
    month = month_start(month_date)
    end = month_end(month_date)
    return selectors.posted_church_settlement_overlaps(
        church, month, end, offering_types
    )


def assert_settlement_not_blocked_by_bank_remit(
    church, period_start, period_end, offering_type=None
):
    """Refuse settlement draft/post when cutoff bank remit already covers the period."""
    from remittance.services import RemittancePolicyError

    if offering_type and offering_type not in _PAYABLE_OFFERING_TYPES:
        return
    for month in iter_month_starts(period_start, period_end):
        if bank_cutoff_remittance_active(church, month):
            raise RemittancePolicyError(
                f"Cannot use settlement: district remittance already recorded for "
                f"{month.strftime('%B %Y')} via monthly cut-off / bank remittance."
            )


def assert_bank_remit_not_blocked_by_settlement(church, month_date):
    """Refuse bank remittance when a posted church settlement overlaps the month."""
    if posted_church_settlement_overlaps_month(church, month_date):
        label = month_start(month_date).strftime("%B %Y")
        raise ValueError(
            f"Cannot record bank remittance: a settlement batch is already posted "
            f"for this church covering {label}."
        )
