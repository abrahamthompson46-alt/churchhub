"""Church-scoped manual adjustment journals (corrections)."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from transactions import repositories as repo
from transactions.models import Account, Transaction

# Remittance payables / clearing — must use dedicated workflows, not open JV.
ADJUSTMENT_BLOCKED_ACCOUNT_TYPES = frozenset(
    {
        "TITHE_REMIT_PAYABLE",
        "COMBINED_REMIT_PAYABLE",
        "REMITTANCE_RECEIVABLE",
    }
)


def adjustment_account_queryset(church):
    """Active church accounts allowed on adjustment lines."""
    qs = Account.objects.filter(church=church, is_active=True).order_by("name")
    blocked = list(ADJUSTMENT_BLOCKED_ACCOUNT_TYPES)
    qs = qs.exclude(account_type__in=blocked)
    qs = qs.exclude(account_type="DISTRICT_PAYABLE", name__icontains="Remittance")
    return qs


def is_account_allowed_for_adjustment(account: Account) -> bool:
    if not account.is_active:
        return False
    if account.account_type in ADJUSTMENT_BLOCKED_ACCOUNT_TYPES:
        return False
    if account.account_type == "DISTRICT_PAYABLE" and "Remittance" in (account.name or ""):
        return False
    return True


def validate_adjustment_line(church, account, side: str, amount: Decimal) -> Decimal:
    if account.church_id != church.pk:
        raise ValueError(f"Account “{account.name}” does not belong to this church.")
    if not is_account_allowed_for_adjustment(account):
        raise ValueError(
            f"Account “{account.name}” cannot be used on adjustment journals. "
            "Use remittance or settlement workflows instead."
        )
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Line amount must be greater than zero.")
    side = (side or "").upper()
    if side not in {"DEBIT", "CREDIT"}:
        raise ValueError("Each line must be debit or credit.")
    return amount if side == "DEBIT" else -amount


def build_adjustment_draft(church, *, narration, entry_date, lines: list[dict]) -> dict:
    """
  lines: [{"account_id", "account_name", "side", "amount": str}, ...]
    """
    narration = (narration or "").strip()
    if len(narration) < 10:
        raise ValueError("Provide a clear reason (at least 10 characters).")

    from transactions.services import (
        PeriodLockedError,
        WorkingDayClosedError,
        assert_period_open,
        assert_working_day_allows_posting,
        resolve_transaction_date,
    )

    entry_date = entry_date or resolve_transaction_date(church)
    assert_period_open(church, entry_date)
    try:
        assert_working_day_allows_posting(church, entry_date)
    except WorkingDayClosedError as exc:
        raise WorkingDayClosedError(
            f"{exc} Open the working day for {entry_date:%d %b %Y} before preparing this journal."
        ) from exc

    if not lines or len(lines) < 2:
        raise ValueError("Enter at least two lines (debit and credit).")

    preview = []
    total = Decimal("0")
    for raw in lines:
        account_id = raw.get("account_id")
        account = Account.objects.filter(pk=account_id, church=church).first()
        if not account:
            raise ValueError("Invalid account selected.")
        signed = validate_adjustment_line(
            church, account, raw.get("side", ""), raw.get("amount")
        )
        total += signed
        preview.append(
            {
                "account_id": str(account.pk),
                "account_name": account.name,
                "side": raw.get("side", "").upper(),
                "amount": str(abs(signed)),
                "signed_amount": str(signed),
            }
        )

    if total != Decimal("0"):
        raise ValueError(
            f"Journal must balance. Debits and credits differ by ₵ {abs(total):.2f}."
        )

    return {
        "narration": narration,
        "date": entry_date.isoformat(),
        "lines": preview,
        "line_count": len(preview),
    }


@db_transaction.atomic
def post_adjustment_journal(church, user, draft, *, idempotency_key=None):
    from permissions.checks import can_create_adjustment_journals

    if not can_create_adjustment_journals(user):
        raise PermissionError("Adjustment journal permission required.")

    from transactions.idempotency import (
        IdempotencyReplay,
        MissingIdempotencyKey,
        claim_financial_idempotency,
        complete_financial_idempotency,
        normalize_idempotency_key,
    )
    from transactions.services import (
        PeriodLockedError,
        WorkingDayClosedError,
        _log_audit,
        _notify_pending_journal,
        assert_period_open,
        assert_working_day_allows_posting,
        validate_transaction_balance,
    )

    key = normalize_idempotency_key(idempotency_key)
    idem_record = None
    if key:
        try:
            idem_record = claim_financial_idempotency(church, user, "ADJUSTMENT", key)
        except IdempotencyReplay as replay:
            return replay.existing_transaction
    elif idempotency_key is not None:
        raise MissingIdempotencyKey(
            "Missing idempotency key. Refresh the page and try again."
        )

    from datetime import date as date_cls

    entry_date = date_cls.fromisoformat(draft["date"])
    assert_period_open(church, entry_date)
    assert_working_day_allows_posting(church, entry_date)

    narration = draft["narration"].strip()
    if len(narration) < 10:
        raise ValueError("Narration is required.")

    trx = repo.create_transaction(
        transaction_type="ADJUSTMENT",
        church=church,
        created_by=user,
        description=narration[:200],
        date=entry_date,
    )

    for line in draft["lines"]:
        account = Account.objects.get(pk=line["account_id"], church=church)
        signed = Decimal(line["signed_amount"])
        if not is_account_allowed_for_adjustment(account):
            raise ValueError(f"Account “{account.name}” is not allowed on adjustments.")
        repo.create_transaction_line(
            transaction=trx,
            account=account,
            amount=signed,
        )

    validate_transaction_balance(trx)
    _log_audit(
        church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "source": "adjustment_journal",
            "line_count": len(draft["lines"]),
            "accounts": [ln["account_name"] for ln in draft["lines"]],
        },
    )
    _notify_pending_journal(trx)

    if idem_record:
        complete_financial_idempotency(idem_record, trx)

    return trx