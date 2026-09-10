"""Write enterprise audit events. Dual-write from domain logs; never a second GL."""

from __future__ import annotations

import hashlib
import json
import logging

from django.db import transaction

from audit import repositories as repo
from audit.context import current_audit_request
from church_system.client_ip import get_client_ip

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64
_REDACT_KEYS = {
    "password",
    "token",
    "secret",
    "otp",
    "ssn",
    "national_id",
    "bank_account",
    "pin",
}

_FINANCE_ACTION_MAP = {
    "CREATE": "journal.create",
    "UPDATE": "journal.update",
    "APPROVE": "journal.approve",
    "REJECT": "journal.reject",
    "VOID": "journal.void",
    "REMIT": "journal.remit",
    "BUDGET_CREATE": "budget.create",
    "BUDGET_UPDATE": "budget.update",
    "BUDGET_DELETE": "budget.delete",
}


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in _REDACT_KEYS:
                out[key] = "[redacted]"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def _event_hash(prev_hash: str, payload: dict) -> str:
    body = f"{prev_hash}:{_canonical(payload)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _request_meta():
    request = current_audit_request()
    if request is None:
        return {"ip_address": None, "user_agent": "", "request_id": ""}
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:256]
    rid = getattr(request, "correlation_id", None) or request.META.get("HTTP_X_REQUEST_ID") or ""
    return {
        "ip_address": get_client_ip(request),
        "user_agent": ua,
        "request_id": str(rid)[:64],
    }


def emit_event(
    *,
    domain: str,
    action: str,
    actor=None,
    church=None,
    denomination=None,
    object_type: str = "",
    object_id: str = "",
    object_label: str = "",
    before=None,
    after=None,
    outcome: str = "success",
    business_date=None,
    source: str = "",
    source_id: str = "",
):
    """Append an immutable AuditEvent. Failures are logged; callers keep working."""
    try:
        if church is not None and denomination is None:
            denomination = getattr(church, "denomination", None)
        meta = _request_meta()
        after_clean = _redact(after or {})
        before_clean = _redact(before or {})
        church_id = getattr(church, "pk", None)
        payload = {
            "domain": domain,
            "action": action,
            "outcome": outcome,
            "actor_id": str(getattr(actor, "pk", "") or ""),
            "actor_role": getattr(actor, "role", "") or "",
            "church_id": str(church_id or ""),
            "object_type": object_type,
            "object_id": str(object_id or ""),
            "source": source,
            "source_id": str(source_id or ""),
            "after": after_clean,
        }
        with transaction.atomic():
            prev = repo.last_event_for_church(church_id, lock=True) if church_id else None
            prev_hash = (prev.event_hash if prev and prev.event_hash else _GENESIS_HASH)
            event_hash = _event_hash(prev_hash, payload)
            return repo.create_audit_event(
                domain=domain,
                action=action,
                outcome=outcome,
                actor=actor,
                actor_role=getattr(actor, "role", "") or "",
                denomination=denomination,
                church=church,
                object_type=object_type,
                object_id=str(object_id or ""),
                object_label=(object_label or "")[:200],
                before=before_clean,
                after=after_clean,
                business_date=business_date,
                source=source,
                source_id=str(source_id or ""),
                prev_hash=prev_hash,
                event_hash=event_hash,
                **meta,
            )
    except Exception:
        logger.exception("Failed to emit enterprise audit event action=%s", action)
        return None


def emit_from_financial_audit(log):
    """Dual-write a FinancialAuditLog row into AuditEvent."""
    txn = getattr(log, "transaction", None)
    object_id = str(txn.pk) if txn is not None else str(log.pk)
    object_label = ""
    if txn is not None:
        object_label = txn.reference or str(txn.pk)
    business_date = getattr(txn, "date", None)
    action = _FINANCE_ACTION_MAP.get(log.action, f"finance.{str(log.action).lower()}")
    return emit_event(
        domain="finance",
        action=action,
        actor=log.performed_by,
        church=log.church,
        object_type="transactions.Transaction" if txn is not None else "transactions.FinancialAuditLog",
        object_id=object_id,
        object_label=object_label,
        after={"financial_action": log.action, "details": log.details or {}},
        business_date=business_date,
        source="financial_audit_log",
        source_id=str(log.pk),
    )
