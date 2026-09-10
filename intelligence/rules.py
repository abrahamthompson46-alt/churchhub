"""Deterministic, explainable findings. No ML."""

from __future__ import annotations

import hashlib
import statistics
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from transactions.models import Transaction


@dataclass(frozen=True)
class Finding:
    rule_code: str
    severity: str
    title: str
    explanation: str
    observed: dict
    threshold: dict
    fingerprint_parts: tuple

    def fingerprint(self) -> str:
        raw = "|".join(str(part) for part in self.fingerprint_parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def journal_amount(txn) -> Decimal:
    positives = [
        line.amount
        for line in txn.lines.all()
        if line.amount is not None and line.amount > 0
    ]
    if positives:
        return sum(positives, Decimal("0.00"))
    return abs(Decimal(str(txn.receipt_total or 0)))


def _dec(value) -> Decimal:
    return Decimal(str(value or 0))


def _as_dt(value):
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year") and not hasattr(value, "hour"):
        return timezone.make_aware(datetime.combine(value, time.min))
    return timezone.now()


def _church_qs(txn):
    return Transaction.objects.filter(church_id=txn.church_id).exclude(pk=txn.pk)


def _amounts(txns) -> list[Decimal]:
    out = []
    for row in txns.prefetch_related("lines__account"):
        out.append(journal_amount(row))
    return out


def rule_unusually_large(txn, policy) -> list[Finding]:
    amount = journal_amount(txn)
    absolute = _dec(policy.large_absolute)
    multiplier = _dec(policy.large_multiplier)
    since = txn.date - timedelta(days=policy.lookback_days)
    peers = _church_qs(txn).filter(date__gte=since, transaction_type=txn.transaction_type)
    sample = [a for a in _amounts(peers) if a > 0]
    median = Decimal(str(statistics.median(sample))) if sample else Decimal("0.00")
    relative_limit = median * multiplier if len(sample) >= policy.large_min_sample else Decimal("0.00")
    limit = max(absolute, relative_limit)
    if amount < absolute and (len(sample) < policy.large_min_sample or amount < relative_limit):
        return []
    if amount < limit:
        return []
    severity = "HIGH" if amount >= limit * Decimal("2") or amount >= absolute * Decimal("2") else "MEDIUM"
    if amount >= absolute:
        severity = "HIGH" if amount >= absolute else severity
    observed = {"amount": str(amount), "sample_size": len(sample), "median": str(median)}
    threshold = {
        "large_absolute": str(absolute),
        "large_multiplier": str(multiplier),
        "relative_limit": str(relative_limit),
        "limit": str(limit),
        "large_min_sample": policy.large_min_sample,
    }
    return [
        Finding(
            rule_code="unusually_large",
            severity=severity if amount >= absolute else "MEDIUM",
            title="Unusually large transaction",
            explanation=(
                f"Amount {amount} exceeds limit {limit} "
                f"(absolute {absolute}, {multiplier}× median {median} of {len(sample)} peers)."
            ),
            observed=observed,
            threshold=threshold,
            fingerprint_parts=(txn.pk, "unusually_large"),
        )
    ]


def rule_near_duplicate(txn, policy) -> list[Finding]:
    amount = journal_amount(txn)
    min_amount = _dec(policy.near_duplicate_min_amount)
    if amount < min_amount:
        return []
    created = _as_dt(txn.created_at)
    window = timedelta(minutes=policy.near_duplicate_minutes)
    qs = _church_qs(txn).filter(
        transaction_type=txn.transaction_type,
        created_at__gte=created - window,
        created_at__lte=created + window,
        member_id=txn.member_id,
    )
    matches = []
    for other in qs.prefetch_related("lines__account"):
        if journal_amount(other) == amount:
            matches.append(other)
    if not matches:
        return []
    other_id = matches[0].pk
    observed = {
        "amount": str(amount),
        "match_count": len(matches),
        "member_id": str(txn.member_id or ""),
        "window_minutes": policy.near_duplicate_minutes,
    }
    threshold = {
        "near_duplicate_minutes": policy.near_duplicate_minutes,
        "near_duplicate_min_amount": str(min_amount),
    }
    return [
        Finding(
            rule_code="near_duplicate",
            severity="MEDIUM",
            title="Near-duplicate transaction",
            explanation=(
                f"Amount {amount} matches {len(matches)} other {txn.transaction_type} "
                f"journal(s) within {policy.near_duplicate_minutes} minutes."
            ),
            observed=observed,
            threshold=threshold,
            fingerprint_parts=tuple(sorted([str(txn.pk), str(other_id)])) + ("near_duplicate",),
        )
    ]


def rule_repeated(txn, policy) -> list[Finding]:
    amount = journal_amount(txn)
    created = _as_dt(txn.created_at)
    since = created - timedelta(hours=policy.repeat_hours)
    qs = Transaction.objects.filter(
        church_id=txn.church_id,
        created_by_id=txn.created_by_id,
        transaction_type=txn.transaction_type,
        created_at__gte=since,
        created_at__lte=created,
    )
    count = 0
    for row in qs.prefetch_related("lines__account"):
        if journal_amount(row) == amount:
            count += 1
    if count < policy.repeat_count:
        return []
    observed = {"amount": str(amount), "count": count, "created_by_id": str(txn.created_by_id or "")}
    threshold = {"repeat_count": policy.repeat_count, "repeat_hours": policy.repeat_hours}
    bucket = created.strftime("%Y%m%d%H")
    return [
        Finding(
            rule_code="repeated",
            severity="HIGH" if count >= policy.repeat_count * 2 else "MEDIUM",
            title="Repeated transactions",
            explanation=(
                f"{count} identical {txn.transaction_type} amounts of {amount} "
                f"by the same maker in {policy.repeat_hours} hours (threshold {policy.repeat_count})."
            ),
            observed=observed,
            threshold=threshold,
            fingerprint_parts=(txn.church_id, txn.created_by_id, amount, txn.transaction_type, bucket, "repeated"),
        )
    ]


def rule_unusual_expense(txn, policy) -> list[Finding]:
    if txn.transaction_type not in ("EXPENSE", "TRANSFER"):
        return []
    amount = journal_amount(txn)
    limit = _dec(policy.expense_absolute)
    if amount < limit:
        return []
    severity = "HIGH" if amount >= limit * Decimal("2") else "MEDIUM"
    return [
        Finding(
            rule_code="unusual_expense",
            severity=severity,
            title="Unusual expense or withdrawal",
            explanation=f"{txn.transaction_type} amount {amount} exceeds expense threshold {limit}.",
            observed={"amount": str(amount), "transaction_type": txn.transaction_type},
            threshold={"expense_absolute": str(limit)},
            fingerprint_parts=(txn.pk, "unusual_expense"),
        )
    ]


def rule_abnormal_reversal(txn, policy) -> list[Finding]:
    if not (txn.is_voided or txn.approval_status == "REVERSED"):
        return []
    since = (txn.voided_at or timezone.now()) - timedelta(days=policy.reversal_days)
    count = Transaction.objects.filter(
        church_id=txn.church_id,
        is_voided=True,
        voided_at__gte=since,
    ).count()
    if count < policy.reversal_count:
        return []
    return [
        Finding(
            rule_code="abnormal_reversal",
            severity="HIGH" if count >= policy.reversal_count * 2 else "MEDIUM",
            title="Abnormal reversals",
            explanation=(
                f"{count} reversals in {policy.reversal_days} days "
                f"(threshold {policy.reversal_count})."
            ),
            observed={"reversal_count": count, "transaction_id": str(txn.pk)},
            threshold={"reversal_count": policy.reversal_count, "reversal_days": policy.reversal_days},
            fingerprint_parts=(txn.church_id, (txn.voided_at or timezone.now()).date(), "abnormal_reversal"),
        )
    ]


def rule_teller_velocity(txn, policy) -> list[Finding]:
    if not txn.created_by_id:
        return []
    created = _as_dt(txn.created_at)
    since = created - timedelta(minutes=policy.velocity_minutes)
    count = Transaction.objects.filter(
        church_id=txn.church_id,
        created_by_id=txn.created_by_id,
        created_at__gte=since,
        created_at__lte=created,
    ).count()
    if count < policy.velocity_count:
        return []
    bucket = created.strftime("%Y%m%d%H")
    return [
        Finding(
            rule_code="teller_velocity",
            severity="HIGH" if count >= policy.velocity_count * 2 else "MEDIUM",
            title="Teller velocity",
            explanation=(
                f"Maker posted {count} journals in {policy.velocity_minutes} minutes "
                f"(threshold {policy.velocity_count})."
            ),
            observed={"count": count, "created_by_id": str(txn.created_by_id)},
            threshold={"velocity_count": policy.velocity_count, "velocity_minutes": policy.velocity_minutes},
            fingerprint_parts=(txn.church_id, txn.created_by_id, bucket, "teller_velocity"),
        )
    ]


def _month_bounds(value):
    start = value.replace(day=1)
    last = monthrange(value.year, value.month)[1]
    end = value.replace(day=last)
    return start, end


def _type_total(church_id, txn_type, start, end) -> Decimal:
    qs = Transaction.objects.filter(
        church_id=church_id,
        transaction_type=txn_type,
        date__gte=start,
        date__lte=end,
        is_voided=False,
    ).exclude(approval_status="REJECTED")
    return sum(_amounts(qs), Decimal("0.00"))


def rule_giving_step_change(txn, policy) -> list[Finding]:
    if txn.transaction_type != "RECEIPT":
        return []
    return _step_change(txn, policy, "RECEIPT", "giving_step_change", "Giving step change")


def rule_spend_step_change(txn, policy) -> list[Finding]:
    if txn.transaction_type != "EXPENSE":
        return []
    return _step_change(txn, policy, "EXPENSE", "spend_step_change", "Spend step change")


def _step_change(txn, policy, txn_type, code, title) -> list[Finding]:
    start, end = _month_bounds(txn.date)
    prev_end = start - timedelta(days=1)
    prev_start, prev_end = _month_bounds(prev_end)
    current = _type_total(txn.church_id, txn_type, start, end)
    previous = _type_total(txn.church_id, txn_type, prev_start, prev_end)
    ratio = _dec(policy.step_change_ratio)
    if previous <= 0 or current < previous * ratio:
        return []
    observed = {"current_total": str(current), "previous_total": str(previous)}
    threshold = {"step_change_ratio": str(ratio)}
    return [
        Finding(
            rule_code=code,
            severity="MEDIUM",
            title=title,
            explanation=(
                f"{txn_type} month total {current} is at least {ratio}× "
                f"prior month {previous}."
            ),
            observed=observed,
            threshold=threshold,
            fingerprint_parts=(txn.church_id, txn.date.year, txn.date.month, code),
        )
    ]


def rule_period_end_bunching(txn, policy) -> list[Finding]:
    last_day = monthrange(txn.date.year, txn.date.month)[1]
    window_start_day = max(1, last_day - policy.bunching_last_days + 1)
    if txn.date.day < window_start_day:
        return []
    start, end = _month_bounds(txn.date)
    month_qs = Transaction.objects.filter(
        church_id=txn.church_id,
        date__gte=start,
        date__lte=end,
        is_voided=False,
    )
    month_count = month_qs.count()
    if month_count < policy.bunching_min_count:
        return []
    tail_count = month_qs.filter(date__day__gte=window_start_day).count()
    share = Decimal(tail_count) / Decimal(month_count)
    if share < _dec(policy.bunching_share):
        return []
    return [
        Finding(
            rule_code="period_end_bunching",
            severity="MEDIUM",
            title="Period-end bunching",
            explanation=(
                f"{tail_count} of {month_count} journals ({share:.2f}) fall in the last "
                f"{policy.bunching_last_days} days (share threshold {policy.bunching_share})."
            ),
            observed={"tail_count": tail_count, "month_count": month_count, "share": str(share)},
            threshold={
                "bunching_last_days": policy.bunching_last_days,
                "bunching_share": str(policy.bunching_share),
                "bunching_min_count": policy.bunching_min_count,
            },
            fingerprint_parts=(txn.church_id, txn.date.year, txn.date.month, "period_end_bunching"),
        )
    ]


def rule_baseline_deviation(txn, policy) -> list[Finding]:
    amount = journal_amount(txn)
    since = txn.date - timedelta(days=policy.lookback_days)
    peers = _church_qs(txn).filter(date__gte=since, transaction_type=txn.transaction_type)
    sample = [float(a) for a in _amounts(peers) if a > 0]
    if len(sample) < policy.baseline_min_sample:
        return []
    mean = statistics.mean(sample)
    stdev = statistics.pstdev(sample)
    if stdev <= 0:
        return []
    z = (float(amount) - mean) / stdev
    if z < float(policy.baseline_z):
        return []
    severity = "HIGH" if z >= float(policy.baseline_z) * 1.5 else "MEDIUM"
    return [
        Finding(
            rule_code="baseline_deviation",
            severity=severity,
            title="Baseline deviation",
            explanation=(
                f"Amount {amount} is z={z:.2f} vs mean {mean:.2f} / stdev {stdev:.2f} "
                f"(threshold z={policy.baseline_z}, n={len(sample)})."
            ),
            observed={
                "amount": str(amount),
                "z": f"{z:.2f}",
                "mean": f"{mean:.2f}",
                "stdev": f"{stdev:.2f}",
                "sample_size": len(sample),
            },
            threshold={"baseline_z": str(policy.baseline_z), "baseline_min_sample": policy.baseline_min_sample},
            fingerprint_parts=(txn.pk, "baseline_deviation"),
        )
    ]


RULES = (
    rule_unusually_large,
    rule_near_duplicate,
    rule_repeated,
    rule_unusual_expense,
    rule_abnormal_reversal,
    rule_teller_velocity,
    rule_giving_step_change,
    rule_spend_step_change,
    rule_period_end_bunching,
    rule_baseline_deviation,
)


def collect_findings(txn, policy) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(txn, policy))
    return findings
