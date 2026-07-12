"""Idempotency protection for financial write operations."""

from django.db import IntegrityError, transaction as db_transaction

from .models import FinancialIdempotencyKey, Transaction


class IdempotencyReplay(Exception):
    """Raised when a duplicate idempotency key is submitted."""

    def __init__(self, existing_transaction):
        self.existing_transaction = existing_transaction
        super().__init__("Duplicate financial submission.")


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
    Returns the FinancialIdempotencyKey record (new or existing incomplete).
    Raises IdempotencyReplay if the action already completed.
    """
    key = normalize_idempotency_key(idempotency_key)
    if not key:
        raise MissingIdempotencyKey(
            "Missing idempotency key. Refresh the page and try again."
        )

    existing = FinancialIdempotencyKey.objects.filter(
        church=church,
        user=user,
        action=action,
        idempotency_key=key,
    ).select_related("transaction").first()
    if existing:
        if existing.transaction_id:
            raise IdempotencyReplay(existing.transaction)
        return existing

    try:
        return FinancialIdempotencyKey.objects.create(
            church=church,
            user=user,
            action=action,
            idempotency_key=key,
        )
    except IntegrityError:
        existing = FinancialIdempotencyKey.objects.filter(
            church=church,
            user=user,
            action=action,
            idempotency_key=key,
        ).select_related("transaction").first()
        if existing and existing.transaction_id:
            raise IdempotencyReplay(existing.transaction)
        return existing


def complete_financial_idempotency(record, transaction: Transaction):
    if not record:
        return
    record.transaction = transaction
    record.save(update_fields=["transaction"])
