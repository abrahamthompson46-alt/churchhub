"""
Persistence helpers for the ledger posting-template domain.

Services own business rules. LedgerCategory writes live here.
Account / Transaction persistence delegates to transactions.repositories —
the transactions app remains the books of record.
"""

from __future__ import annotations

from transactions import repositories as txn_repo
from transactions.models import Account

from .models import LedgerCategory


def deactivate_categories_for_church(church):
    """Soft-deactivate so historical Transaction.ledger_category FKs stay valid."""
    return LedgerCategory.objects.filter(church=church).update(is_active=False)


def update_or_create_category(*, church, code, defaults):
    return LedgerCategory.objects.update_or_create(
        church=church,
        code=code,
        defaults=defaults,
    )


def create_category(**fields):
    category = LedgerCategory(**fields)
    category.full_clean()
    category.save()
    return category


def save_category(category, *, update_fields=None):
    if update_fields is not None:
        category.save(update_fields=update_fields)
    else:
        category.save()
    return category


def get_or_create_account(*, church, name, defaults):
    """Match Account.objects.get_or_create (defaults apply on create only)."""
    return Account.objects.get_or_create(
        church=church,
        name=name,
        defaults=defaults,
    )


def create_account(*, church, name, account_type, code="", is_active=True):
    return txn_repo.create_account(
        church=church,
        name=name,
        account_type=account_type,
        code=code,
        is_active=is_active,
    )


def save_account(account, *, update_fields=None):
    if update_fields is not None:
        return txn_repo.save_account_fields(account, update_fields=update_fields)
    account.full_clean()
    account.save()
    return account


def create_ledger_transaction(**fields):
    """Create a PENDING journal header in transactions (books of record)."""
    return txn_repo.create_transaction(**fields)
