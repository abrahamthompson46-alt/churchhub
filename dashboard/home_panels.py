"""Supplementary home dashboard panels (inbox, ministry, settlement, activity)."""

from __future__ import annotations

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from django.utils import timezone

from church_system.church_scope import get_active_church
from dashboard import metrics, selectors
from organization.models import Church
from permissions.checks import (
    can_manage_finances,
    can_manage_members,
    can_manage_receipts,
    can_run_cutoff,
    can_view_members,
    can_view_meetings,
    can_view_transactions,
)
from sitecontrol.services import church_has_feature


def get_notification_inbox(user, *, limit=5):
    notes = selectors.recent_notifications_for_user(user, limit=limit)
    unread = selectors.unread_notification_count(user)
    items = []
    for note in notes:
        items.append({
            "pk": note.pk,
            "title": note.title,
            "message": note.message,
            "category": note.category,
            "read": note.read,
            "created_at": note.created_at,
            "action_url": note.action_url or "",
        })
    return {"items": items, "unread_count": unread}


def get_attendance_panel(request):
    user = request.user
    church = get_active_church(request)
    if not church or not (can_view_members(user) or can_manage_members(user)):
        return None
    snap = selectors.worship_attendance_snapshot_for_church(church)
    if not snap:
        return {
            "empty": True,
            "hint": "Record Sabbath worship attendance to track presence trends.",
            "url_name": "meetings:attendance_create",
        }
    return {"empty": False, **snap}


def get_visitor_funnel_panel(request):
    church = get_active_church(request)
    user = request.user
    if not church or not (can_view_members(user) or can_manage_members(user)):
        return None
    counts = selectors.visitor_funnel_counts_for_church(church)
    if not counts.get("open_total"):
        return None
    return counts


def get_settlement_strip(request, church_ids):
    if not church_ids:
        return None
    user = request.user
    if not (
        can_manage_finances(user)
        or can_run_cutoff(user)
        or can_manage_receipts(user)
    ):
        return None
    from organization.models import Church

    church = get_active_church(request)
    if not church and church_ids:
        church = Church.objects.filter(pk=church_ids[0]).first()
    now = timezone.now()
    prior_month = (now.replace(day=1) - relativedelta(months=1)).date().replace(day=1)
    counts = selectors.remittance_scope_strip_counts(church_ids, prior_month)
    counts["period_label"] = prior_month.strftime("%B %Y")
    counts["cutoff_url"] = reverse("dashboard:cutoff")
    if church and church_has_feature(church, "remittance"):
        counts["settlements_url"] = reverse("remittance:settlements")
    else:
        counts["settlements_url"] = ""
    return counts


def get_budget_glance(request):
    from budgets.services import budget_kpis, budget_summary

    user = request.user
    church = get_active_church(request)
    if not church or not can_manage_finances(user):
        return None
    if not church_has_feature(church, "budgets"):
        return None
    year = timezone.localdate().year
    try:
        rows = budget_summary(church, year, level="CHURCH")
    except Exception:
        return None
    if not rows:
        return None
    kpis = budget_kpis(rows)
    return {
        "year": year,
        "expense_budgeted": kpis["expense_budgeted"],
        "expense_actual": kpis["expense_actual"],
        "over_budget_count": kpis["over_budget_count"],
        "url_name": "budgets:list",
    }


def get_recent_activity_panel(request, church_ids, *, limit=8):
    user = request.user
    if not church_ids:
        return None
    if not (
        can_manage_finances(user)
        or can_manage_receipts(user)
        or can_view_transactions(user)
    ):
        return None
    return selectors.recent_financial_activity(church_ids, limit=limit)


def get_member_role_extras(request):
    """Richer staff/member home: next service meeting + church contact."""
    user = request.user
    church = get_active_church(request) or user.church
    if not church:
        return {}
    extras = {
        "church_name": church.name,
        "church_phone": getattr(church, "phone", "") or "",
        "church_email": getattr(church, "email", "") or "",
    }
    if can_view_meetings(user):
        from meetings.models import Meeting, MeetingStatus

        now = timezone.now()
        nxt = (
            Meeting.objects.filter(
                church=church,
                scheduled_at__gte=now,
                status=MeetingStatus.SCHEDULED,
            )
            .order_by("scheduled_at")
            .first()
        )
        if nxt:
            extras["next_meeting"] = {
                "title": nxt.title,
                "when": nxt.scheduled_at,
                "url_name": "meetings:detail",
                "url_kwargs": {"pk": nxt.pk},
            }
    extras["portal_url"] = reverse("portal:home")
    extras["calendar_url"] = reverse("announcements:upcoming_calendar")
    return extras


def get_membership_analysis(church_ids, month_start):
    """Per-church and district membership with month-to-date join growth."""
    if not church_ids:
        return None
    churches = list(
        Church.objects.filter(pk__in=church_ids)
        .select_related("district")
        .order_by("district__name", "name")
    )
    if not churches:
        return None
    growth = selectors.membership_growth_by_church(list(church_ids), month_start)
    church_rows = []
    district_map = {}
    for church in churches:
        stats = growth.get(church.pk, {"current": 0, "new_mtd": 0})
        current = int(stats.get("current") or 0)
        new_mtd = int(stats.get("new_mtd") or 0)
        prior = max(current - new_mtd, 0)
        row = {
            "church_id": church.pk,
            "church": church.name,
            "district": church.district.name if church.district_id else "—",
            "district_id": church.district_id,
            "members": current,
            "new_mtd": new_mtd,
            "delta_pct": metrics.pct_change(current, prior),
            "focus_url": f"{reverse('dashboard:home')}?church={church.id}",
        }
        church_rows.append(row)
        bucket = district_map.setdefault(
            church.district_id or "none",
            {
                "district": row["district"],
                "members": 0,
                "new_mtd": 0,
                "church_count": 0,
            },
        )
        bucket["members"] += current
        bucket["new_mtd"] += new_mtd
        bucket["church_count"] += 1

    district_rows = []
    for bucket in district_map.values():
        prior = max(bucket["members"] - bucket["new_mtd"], 0)
        bucket["delta_pct"] = metrics.pct_change(bucket["members"], prior)
        district_rows.append(bucket)
    district_rows.sort(key=lambda r: r["district"])

    total_members = sum(r["members"] for r in church_rows)
    total_new = sum(r["new_mtd"] for r in church_rows)
    return {
        "churches": church_rows,
        "districts": district_rows,
        "show_districts": len(district_rows) > 1 or (len(church_rows) > 1 and district_rows),
        "totals": {
            "members": total_members,
            "new_mtd": total_new,
            "delta_pct": metrics.pct_change(total_members, max(total_members - total_new, 0)),
            "church_count": len(church_rows),
        },
        "period_label": month_start.strftime("%B %Y"),
    }


def get_dashboard_coaching_hints(context):
    """Actionable empty-state hints when panels are clear."""
    hints = []
    role = context.get("dashboard_role")
    scope = context.get("dashboard_scope")
    queue = context.get("action_queue") or []
    if not queue:
        if role == "treasury":
            if context.get("church_focused"):
                hints.append({
                    "text": "Open the business day, then record a receipt.",
                    "url_name": "transactions:record_receipt",
                })
            else:
                hints.append({
                    "text": "Select a congregation to open the teller and record receipts.",
                    "url_name": "dashboard:home",
                })
        elif role in ("leadership", "secretary"):
            hints.append({
                "text": "Review visitor follow-ups and record Sabbath attendance.",
                "url_name": "members:visitor_list",
            })
        elif role == "member":
            hints.append({
                "text": "Check upcoming events on the church calendar.",
                "url_name": "announcements:upcoming_calendar",
            })
    if scope and not scope.finance_church_ids and context.get("show_finance"):
        hints.append({
            "text": "Select a church in the toolbar to see financial charts.",
            "url_name": "dashboard:home",
        })
    return hints[:3]


def get_portal_staff_alerts(request):
    from permissions.checks import can_view_portal_submissions
    from portal.models import SpiritualSubmissionKind
    from portal.spiritual_services import count_new_praise_submissions, count_new_submissions

    if not can_view_portal_submissions(request.user):
        return None
    prayer_new = count_new_submissions(
        request.user, request, kind=SpiritualSubmissionKind.PRAYER
    )
    praise_new = count_new_praise_submissions(request.user, request)
    return {
        "prayer_new": prayer_new,
        "praise_new": praise_new,
        "prayer_url": reverse("portal:staff_submissions") + "?kind=PRAYER",
        "praise_url": reverse("portal:staff_submissions") + "?kind=THANKSGIVING",
    }


def get_member_portal_banner(user):
    from portal.views import user_can_use_member_portal

    if not user_can_use_member_portal(user):
        return None
    return {
        "portal_home_url": reverse("portal:home"),
        "prayer_url": reverse("portal:prayer_request"),
        "thanksgiving_url": reverse("portal:thanksgiving_testimony"),
    }
