"""
Persistence helpers for the budgets planning UI.

Budget rows and financial audit logs live in the transactions app (SoR).
Services own validation, variance, and delete guards; this module writes only.
"""

from __future__ import annotations

from transactions import repositories as txn_repo


def save_budget(budget, *, update_fields=None):
    if update_fields is not None:
        budget.save(update_fields=update_fields)
    else:
        budget.save()
    return budget


def delete_budget(budget):
    budget.delete()


def create_budget_audit(*, church, action, user, details=None):
    return txn_repo.create_audit_log(
        church=church,
        action=action,
        user=user,
        details=details or {},
    )
