"""Church-scoped membership dashboard snapshot (aggregates only)."""

from __future__ import annotations

import json
from calendar import month_abbr
from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from dashboard import metrics, selectors
from members.models import (
    AGE_GROUP_CHOICES,
    Gender,
    MembershipStatus,
    MemberTransfer,
    TransferStatus,
)
from members.selectors import age_group_q_map
from permissions.checks import can_add_members, can_view_members, can_manage_members

ALLOWED_TREND_MONTHS = (6, 12, 24)
DEFAULT_TREND_MONTHS = 12


def parse_trend_months(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_TREND_MONTHS
    if value in ALLOWED_TREND_MONTHS:
        return value
    return DEFAULT_TREND_MONTHS


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_keys(end_month: date, months: int) -> list[date]:
    keys = []
    cursor = end_month
    for _ in range(months):
        keys.append(cursor)
        cursor = cursor - relativedelta(months=1)
    keys.reverse()
    return keys


def _pct(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


def _label_month(d: date) -> str:
    return f"{month_abbr[d.month]} {d.year}"


def build_member_dashboard(request, *, church_ids=None):
    """
    Membership KPIs, demographics, trends, activity, and data-quality counts.

    Gated by view/manage members. Uses Member.objects (alive rows only).
    """
    user = request.user
    if not (can_view_members(user) or can_manage_members(user)):
        return None

    months = parse_trend_months(request.GET.get("member_months"))
    today = timezone.localdate()
    this_month = _month_start(today)
    period_start = this_month - relativedelta(months=months - 1)
    prior_start = period_start - relativedelta(months=months)
    qs = selectors.scoped_members_qs(request)
    age_q = age_group_q_map(today)
    known_gender = (Gender.MALE, Gender.FEMALE)

    aggregates = qs.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(membership_status=MembershipStatus.ACTIVE)),
        inactive=Count("id", filter=Q(membership_status=MembershipStatus.INACTIVE)),
        transferred=Count("id", filter=Q(membership_status=MembershipStatus.TRANSFERRED)),
        deceased=Count("id", filter=Q(membership_status=MembershipStatus.DECEASED)),
        missing=Count("id", filter=Q(membership_status=MembershipStatus.MISSING)),
        suspended=Count("id", filter=Q(membership_status=MembershipStatus.SUSPENDED)),
        former=Count("id", filter=Q(membership_status=MembershipStatus.FORMER)),
        is_active_true=Count("id", filter=Q(is_active=True)),
        is_active_false=Count("id", filter=Q(is_active=False)),
        baptized=Count("id", filter=Q(baptism_date__isnull=False)),
        unbaptized=Count("id", filter=Q(baptism_date__isnull=True)),
        male=Count("id", filter=Q(gender=Gender.MALE)),
        female=Count("id", filter=Q(gender=Gender.FEMALE)),
        gender_unknown=Count("id", filter=~Q(gender__in=known_gender)),
        new_this_month=Count("id", filter=Q(date_joined__gte=this_month)),
        new_period=Count(
            "id",
            filter=Q(date_joined__gte=period_start, date_joined__isnull=False),
        ),
        new_prior=Count(
            "id",
            filter=Q(
                date_joined__gte=prior_start,
                date_joined__lt=period_start,
            ),
        ),
        child=Count("id", filter=age_q["CHILD"]),
        teen=Count("id", filter=age_q["TEEN"]),
        youth=Count("id", filter=age_q["YOUTH"]),
        adult=Count("id", filter=age_q["ADULT"]),
        senior=Count("id", filter=age_q["SENIOR"]),
        missing_dob=Count("id", filter=Q(date_of_birth__isnull=True)),
        missing_phone=Count("id", filter=Q(phone="")),
        missing_email=Count("id", filter=Q(email="")),
        missing_joined=Count("id", filter=Q(date_joined__isnull=True)),
    )

    total = int(aggregates["total"] or 0)
    status_rows = []
    for code, label in MembershipStatus.choices:
        key = {
            MembershipStatus.ACTIVE: "active",
            MembershipStatus.INACTIVE: "inactive",
            MembershipStatus.TRANSFERRED: "transferred",
            MembershipStatus.DECEASED: "deceased",
            MembershipStatus.MISSING: "missing",
            MembershipStatus.SUSPENDED: "suspended",
            MembershipStatus.FORMER: "former",
        }.get(code)
        count = int(aggregates.get(key) or 0) if key else 0
        status_rows.append(
            {"code": code, "label": label, "count": count, "pct": _pct(count, total)}
        )

    gender_rows = [
        {"code": Gender.MALE, "label": "Male", "count": int(aggregates["male"] or 0)},
        {"code": Gender.FEMALE, "label": "Female", "count": int(aggregates["female"] or 0)},
        {
            "code": "unknown",
            "label": "Not specified",
            "count": int(aggregates["gender_unknown"] or 0),
        },
    ]
    for row in gender_rows:
        row["pct"] = _pct(row["count"], total)

    age_rows = []
    age_map = {
        "CHILD": aggregates["child"],
        "TEEN": aggregates["teen"],
        "YOUTH": aggregates["youth"],
        "ADULT": aggregates["adult"],
        "SENIOR": aggregates["senior"],
    }
    with_dob = total - int(aggregates["missing_dob"] or 0)
    for code, label in AGE_GROUP_CHOICES:
        count = int(age_map.get(code) or 0)
        age_rows.append(
            {
                "code": code,
                "label": label,
                "count": count,
                "pct": _pct(count, with_dob),
            }
        )
    largest_age = max(age_rows, key=lambda r: r["count"]) if age_rows else None
    if largest_age and largest_age["count"] == 0:
        largest_age = None

    church_ids = list(church_ids or [])
    if not church_ids:
        church_ids = list(qs.values_list("church_id", flat=True).distinct())

    def _bucket_month(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().replace(day=1)
        return value.replace(day=1)

    new_by_month = {}
    for row in (
        qs.filter(date_joined__gte=period_start, date_joined__isnull=False)
        .annotate(month=TruncMonth("date_joined"))
        .values("month")
        .annotate(count=Count("id"))
    ):
        key = _bucket_month(row["month"])
        if key:
            new_by_month[key] = int(row["count"] or 0)

    left_qs = MemberTransfer.objects.filter(
        status=TransferStatus.COMPLETED,
        transfer_date__gte=period_start,
        from_church_id__in=church_ids,
    )
    left_by_month = {}
    for row in (
        left_qs.annotate(month=TruncMonth("transfer_date"))
        .values("month")
        .annotate(count=Count("id"))
    ):
        key = _bucket_month(row["month"])
        if key:
            left_by_month[key] = int(row["count"] or 0)

    month_keys = _month_keys(this_month, months)
    new_series = []
    left_series = []
    net_series = []
    cumulative = 0
    labels = []
    for key in month_keys:
        n = int(new_by_month.get(key, 0))
        left = int(left_by_month.get(key, 0))
        net = n - left
        cumulative += net
        labels.append(_label_month(key))
        new_series.append(n)
        left_series.append(left)
        net_series.append(cumulative)

    new_period = int(aggregates["new_period"] or 0)
    new_prior = int(aggregates["new_prior"] or 0)
    transferred = int(aggregates["transferred"] or 0)
    former = int(aggregates["former"] or 0)
    left_snapshot = transferred + former

    quality = [
        {"key": "phone", "label": "Missing phone", "count": int(aggregates["missing_phone"] or 0)},
        {"key": "email", "label": "Missing email", "count": int(aggregates["missing_email"] or 0)},
        {"key": "dob", "label": "Missing date of birth", "count": int(aggregates["missing_dob"] or 0)},
        {
            "key": "gender",
            "label": "Gender not specified",
            "count": int(aggregates["gender_unknown"] or 0),
        },
        {
            "key": "joined",
            "label": "Missing membership date",
            "count": int(aggregates["missing_joined"] or 0),
        },
    ]
    incomplete_demo = int(aggregates["missing_dob"] or 0) + int(aggregates["gender_unknown"] or 0)

    activity = _recent_activity(qs, church_ids)

    links = [{"label": "Member directory", "url_name": "members:list"}]
    if can_add_members(user):
        links.append({"label": "Add member", "url_name": "members:add"})
    links.append({"label": "Baptism register", "url_name": "members:baptism_register"})
    links.append({"label": "Transfers", "url_name": "members:transfer_list"})
    links.append({"label": "Member summary report", "report_key": "member_summary"})

    return {
        "visible": True,
        "trend_months": months,
        "trend_month_choices": ALLOWED_TREND_MONTHS,
        "period_start": period_start,
        "period_label": f"{_label_month(period_start)} – {_label_month(this_month)}",
        "kpis": {
            "total": total,
            "active": int(aggregates["active"] or 0),
            "inactive": int(aggregates["inactive"] or 0),
            "new_this_month": int(aggregates["new_this_month"] or 0),
            "new_period": new_period,
            "left": left_snapshot,
            "baptized": int(aggregates["baptized"] or 0),
            "unbaptized": int(aggregates["unbaptized"] or 0),
        },
        "status_rows": status_rows,
        "gender_rows": gender_rows,
        "age_rows": age_rows,
        "age_missing_dob": int(aggregates["missing_dob"] or 0),
        "insights": {
            "largest_age_label": largest_age["label"] if largest_age else None,
            "largest_age_count": largest_age["count"] if largest_age else 0,
            "male_pct": _pct(int(aggregates["male"] or 0), total),
            "female_pct": _pct(int(aggregates["female"] or 0), total),
            "new_this_month": int(aggregates["new_this_month"] or 0),
            "new_period_delta_pct": metrics.pct_change(new_period, new_prior),
            "active_pct": _pct(int(aggregates["active"] or 0), total),
            "incomplete_demographics": incomplete_demo,
        },
        "quality": quality,
        "activity": activity,
        "links": links,
        "trend": {
            "labels_json": json.dumps(labels),
            "new_json": json.dumps(new_series),
            "left_json": json.dumps(left_series),
            "cumulative_net_json": json.dumps(net_series),
            "has_activity": any(new_series) or any(left_series),
        },
        "status_chart": {
            "labels_json": json.dumps([r["label"] for r in status_rows if r["count"]]),
            "data_json": json.dumps([r["count"] for r in status_rows if r["count"]]),
            "has_activity": any(r["count"] for r in status_rows),
        },
        # Backward-compatible keys used by existing dashboard context/widgets.
        "member_count": int(aggregates["is_active_true"] or 0),
        "inactive_count": int(aggregates["is_active_false"] or 0),
        "recent_members": selectors.members_for_request(request).order_by("-created_at")[:5],
    }


def _recent_activity(qs, church_ids, *, limit=8):
    items = []
    for member in qs.order_by("-created_at").only(
        "id", "first_name", "middle_name", "last_name", "preferred_name", "created_at", "membership_status"
    )[:5]:
        items.append(
            {
                "kind": "registered",
                "title": member.full_name,
                "subtitle": "Registered",
                "when": member.created_at,
                "url": reverse("members:detail", args=[member.pk]),
            }
        )
    baptized = (
        qs.filter(baptism_date__isnull=False)
        .order_by("-baptism_date", "-updated_at")
        .only(
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "preferred_name",
            "baptism_date",
        )[:5]
    )
    for member in baptized:
        items.append(
            {
                "kind": "baptism",
                "title": member.full_name,
                "subtitle": "Baptized",
                "when": member.baptism_date,
                "url": reverse("members:detail", args=[member.pk]),
            }
        )
    if church_ids:
        transfers = (
            MemberTransfer.objects.filter(
                status=TransferStatus.COMPLETED,
                from_church_id__in=church_ids,
            )
            .select_related("member", "to_church")
            .order_by("-transfer_date", "-processed_at")[:5]
        )
        for row in transfers:
            items.append(
                {
                    "kind": "transfer",
                    "title": row.member.full_name,
                    "subtitle": f"Transferred to {row.to_church.name}",
                    "when": row.processed_at or row.transfer_date,
                    "url": reverse("members:detail", args=[row.member_id]),
                }
            )

    def _sort_key(item):
        when = item["when"]
        if when is None:
            return timezone.now()
        if isinstance(when, datetime):
            if timezone.is_aware(when) or not timezone.is_aware(timezone.now()):
                return when
            return timezone.make_aware(when, timezone.get_current_timezone())
        combined = datetime.combine(when, time.min)
        if timezone.is_aware(timezone.now()):
            return timezone.make_aware(combined, timezone.get_current_timezone())
        return combined

    # Dedupe by title+kind keeping latest
    items.sort(key=_sort_key, reverse=True)
    seen = set()
    unique = []
    for item in items:
        key = (item["kind"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique
