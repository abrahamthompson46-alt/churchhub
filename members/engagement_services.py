"""Attendance-first membership engagement review.

`membership_status` is the source of truth (`Member.save` already syncs `is_active`).
This module never invents Transferred / Deceased / Suspended / Former.
Inactive is clerk-applied only unless a later policy expands auto-apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import Count, Max
from django.utils import timezone

from members.models import (
    Member,
    MemberEngagementDismissal,
    MemberEngagementPolicy,
    MembershipStatus,
)
from members.services import log_member_audit, update_member

TERMINAL_STATUSES = frozenset({
    MembershipStatus.TRANSFERRED,
    MembershipStatus.DECEASED,
    MembershipStatus.SUSPENDED,
    MembershipStatus.FORMER,
})

MIN_ATTENDANCE_EVENTS = 2
GIVING_RECEIPT_TYPE = "RECEIPT"


@dataclass(frozen=True)
class EngagementCandidate:
    member: Member
    current_status: str
    suggested_status: str
    last_seen_on: date | None
    last_gave_on: date | None
    weeks_absent: int | None
    reason: str
    auto_eligible: bool


@dataclass(frozen=True)
class EngagementReview:
    church: object
    policy: MemberEngagementPolicy
    as_of: date
    attendance_event_count: int
    attendance_too_thin: bool
    candidates: list[EngagementCandidate]


def get_or_create_engagement_policy(church) -> MemberEngagementPolicy:
    policy, _created = MemberEngagementPolicy.objects.get_or_create(church=church)
    return policy


def evaluate_church_engagement(church, *, as_of: date | None = None) -> EngagementReview:
    as_of = as_of or timezone.localdate()
    policy = get_or_create_engagement_policy(church)
    last_seen = _last_present_by_member(church)
    last_gave = _last_giving_by_member(church) if policy.giving_protects else {}
    event_count = _attendance_event_count(church, as_of=as_of, policy=policy)
    thin = event_count < MIN_ATTENDANCE_EVENTS
    dismissals = {
        row.member_id: row.last_seen_on
        for row in MemberEngagementDismissal.objects.filter(church=church)
    }

    members = list(
        Member.objects.filter(church=church).exclude(membership_status__in=TERMINAL_STATUSES)
    )
    candidates: list[EngagementCandidate] = []
    for member in members:
        seen = last_seen.get(member.pk)
        if member.pk in dismissals and dismissals[member.pk] == seen:
            continue
        candidate = _candidate_for_member(
            member,
            policy=policy,
            as_of=as_of,
            last_seen_on=seen,
            last_gave_on=last_gave.get(member.pk),
            attendance_too_thin=thin,
        )
        if candidate:
            candidates.append(candidate)

    candidates.sort(key=lambda row: (row.suggested_status, row.member.last_name, row.member.first_name))
    return EngagementReview(
        church=church,
        policy=policy,
        as_of=as_of,
        attendance_event_count=event_count,
        attendance_too_thin=thin,
        candidates=candidates,
    )


def apply_engagement_candidate(*, church, member, suggested_status, performed_by=None):
    if member.church_id != church.pk:
        raise ValueError("Member is not in this church.")
    if suggested_status not in {
        MembershipStatus.ACTIVE,
        MembershipStatus.MISSING,
        MembershipStatus.INACTIVE,
    }:
        raise ValueError("Suggested status is not allowed.")
    review = evaluate_church_engagement(church)
    match = next((row for row in review.candidates if row.member.pk == member.pk), None)
    if match is None or match.suggested_status != suggested_status:
        raise ValueError("This review suggestion is no longer current.")
    update_member(member, performed_by=performed_by, membership_status=suggested_status)
    MemberEngagementDismissal.objects.filter(church=church, member=member).delete()
    return member


def dismiss_engagement_candidate(*, church, member, performed_by=None, notes=""):
    if member.church_id != church.pk:
        raise ValueError("Member is not in this church.")
    last_seen = _last_present_by_member(church, member_ids=[member.pk]).get(member.pk)
    MemberEngagementDismissal.objects.update_or_create(
        church=church,
        member=member,
        defaults={
            "last_seen_on": last_seen,
            "dismissed_by": performed_by,
            "notes": notes or "",
        },
    )
    log_member_audit(
        church,
        "ENGAGEMENT_DISMISS",
        performed_by=performed_by,
        member=member,
        details={"last_seen_on": last_seen.isoformat() if last_seen else None},
    )
    return member


def auto_apply_missing_for_church(church, *, as_of: date | None = None) -> int:
    review = evaluate_church_engagement(church, as_of=as_of)
    if not review.policy.auto_apply_missing:
        return 0
    applied = 0
    for row in review.candidates:
        if not row.auto_eligible:
            continue
        update_member(row.member, membership_status=row.suggested_status)
        applied += 1
    return applied


def remind_engagement_reviews(*, as_of: date | None = None) -> dict:
    from organization.models import Church
    from members.notifications import notify_engagement_review

    as_of = as_of or timezone.localdate()
    churches = 0
    notified = 0
    auto_applied = 0
    for church in Church.objects.filter(is_active=True).iterator():
        review = evaluate_church_engagement(church, as_of=as_of)
        auto_applied += auto_apply_missing_for_church(church, as_of=as_of)
        remaining = evaluate_church_engagement(church, as_of=as_of)
        if not remaining.candidates:
            continue
        churches += 1
        notified += notify_engagement_review(church, count=len(remaining.candidates), as_of=as_of)
    return {"churches": churches, "notified": notified, "auto_applied": auto_applied}


def _candidate_for_member(
    member,
    *,
    policy,
    as_of,
    last_seen_on,
    last_gave_on,
    attendance_too_thin,
):
    status = member.membership_status
    missing_days = policy.missing_after_weeks * 7
    inactive_days = (policy.missing_after_weeks + policy.inactive_after_weeks) * 7
    weeks_absent = _weeks_absent(as_of, last_seen_on)
    in_grace = _in_join_grace(member, as_of=as_of, grace_days=missing_days)

    if last_seen_on and (as_of - last_seen_on).days < missing_days:
        if status in {MembershipStatus.MISSING, MembershipStatus.INACTIVE}:
            return EngagementCandidate(
                member=member,
                current_status=status,
                suggested_status=MembershipStatus.ACTIVE,
                last_seen_on=last_seen_on,
                last_gave_on=last_gave_on,
                weeks_absent=weeks_absent,
                reason="Marked present again — restore Active.",
                auto_eligible=status == MembershipStatus.MISSING,
            )
        return None

    if attendance_too_thin or in_grace:
        return None

    giving_blocks_missing = (
        policy.giving_protects
        and last_gave_on is not None
        and (as_of - last_gave_on).days < missing_days
    )
    giving_blocks_inactive = (
        policy.giving_protects
        and last_gave_on is not None
        and (as_of - last_gave_on).days < inactive_days
    )

    days_since = (as_of - last_seen_on).days if last_seen_on else None
    if days_since is None:
        days_since = (as_of - _joined_on(member)).days

    if status == MembershipStatus.ACTIVE and days_since >= missing_days and not giving_blocks_missing:
        return EngagementCandidate(
            member=member,
            current_status=status,
            suggested_status=MembershipStatus.MISSING,
            last_seen_on=last_seen_on,
            last_gave_on=last_gave_on,
            weeks_absent=weeks_absent if last_seen_on else days_since // 7,
            reason="No present mark for the Missing window.",
            auto_eligible=True,
        )

    if status == MembershipStatus.MISSING and days_since >= inactive_days and not giving_blocks_inactive:
        return EngagementCandidate(
            member=member,
            current_status=status,
            suggested_status=MembershipStatus.INACTIVE,
            last_seen_on=last_seen_on,
            last_gave_on=last_gave_on,
            weeks_absent=weeks_absent if last_seen_on else days_since // 7,
            reason="Still missing after the Inactive window.",
            auto_eligible=False,
        )
    return None


def _weeks_absent(as_of: date, last_seen_on: date | None) -> int | None:
    if last_seen_on is None:
        return None
    return max(0, (as_of - last_seen_on).days // 7)


def _joined_on(member) -> date:
    if member.date_joined:
        return member.date_joined
    created = member.created_at
    if timezone.is_aware(created):
        return timezone.localtime(created).date()
    return created.date()


def _in_join_grace(member, *, as_of: date, grace_days: int) -> bool:
    return (as_of - _joined_on(member)).days < grace_days


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        return value.date()
    return value


def _last_present_by_member(church, member_ids=None) -> dict:
    from meetings.models import AttendanceRecord, MeetingAttendance

    member_filter = {"member__church": church}
    if member_ids is not None:
        member_filter["member_id__in"] = member_ids

    event_rows = (
        AttendanceRecord.objects.filter(is_present=True, **member_filter)
        .values("member_id")
        .annotate(last=Max("event__event_date"))
    )
    meeting_rows = (
        MeetingAttendance.objects.filter(is_present=True, meeting__church=church, **(
            {"member_id__in": member_ids} if member_ids is not None else {}
        ))
        .values("member_id")
        .annotate(last=Max("meeting__scheduled_at"))
    )
    out: dict = {}
    for row in event_rows:
        out[row["member_id"]] = _as_date(row["last"])
    for row in meeting_rows:
        stamp = _as_date(row["last"])
        current = out.get(row["member_id"])
        if stamp and (current is None or stamp > current):
            out[row["member_id"]] = stamp
    return out


def _last_giving_by_member(church) -> dict:
    from transactions.models import Transaction

    rows = (
        Transaction.objects.filter(
            church=church,
            member__isnull=False,
            transaction_type=GIVING_RECEIPT_TYPE,
            approval_status="APPROVED",
            is_voided=False,
        )
        .values("member_id")
        .annotate(last=Max("date"))
    )
    return {row["member_id"]: row["last"] for row in rows}


def _attendance_event_count(church, *, as_of: date, policy: MemberEngagementPolicy) -> int:
    from meetings.models import AttendanceEvent, MeetingAttendance

    window_start = as_of - timedelta(days=(policy.missing_after_weeks + policy.inactive_after_weeks) * 7)
    events = AttendanceEvent.objects.filter(
        church=church,
        event_date__gte=window_start,
        event_date__lte=as_of,
        records__is_present=True,
    ).distinct().count()
    meetings = (
        MeetingAttendance.objects.filter(
            is_present=True,
            meeting__church=church,
            meeting__scheduled_at__date__gte=window_start,
            meeting__scheduled_at__date__lte=as_of,
        )
        .values("meeting_id")
        .annotate(n=Count("id"))
        .count()
    )
    return events + meetings
