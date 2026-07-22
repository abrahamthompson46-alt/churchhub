"""
Persistence helpers for the remittance domain.

Services own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from .models import (
    RemittancePolicy,
    RemittancePolicyAuditLog,
    SettlementBatch,
    SettlementLine,
    WelfareAssistanceCase,
    WelfareCaseAttachment,
    WelfareContribution,
    WelfareMemberLedger,
)


def create_policy_audit(*, policy=None, action, changed_by, snapshot=None):
    return RemittancePolicyAuditLog.objects.create(
        policy=policy,
        action=action,
        changed_by=changed_by,
        snapshot=snapshot or {},
    )


def create_policy(**fields):
    return RemittancePolicy.objects.create(**fields)


def save_policy(policy):
    policy.full_clean()
    policy.save()
    return policy


def create_settlement_batch(**fields):
    return SettlementBatch.objects.create(**fields)


def save_settlement_batch(batch, *, update_fields=None):
    if update_fields is not None:
        batch.save(update_fields=update_fields)
    else:
        batch.save()
    return batch


def create_settlement_line(**fields):
    return SettlementLine.objects.create(**fields)


def create_welfare_contribution(**fields):
    return WelfareContribution.objects.create(**fields)


def save_welfare_contribution(contribution, *, update_fields=None):
    if update_fields is not None:
        contribution.save(update_fields=update_fields)
    else:
        contribution.save()
    return contribution


def delete_welfare_contribution(contribution):
    contribution.delete()


def create_member_ledger_entry(**fields):
    return WelfareMemberLedger.objects.create(**fields)


def update_ledger_for_contribution(contribution, *, description, entry_date):
    return WelfareMemberLedger.objects.filter(contribution=contribution).update(
        description=description[:255],
        entry_date=entry_date,
    )


def create_welfare_case(**fields):
    return WelfareAssistanceCase.objects.create(**fields)


def save_welfare_case(case, *, update_fields=None):
    if update_fields is not None:
        case.save(update_fields=update_fields)
    else:
        case.save()
    return case


def create_case_attachment(**fields):
    return WelfareCaseAttachment.objects.create(**fields)
