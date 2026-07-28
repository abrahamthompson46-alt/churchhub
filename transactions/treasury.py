"""Cash position and teller daily console helpers."""

from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from transactions.models import Transaction, TransactionLine
from transactions.services import get_active_working_day, resolve_transaction_date


def get_cash_position(church):
    """
    Book balances for liquid accounts (approved, non-voided lines).
    Asset convention: debit-positive → balance = sum(amount).
    Single grouped query instead of four separate aggregates.
    """
    empty = {
        "cash": Decimal("0.00"),
        "bank": Decimal("0.00"),
        "petty_cash": Decimal("0.00"),
        "total_liquid": Decimal("0.00"),
        "business_date": None,
    }
    if not church:
        return empty

    rows = (
        TransactionLine.objects.filter(
            transaction__church=church,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__is_active=True,
        )
        .filter(Q(account__account_type__in=["CASH", "BANK"]) | Q(account__name="Petty Cash"))
        .values("account__account_type", "account__name")
        .annotate(t=Coalesce(Sum("amount"), Decimal("0.00")))
    )

    cash = Decimal("0.00")
    bank = Decimal("0.00")
    petty = Decimal("0.00")
    for row in rows:
        amount = row["t"] or Decimal("0.00")
        name = row["account__name"]
        acc_type = row["account__account_type"]
        if name == "Petty Cash":
            petty += amount
        elif acc_type == "BANK":
            bank += amount
        elif acc_type == "CASH":
            cash += amount

    return {
        "cash": cash,
        "bank": bank,
        "petty_cash": petty,
        "total_liquid": cash + bank + petty,
        "business_date": resolve_transaction_date(church),
    }


def get_teller_daily_summary(church, business_date=None):
    """Per-teller entry counts and totals for the church business date."""
    if not church:
        return {"business_date": None, "tellers": [], "totals": {}, "working_day_open": False}

    business_date = business_date or resolve_transaction_date(church)
    txns = (
        Transaction.objects.filter(
            church=church,
            date=business_date,
            is_voided=False,
        )
        .select_related("created_by")
        .prefetch_related("lines__account")
    )

    by_user = {}
    for txn in txns:
        uid = txn.created_by_id or 0
        if uid not in by_user:
            user = txn.created_by
            by_user[uid] = {
                "user_id": uid,
                "name": (user.get_full_name() or user.username) if user else "Unassigned",
                "entries": 0,
                "receipts": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "transfers": Decimal("0.00"),
                "pending": 0,
                "approved": 0,
            }
        row = by_user[uid]
        row["entries"] += 1
        amount = abs(txn.receipt_total or Decimal("0.00"))
        if txn.transaction_type == "RECEIPT":
            row["receipts"] += amount
        elif txn.transaction_type == "EXPENSE":
            row["expenses"] += amount
        else:
            row["transfers"] += amount
        if txn.approval_status == "PENDING":
            row["pending"] += 1
        elif txn.approval_status == "APPROVED":
            row["approved"] += 1

    tellers = sorted(by_user.values(), key=lambda r: (-r["entries"], r["name"]))
    totals = {
        "entries": sum(t["entries"] for t in tellers),
        "receipts": sum((t["receipts"] for t in tellers), Decimal("0.00")),
        "expenses": sum((t["expenses"] for t in tellers), Decimal("0.00")),
        "transfers": sum((t["transfers"] for t in tellers), Decimal("0.00")),
        "pending": sum(t["pending"] for t in tellers),
    }
    return {
        "business_date": business_date,
        "tellers": tellers,
        "totals": totals,
        "working_day_open": bool(get_active_working_day(church)),
    }
