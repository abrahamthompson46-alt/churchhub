"""Maker-checker façade. Journal posting stays in transactions.services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.utils import timezone

from approvals import repositories as repo
from approvals import selectors
from approvals.models import ApprovalCase, ApprovalStep
from audit.services import emit_event
from permissions.checks import can_void_transactions
from permissions.org_scope import church_in_user_scope
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches
from permissions.services import user_has_permission
from permissions.superadmin import is_superadmin
from transactions.services import approve_transaction, reject_transaction, void_transaction

logger = logging.getLogger(__name__)


def _journal_amount(txn) -> Decimal:
    positives = [line.amount for line in txn.lines.all() if line.amount and line.amount > 0]
    if positives:
        return sum(positives, Decimal("0.00"))
    return abs(Decimal(str(txn.receipt_total or 0)))


def _emit(action, *, actor, church, txn=None, case=None, after=None):
    try:
        emit_event(
            domain="finance",
            action=action,
            actor=actor,
            church=church,
            object_type="approvals.ApprovalCase" if case else "transactions.Transaction",
            object_id=str(case.pk if case else getattr(txn, "pk", "") or ""),
            object_label=getattr(txn, "reference", "") or "",
            after=after or {},
            source="approvals",
            source_id=str(case.pk if case else ""),
        )
    except Exception:
        logger.exception("Failed to emit approval audit event action=%s", action)


def get_or_create_policy(church):
    policy, _created = repo.get_or_create_policy(church=church, defaults={"required_steps": 1})
    if not policy.required_steps or policy.required_steps < 1:
        policy.required_steps = 1
        repo.save_policy(policy, update_fields=["required_steps"])
    return policy


def ensure_case(transaction):
    """Open a case for a PENDING journal. Snapshot step count; default is one checker."""
    existing = repo.get_case_for_transaction(transaction)
    if existing:
        return existing
    if transaction.approval_status != "PENDING":
        return None
    policy = get_or_create_policy(transaction.church)
    steps = policy.required_steps if policy.is_active else 1
    steps = max(1, min(int(steps), 5))
    denomination = getattr(transaction.church, "denomination", None)
    case = repo.create_case(
        church=transaction.church,
        denomination=denomination,
        transaction=transaction,
        maker=transaction.created_by,
        required_steps=steps,
        current_step=1,
        status=ApprovalCase.STATUS_OPEN,
    )
    for number in range(1, steps + 1):
        repo.create_step(case=case, step_number=number)
    return case


def _blocked_approver_role(user) -> bool:
    return getattr(user, "role", None) == UserRole.DISTRICT_PASTOR


def _valid_delegation(user, church, amount: Decimal) -> bool:
    if not church_in_user_scope(user, church):
        return False
    for row in selectors.active_delegations_for_grantee(user, church):
        if not user_has_permission(row.grantor, "approve_transactions"):
            continue
        if not church_in_user_scope(row.grantor, church):
            continue
        if row.max_amount is not None and amount > Decimal(str(row.max_amount)):
            continue
        return True
    return False


def actor_may_decide(user, transaction) -> bool:
    """Approve/reject/correct/escalate authority. Not posting. District Admin never qualifies."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not transaction or not transaction.church_id:
        return False
    if not get_manageable_churches(user).filter(pk=transaction.church_id).exists():
        return False
    if not church_in_user_scope(user, transaction.church):
        return False
    if _blocked_approver_role(user):
        return False
    if is_superadmin(user):
        return True
    if user_has_permission(user, "approve_transactions"):
        return True
    return _valid_delegation(user, transaction.church, _journal_amount(transaction))


def actor_may_void(user, transaction) -> bool:
    if not user or not transaction or not transaction.church_id:
        return False
    if _blocked_approver_role(user):
        return False
    if not church_in_user_scope(user, transaction.church):
        return False
    if not get_manageable_churches(user).filter(pk=transaction.church_id).exists():
        return False
    return can_void_transactions(user)


@dataclass
class ApprovalOutcome:
    posted: bool
    case: object
    transaction: object
    message: str


@db_transaction.atomic
def record_approval(transaction, user, notes=""):
    if not actor_may_decide(user, transaction):
        raise PermissionDenied
    case = ensure_case(transaction)
    if case is None:
        raise ValueError("Transaction is not pending approval.")
    locked_case = repo.lock_case(case.pk)
    txn = locked_case.transaction
    if txn.created_by_id == user.id and not is_superadmin(user):
        raise ValueError("Creator cannot approve their own transaction.")
    if locked_case.status not in {ApprovalCase.STATUS_OPEN, ApprovalCase.STATUS_CORRECTION, ApprovalCase.STATUS_ESCALATED}:
        raise ValueError("Approval case is not open.")
    step = locked_case.steps.filter(
        step_number=locked_case.current_step, status=ApprovalStep.STATUS_PENDING
    ).first()
    if step is None:
        raise ValueError("No pending approval step.")
    now = timezone.now()
    step.status = ApprovalStep.STATUS_COMPLETED
    step.action = ApprovalStep.ACTION_APPROVE
    step.actor = user
    step.notes = notes or ""
    step.decided_at = now
    repo.save_step(step, update_fields=["status", "action", "actor", "notes", "decided_at"])
    is_final = locked_case.current_step >= locked_case.required_steps
    if not is_final:
        locked_case.current_step = locked_case.current_step + 1
        locked_case.status = ApprovalCase.STATUS_OPEN
        repo.save_case(locked_case, update_fields=["current_step", "status", "updated_at"])
        _emit(
            "approval.step",
            actor=user,
            church=txn.church,
            txn=txn,
            case=locked_case,
            after={
                "step": locked_case.current_step - 1,
                "required_steps": locked_case.required_steps,
                "posted": False,
            },
        )
        txn.refresh_from_db()
        return ApprovalOutcome(
            posted=False,
            case=locked_case,
            transaction=txn,
            message=f"Step {locked_case.current_step - 1} of {locked_case.required_steps} recorded. Journal remains pending.",
        )
    posted = approve_transaction(txn, user)
    locked_case.status = ApprovalCase.STATUS_APPROVED
    repo.save_case(locked_case, update_fields=["status", "updated_at"])
    _emit(
        "approval.decide",
        actor=user,
        church=posted.church,
        txn=posted,
        case=locked_case,
        after={"posted": True, "step": locked_case.required_steps},
    )
    return ApprovalOutcome(
        posted=True,
        case=locked_case,
        transaction=posted,
        message=f"{posted.reference} approved.",
    )


@db_transaction.atomic
def record_rejection(transaction, user, reason=""):
    if not actor_may_decide(user, transaction):
        raise PermissionDenied
    case = ensure_case(transaction)
    rejected = reject_transaction(transaction, user, reason=reason)
    if case:
        locked_case = repo.lock_case(case.pk)
        step = locked_case.steps.filter(step_number=locked_case.current_step).first()
        if step and step.status == ApprovalStep.STATUS_PENDING:
            step.status = ApprovalStep.STATUS_COMPLETED
            step.action = ApprovalStep.ACTION_REJECT
            step.actor = user
            step.notes = reason or ""
            step.decided_at = timezone.now()
            repo.save_step(
                step, update_fields=["status", "action", "actor", "notes", "decided_at"]
            )
        locked_case.status = ApprovalCase.STATUS_REJECTED
        repo.save_case(locked_case, update_fields=["status", "updated_at"])
        _emit(
            "approval.reject",
            actor=user,
            church=rejected.church,
            txn=rejected,
            case=locked_case,
            after={"reason": reason or ""},
        )
    return rejected


@db_transaction.atomic
def record_void(transaction, user, reason=""):
    if not actor_may_void(user, transaction):
        raise PermissionDenied
    return void_transaction(transaction, user, reason=reason)


@db_transaction.atomic
def request_correction(transaction, user, note=""):
    if not actor_may_decide(user, transaction):
        raise PermissionDenied
    if transaction.created_by_id == user.id and not is_superadmin(user):
        raise ValueError("Creator cannot request correction on their own transaction.")
    if transaction.approval_status != "PENDING":
        raise ValueError("Only pending journals can be sent for correction.")
    case = ensure_case(transaction)
    if case is None:
        raise ValueError("No open approval case.")
    locked_case = repo.lock_case(case.pk)
    locked_case.status = ApprovalCase.STATUS_CORRECTION
    locked_case.correction_note = (note or "")[:4000]
    repo.save_case(locked_case, update_fields=["status", "correction_note", "updated_at"])
    txn = locked_case.transaction
    if txn.approval_status != "PENDING":
        raise ValueError("Transaction approval status must remain PENDING.")
    _emit(
        "approval.correct",
        actor=user,
        church=txn.church,
        txn=txn,
        case=locked_case,
        after={"note": locked_case.correction_note, "approval_status": txn.approval_status},
    )
    return locked_case


@db_transaction.atomic
def escalate_case(transaction, user, reason=""):
    if not actor_may_decide(user, transaction):
        raise PermissionDenied
    if not (reason or "").strip():
        raise ValueError("Escalation requires a reason.")
    case = ensure_case(transaction)
    if case is None:
        raise ValueError("No open approval case.")
    locked_case = repo.lock_case(case.pk)
    txn = locked_case.transaction
    if txn.approval_status != "PENDING":
        raise ValueError("Only pending journals can be escalated.")
    repo.create_escalation(case=locked_case, requested_by=user, reason=reason.strip())
    locked_case.status = ApprovalCase.STATUS_ESCALATED
    repo.save_case(locked_case, update_fields=["status", "updated_at"])
    txn.refresh_from_db()
    if txn.approval_status != "PENDING":
        raise ValueError("Escalation must not change journal approval status.")
    _emit(
        "approval.escalate",
        actor=user,
        church=txn.church,
        txn=txn,
        case=locked_case,
        after={"reason": reason.strip(), "auto_approved": False},
    )
    return locked_case


def create_delegation(*, grantor, grantee, church, valid_from, valid_until, max_amount=None):
    if not user_has_permission(grantor, "manage_approval_delegations"):
        raise PermissionDenied
    if not user_has_permission(grantor, "approve_transactions"):
        raise PermissionDenied
    if not church_in_user_scope(grantor, church):
        raise PermissionDenied
    if getattr(grantee, "role", None) == UserRole.DISTRICT_PASTOR:
        raise ValueError("District Administrator cannot receive approval delegation.")
    if not church_in_user_scope(grantee, church):
        raise ValueError("Grantee is outside the church scope.")
    if valid_until < valid_from:
        raise ValueError("Delegation end date must be on or after the start date.")
    row = repo.create_delegation(
        grantor=grantor,
        grantee=grantee,
        church=church,
        denomination=getattr(church, "denomination", None),
        permission_codename="approve_transactions",
        valid_from=valid_from,
        valid_until=valid_until,
        max_amount=max_amount,
    )
    _emit(
        "approval.delegate",
        actor=grantor,
        church=church,
        after={
            "grantee_id": str(grantee.pk),
            "valid_from": str(valid_from),
            "valid_until": str(valid_until),
            "max_amount": str(max_amount) if max_amount is not None else "",
        },
    )
    return row


def revoke_delegation(delegation, user):
    if delegation.grantor_id != user.id and not is_superadmin(user):
        if not user_has_permission(user, "manage_approval_delegations"):
            raise PermissionDenied
        if not church_in_user_scope(user, delegation.church):
            raise PermissionDenied
    delegation.is_revoked = True
    repo.save_delegation(delegation, update_fields=["is_revoked"])
    _emit(
        "approval.delegate_revoke",
        actor=user,
        church=delegation.church,
        after={"delegation_id": str(delegation.pk)},
    )
    return delegation


def save_required_steps(church, user, required_steps: int):
    if not user_has_permission(user, "manage_approval_policy"):
        raise PermissionDenied
    if not church_in_user_scope(user, church):
        raise PermissionDenied
    if getattr(user, "role", None) in {UserRole.DISTRICT_PASTOR, UserRole.DISTRICT_TREASURY}:
        raise PermissionDenied
    steps = max(1, min(int(required_steps), 5))
    policy = get_or_create_policy(church)
    policy.required_steps = steps
    repo.save_policy(policy, update_fields=["required_steps", "is_active"])
    _emit(
        "approval.policy",
        actor=user,
        church=church,
        after={"required_steps": steps},
    )
    return policy
