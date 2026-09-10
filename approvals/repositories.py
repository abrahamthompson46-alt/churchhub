"""Persistence for maker-checker cases."""

from __future__ import annotations

from approvals.models import (
    ApprovalCase,
    ApprovalDelegation,
    ApprovalEscalation,
    ApprovalPolicy,
    ApprovalStep,
)


def get_or_create_policy(*, church, defaults=None):
    return ApprovalPolicy.objects.get_or_create(church=church, defaults=defaults or {})


def save_policy(policy, *, update_fields):
    policy.save(update_fields=update_fields)
    return policy


def get_case_for_transaction(transaction):
    return ApprovalCase.objects.filter(transaction=transaction).first()


def create_case(**kwargs):
    return ApprovalCase.objects.create(**kwargs)


def create_step(**kwargs):
    return ApprovalStep.objects.create(**kwargs)


def lock_case(case_id):
    return ApprovalCase.objects.select_for_update().select_related("transaction", "church").get(pk=case_id)


def save_case(case, *, update_fields):
    case.save(update_fields=update_fields)
    return case


def save_step(step, *, update_fields):
    step.save(update_fields=update_fields)
    return step


def create_delegation(**kwargs):
    return ApprovalDelegation.objects.create(**kwargs)


def save_delegation(delegation, *, update_fields):
    delegation.save(update_fields=update_fields)
    return delegation


def create_escalation(**kwargs):
    return ApprovalEscalation.objects.create(**kwargs)
