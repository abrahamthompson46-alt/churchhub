"""Evaluate journals and record explainable alerts. Never posts or auto-decides."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from audit.services import emit_event
from intelligence import repositories as repo
from intelligence.models import RiskAlert
from intelligence.rules import collect_findings
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches
from permissions.services import user_has_permission
from transactions.models import Transaction

logger = logging.getLogger(__name__)


def get_or_create_policy(church):
    policy, _created = repo.get_or_create_policy(church=church)
    return policy


def _emit(action, *, actor, church, alert=None, txn=None, after=None):
    try:
        emit_event(
            domain="finance",
            action=action,
            actor=actor,
            church=church,
            object_type="intelligence.RiskAlert" if alert is not None else "transactions.Transaction",
            object_id=str(getattr(alert, "pk", None) or getattr(txn, "pk", "") or ""),
            object_label=(getattr(alert, "title", None) or getattr(txn, "reference", "") or "")[:200],
            after=after or {},
            source="intelligence",
            source_id=str(getattr(alert, "pk", "") or ""),
        )
    except Exception:
        logger.exception("Failed to emit intelligence audit event action=%s", action)


def evaluate_transaction(transaction):
    """Run deterministic rules. Failures never raise to posting callers."""
    if transaction is None:
        return []
    try:
        txn = (
            Transaction.objects.select_related("church", "created_by")
            .prefetch_related("lines__account")
            .filter(pk=getattr(transaction, "pk", transaction))
            .first()
        )
        if txn is None or txn.church_id is None:
            return []
        policy = get_or_create_policy(txn.church)
        if not policy.is_active:
            return []
        created = []
        for finding in collect_findings(txn, policy):
            alert, is_new = repo.create_alert(
                church=txn.church,
                denomination=getattr(txn.church, "denomination", None),
                transaction=txn,
                rule_code=finding.rule_code,
                severity=finding.severity,
                fingerprint=finding.fingerprint(),
                title=finding.title[:200],
                explanation=finding.explanation,
                observed=finding.observed,
                threshold=finding.threshold,
            )
            if not is_new or alert is None:
                continue
            created.append(alert)
            _emit(
                "risk.detect",
                actor=txn.created_by,
                church=txn.church,
                alert=alert,
                after={
                    "rule_code": alert.rule_code,
                    "severity": alert.severity,
                    "observed": alert.observed,
                    "threshold": alert.threshold,
                },
            )
            if alert.severity == RiskAlert.SEVERITY_HIGH and txn.approval_status == "PENDING":
                _queue_pending_case(alert, txn)
        return created
    except Exception:
        logger.exception("Intelligence evaluation failed for transaction %s", getattr(transaction, "pk", None))
        return []


def _queue_pending_case(alert, txn):
    """Attach an ApprovalCase for review. Never approve or reject the journal."""
    try:
        from approvals.services import ensure_case

        case = ensure_case(txn)
        if case is None:
            return
        alert.approval_case = case
        repo.save_alert(alert, update_fields=["approval_case"])
        _emit(
            "risk.queue",
            actor=txn.created_by,
            church=txn.church,
            alert=alert,
            after={
                "approval_case_id": str(case.pk),
                "transaction_id": str(txn.pk),
                "approval_status": txn.approval_status,
            },
        )
    except Exception:
        logger.exception("Failed to queue approval case for risk alert %s", alert.pk)


def _assert_church_scope(user, church):
    if church is None:
        raise PermissionDenied
    churches = get_manageable_churches(user)
    if not churches.filter(pk=church.pk).exists():
        raise PermissionDenied


def dismiss_alert(alert, user, note=""):
    if getattr(user, "role", None) == UserRole.DISTRICT_PASTOR:
        raise PermissionDenied
    if not user_has_permission(user, "review_risk_alerts"):
        raise PermissionDenied
    _assert_church_scope(user, alert.church)
    if alert.status != RiskAlert.STATUS_OPEN:
        raise ValueError("Alert is not open.")
    alert.status = RiskAlert.STATUS_DISMISSED
    alert.reviewed_by = user
    alert.reviewed_at = timezone.now()
    alert.review_note = (note or "").strip()
    repo.save_alert(alert, update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    _emit(
        "risk.dismiss",
        actor=user,
        church=alert.church,
        alert=alert,
        after={"status": alert.status},
    )
    return alert


def confirm_alert(alert, user, note=""):
    if getattr(user, "role", None) == UserRole.DISTRICT_PASTOR:
        raise PermissionDenied
    if not user_has_permission(user, "review_risk_alerts"):
        raise PermissionDenied
    _assert_church_scope(user, alert.church)
    if alert.status != RiskAlert.STATUS_OPEN:
        raise ValueError("Alert is not open.")
    alert.status = RiskAlert.STATUS_CONFIRMED
    alert.reviewed_by = user
    alert.reviewed_at = timezone.now()
    alert.review_note = (note or "").strip()
    repo.save_alert(alert, update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    _emit(
        "risk.confirm",
        actor=user,
        church=alert.church,
        alert=alert,
        after={"status": alert.status, "transaction_status": getattr(alert.transaction, "approval_status", "")},
    )
    return alert


def save_risk_policy(church, user, **fields):
    if getattr(user, "role", None) == UserRole.DISTRICT_PASTOR:
        raise PermissionDenied
    if not user_has_permission(user, "manage_risk_policy"):
        raise PermissionDenied
    _assert_church_scope(user, church)
    policy = get_or_create_policy(church)
    allowed = {
        "is_active",
        "block_auto_approve_on_high",
        "large_multiplier",
        "large_absolute",
        "large_min_sample",
        "near_duplicate_minutes",
        "near_duplicate_min_amount",
        "repeat_count",
        "repeat_hours",
        "expense_absolute",
        "reversal_count",
        "reversal_days",
        "velocity_count",
        "velocity_minutes",
        "step_change_ratio",
        "bunching_last_days",
        "bunching_share",
        "bunching_min_count",
        "baseline_min_sample",
        "baseline_z",
        "lookback_days",
    }
    update = []
    for key, value in fields.items():
        if key in allowed:
            setattr(policy, key, value)
            update.append(key)
    if update:
        repo.save_policy(policy, update_fields=update)
    _emit(
        "risk.policy",
        actor=user,
        church=church,
        after={"fields": update, "block_auto_approve_on_high": policy.block_auto_approve_on_high},
    )
    return policy
