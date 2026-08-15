"""Idempotency protection for financial write operations.

INV-IDEM-01 / INV-IDEM-03 / CH-SEC-013:
- Completed keys replay the bound transaction (no duplicate effect).
- Incomplete keys are row-locked; concurrent callers serialize — they do not
  both execute financial work in parallel.
"""

from django.db import IntegrityError, transaction as db_transaction

from .models import FinancialIdempotencyKey, Transaction


class IdempotencyReplay(Exception):
    """Raised when a duplicate idempotency key is submitted."""

    def __init__(self, existing_transaction):
        self.existing_transaction = existing_transaction
        super().__init__("Duplicate financial submission.")


class IdempotencyInProgress(Exception):
    """Raised when another request holds an incomplete key (should be rare after lock wait)."""

    def __init__(self, record=None):
        self.record = record
        super().__init__(
            "This financial submission is already in progress. Wait and retry."
        )


def normalize_idempotency_key(raw_key):
    key = (raw_key or "").strip()
    if not key or len(key) > 64:
        return None
    return key


class MissingIdempotencyKey(ValueError):
    """Raised when a financial POST omits the required idempotency key."""


@db_transaction.atomic
def claim_financial_idempotency(church, user, action, idempotency_key):
    """
    Reserve an idempotency key for a financial action.

    Returns the FinancialIdempotencyKey record (new or locked incomplete owned
    by this serialized transaction).

    Raises:
        MissingIdempotencyKey: blank/invalid key
        IdempotencyReplay: key already completed with a transaction
    """
    key = normalize_idempotency_key(idempotency_key)
    if not key:
        raise MissingIdempotencyKey(
            "Missing idempotency key. Refresh the page and try again."
        )

    existing = (
        FinancialIdempotencyKey.objects.select_for_update()
        .filter(
            church=church,
            user=user,
            action=action,
            idempotency_key=key,
        )
        .select_related("transaction")
        .first()
    )
    if existing:
        if existing.transaction_id:
            raise IdempotencyReplay(existing.transaction)
        # Incomplete: this caller holds the row lock for the remainder of the
        # outer atomic block. A concurrent claim waits, then either replays or
        # continues only if still incomplete after the first commit.
        return existing

    try:
        return FinancialIdempotencyKey.objects.create(
            church=church,
            user=user,
            action=action,
            idempotency_key=key,
        )
    except IntegrityError:
        existing = (
            FinancialIdempotencyKey.objects.select_for_update()
            .filter(
                church=church,
                user=user,
                action=action,
                idempotency_key=key,
            )
            .select_related("transaction")
            .first()
        )
        if existing is None:
            raise IdempotencyInProgress() from None
        if existing.transaction_id:
            raise IdempotencyReplay(existing.transaction)
        return existing


def complete_financial_idempotency(record, transaction: Transaction):
    if not record:
        return
    record.transaction = transaction
    record.save(update_fields=["transaction"])
