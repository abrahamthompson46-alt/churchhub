"""Dashboard services — role context, metrics, notifications."""

import json
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from accounts.models import UserRole
from announcements.services import visible_announcements
from church_system.church_scope import get_active_church
from dashboard import repositories as repo
from dashboard import selectors
from permissions.checks import (
    can_approve_announcements,
    can_approve_minutes,
    can_approve_transactions,
    can_create_announcements,
    can_manage_expenses,
    can_manage_finances,
    can_manage_ledger_entries,
    can_manage_meetings,
    can_manage_members,
    can_manage_receipts,
    can_manage_users,
    can_run_cutoff,
    can_transfer_members,
    can_view_all_churches,
    can_view_dashboard_finance,
    can_view_meetings,
    can_view_members,
    can_view_pending_approvals,
    can_view_transactions,
)
from permissions.scoping import get_manageable_churches

REMIT_PAYABLE_TYPES = selectors.REMIT_PAYABLE_TYPES
INCOME_REMIT_TYPES = selectors.INCOME_REMIT_TYPES


def notify_user(user, title, message, category="INFO", action_url=""):
    """Create an in-app notification for a user."""
    if not user or not user.is_active:
        return None
    from dashboard.models import Notification

    if category not in Notification.VALID_CATEGORIES:
        category = "INFO"
    return repo.create_notification(
        user=user,
        title=title,
        message=message,
        category=category,
        action_url=action_url,
    )


def notify_users(users, title, message, category="INFO", action_url=""):
    """Fan-out helper; skips inactive / missing users."""
    created = []
    seen = set()
    for user in users:
        if not user or getattr(user, "pk", None) in seen:
            continue
        seen.add(user.pk)
        note = notify_user(user, title, message, category=category, action_url=action_url)
        if note:
            created.append(note)
    return created


def get_dashboard_role(user):
    """Determine which dashboard layout to show (identity-first)."""
    if user.is_superuser or user.role == UserRole.SUPER_ADMIN:
        return "admin"
    if user.role == UserRole.GENERAL_OVERSEER:
        return "overseer"
    if user.role == UserRole.DISTRICT_PASTOR:
        return "district_overseer"
    if user.role == UserRole.TREASURY:
        return "treasury"
    if user.role == UserRole.SECRETARY:
        return "secretary"
    if user.role == UserRole.LOCAL_PASTOR:
        return "leadership"
    if can_approve_transactions(user):
        return "leadership"
    if can_manage_finances(user):
        return "finance"
    if can_manage_members(user) or can_view_members(user):
        return "members"
    return "member"


def _month_bounds(now=None):
    now = now or timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if timezone.is_aware(month_start):
        month_start_date = timezone.localdate(month_start)
    else:
        month_start_date = month_start.date()
    return now, month_start, month_start_date


def _sum_account_type(lines_qs, acc_type):
    return selectors.sum_line_amount_for_type(lines_qs, acc_type)


def _compute_remittance_payable_mtd(church, month_start_date):
    """Sum remittance payable GL lines for a church/month without creating MonthlyCutoff."""
    return selectors.remittance_payable_mtd_amounts(church, month_start_date)


def _sum_remittance_payable_mtd_for_churches(churches, month_start_date):
    """Per-church cut-off or GL compute, summed — matches the cut-off page and church KPIs."""
    return selectors.sum_remittance_payable_mtd_for_churches(churches, month_start_date)


def get_workspace_finance_mtd(request):
    """MTD finance snapshot for the workspace status bar (active church)."""
    from accounts.permissions import can_view_dashboard_finance

    if not request.user.is_authenticated or not can_view_dashboard_finance(request.user):
        return None

    church = get_active_church(request)
    if not church:
        return None

    _, _, month_start_date = _month_bounds()
    mtd_lines = selectors.mtd_lines_for_churches([church.pk], month_start_date)
    mtd_tithe, mtd_combined = selectors.sum_tithe_combined_mtd(mtd_lines)
    ie = selectors.sum_line_amounts_by_types(mtd_lines, ("INCOME", "EXPENSE"))
    mtd_remit = _sum_remittance_payable_mtd_for_churches([church], month_start_date)
    return {
        "mtd_tithe": mtd_tithe,
        "mtd_combined": mtd_combined,
        "mtd_remittance_payable": mtd_remit,
        "mtd_net": ie["INCOME"] - ie["EXPENSE"],
    }


def get_financial_summary(request):
    """Core financial KPIs for finance dashboards (MTD primary)."""
    now, month_start, month_start_date = _month_bounds()
    transactions = selectors.transactions_for_request(request)
    approved = selectors.approved_transactions(transactions)
    mtd_approved = approved.filter(date__gte=month_start_date)
    mtd_lines = selectors.lines_for_transactions(mtd_approved)
    all_time_lines = selectors.lines_for_transactions(approved)

    tithe_total, combined_total = selectors.sum_tithe_combined_mtd(mtd_lines)
    mtd_totals = selectors.sum_line_amounts_by_types(mtd_lines, ("INCOME", "EXPENSE"))
    income_total = mtd_totals["INCOME"]
    expense_total = mtd_totals["EXPENSE"]

    church = get_active_church(request)
    if church:
        monthly_cutoff_total = _sum_remittance_payable_mtd_for_churches(
            [church], month_start_date
        )
    else:
        monthly_cutoff_total = _sum_remittance_payable_mtd_for_churches(
            list(get_manageable_churches(request.user)), month_start_date
        )

    six_months_ago = (now - relativedelta(months=5)).replace(day=1)
    six_months_ago_date = (
        timezone.localdate(six_months_ago) if timezone.is_aware(six_months_ago) else six_months_ago.date()
    )
    trend_qs = selectors.income_expense_trend_aggregates(all_time_lines, six_months_ago_date)

    trend_dict = {}
    for i in range(6):
        m_dt = (now - relativedelta(months=i)).replace(day=1)
        label = m_dt.strftime("%b %Y")
        trend_dict[label] = {"INCOME": 0.0, "EXPENSE": 0.0}

    for row in trend_qs:
        month_val = row["month"]
        if not month_val:
            continue
        label = month_val.strftime("%b %Y")
        acc_type = row["account__account_type"]
        if label in trend_dict and acc_type in trend_dict[label]:
            trend_dict[label][acc_type] += float(abs(row["total"] or 0))

    trend_labels = list(reversed(list(trend_dict.keys())))
    income_data = [trend_dict[m]["INCOME"] for m in trend_labels]
    expense_data = [trend_dict[m]["EXPENSE"] for m in trend_labels]

    all_time_tithe, all_time_combined = selectors.sum_tithe_combined_mtd(all_time_lines)

    return {
        "kpi_period_label": "Month to date",
        "cutoff_metric_label": "Remittance payable (MTD)",
        "tithe_total": tithe_total,
        "combined_total": combined_total,
        "church_income_total": income_total,
        "expense_total": expense_total,
        "net_balance": income_total - expense_total,
        "monthly_cutoff_total": monthly_cutoff_total,
        "tithe_total_all_time": all_time_tithe,
        "combined_total_all_time": all_time_combined,
        "pending_count": selectors.pending_transactions_count(transactions),
        "recent_transactions": selectors.recent_approved_transactions(approved),
        "trend_labels": json.dumps(trend_labels),
        "income_data": json.dumps(income_data),
        "expense_data": json.dumps(expense_data),
        "has_active_church": bool(church),
    }


def get_member_summary(request):
    members = selectors.members_for_request(request)
    active_church = get_active_church(request)
    transfers = selectors.pending_transfers_for_church(active_church)

    return {
        "member_count": members.filter(is_active=True).count(),
        "inactive_count": members.filter(is_active=False).count(),
        "recent_members": members.order_by("-created_at")[:5],
        "pending_transfers": transfers.count(),
    }


def get_admin_summary(user):
    """Hierarchy-level stats scoped to manageable churches / denomination."""
    if not (can_view_all_churches(user) or user.is_superuser):
        return {}

    manageable = get_manageable_churches(user)
    church_ids = list(manageable.values_list("id", flat=True))
    district_ids = manageable.values_list("district_id", flat=True).distinct()
    conference_ids = manageable.values_list(
        "district__zone__conference_id", flat=True
    ).distinct()

    conferences = selectors.conferences_for_admin(user, conference_ids)
    pending_ann = selectors.pending_announcements_for_admin(user, church_ids)

    return {
        "conference_count": conferences.count(),
        "church_count": len(church_ids),
        "district_count": selectors.district_count_for_ids(district_ids),
        "pending_announcements": pending_ann.count(),
    }


def get_role_focus(role):
    """Role-specific dashboard headline and focus areas."""
    focus_map = {
        "overseer": {
            "headline": "Executive command center — organization performance at a glance.",
            "focus": ["District performance", "Remittance compliance", "Approval queue"],
        },
        "district_overseer": {
            "headline": "District command center — churches, remittances, and pastoral oversight.",
            "focus": ["Church leaderboard", "Remittance compliance", "Action queue"],
        },
        "admin": {
            "headline": "System command center — hierarchy health and operational control.",
            "focus": ["Organization KPIs", "Compliance", "Pending actions"],
        },
        "treasury": {
            "headline": "Record receipts, track cut-offs, and manage remittances.",
            "focus": ["Monthly cut-off", "Pending approvals", "Period locks"],
        },
        "finance": {
            "headline": "Financial operations and reporting for your church.",
            "focus": ["Income & expenses", "Budget tracking", "Audit trail"],
        },
        "secretary": {
            "headline": "Members, meetings, and church communications.",
            "focus": ["Membership records", "Transfers", "Meeting minutes"],
        },
        "leadership": {
            "headline": "Oversight, approvals, and pastoral visibility.",
            "focus": ["Pending approvals", "Announcements", "Member care"],
        },
        "members": {
            "headline": "Membership administration and pastoral records.",
            "focus": ["Active members", "Departments", "Transfers"],
        },
        "member": {
            "headline": "Stay connected with your church community.",
            "focus": ["Announcements", "Giving history", "Upcoming events"],
        },
    }
    return focus_map.get(role, focus_map["member"])


def get_quick_actions(user):
    """Permission- and role-based shortcut links for the dashboard."""
    from church_system.navigation import _item
    from sitecontrol.services import church_has_feature

    role = get_dashboard_role(user)
    actions = []
    seen_labels = set()

    def _add(item):
        label = item.get("label")
        if label in seen_labels:
            return
        seen_labels.add(label)
        actions.append(item)

    if role == "treasury":
        if can_manage_receipts(user):
            _add(_item("Record Receipt", "transactions:record_receipt", "bi-plus-circle"))
        if can_manage_ledger_entries(user):
            _add(_item("Journal Entry", "ledger:entry", "bi-journal-plus"))
        if can_view_pending_approvals(user) or can_approve_transactions(user):
            _add(_item("Pending Approvals", "transactions:pending_approvals", "bi-hourglass-split"))
        if (
            user.church_id
            and church_has_feature(user.church, "remittance")
            and (can_manage_expenses(user) or can_manage_receipts(user) or can_manage_finances(user))
        ):
            _add(_item("Remittance", "transactions:record_remittance", "bi-send"))
    elif role == "secretary":
        if can_manage_members(user):
            _add(_item("Add Member", "members:add", "bi-person-plus"))
        if can_transfer_members(user):
            _add(_item("Transfers", "members:transfer_list", "bi-arrow-left-right"))
        if can_manage_meetings(user):
            _add(_item("Schedule Meeting", "meetings:create", "bi-calendar-plus"))
        if can_create_announcements(user):
            _add(_item("New Announcement", "announcements:create_announcement", "bi-megaphone"))
    elif role in ("leadership",):
        if can_approve_transactions(user):
            _add(_item("Approvals", "transactions:pending_approvals", "bi-check2-circle"))
        if can_create_announcements(user) or can_approve_announcements(user):
            _add(_item("Announcements", "announcements:announcement_list", "bi-newspaper"))
        if can_view_members(user) or can_manage_members(user):
            _add(_item("Member Directory", "members:list", "bi-people"))
    elif role in ("overseer", "district_overseer", "admin"):
        if can_view_all_churches(user):
            _add(_item("Organization", "organization:hierarchy", "bi-diagram-3"))
            _add(_item("Roll-up Report", report_key="hierarchy_rollup", icon="bi-bar-chart-steps"))
        if can_run_cutoff(user) or can_view_dashboard_finance(user):
            _add(_item("Cut-off", "dashboard:cutoff", "bi-calendar-check"))
    else:
        if can_manage_finances(user) or can_manage_ledger_entries(user):
            _add(_item("Journal Entry", "ledger:entry", "bi-journal-plus"))
        if can_view_pending_approvals(user) or can_approve_transactions(user):
            _add(_item("Pending Approvals", "transactions:pending_approvals", "bi-hourglass-split"))
        if can_manage_members(user):
            _add(_item("Add Member", "members:add", "bi-person-plus"))
        if can_manage_meetings(user):
            _add(_item("Schedule Meeting", "meetings:create", "bi-calendar-plus"))
        if can_approve_transactions(user):
            # Deduplicate: do not add both Pending Approvals and Approvals
            if "Pending Approvals" not in seen_labels:
                _add(_item("Approvals", "transactions:pending_approvals", "bi-check2-circle"))
        if can_approve_announcements(user):
            _add(_item("Pending Announcements", "announcements:pending_approvals", "bi-megaphone"))
        if can_manage_users(user):
            _add(_item("Invite User", "accounts:invite_user", "bi-envelope-plus"))
        if can_view_all_churches(user):
            _add(_item("Organization", "organization:hierarchy", "bi-diagram-3"))
            _add(_item("Roll-up Report", report_key="hierarchy_rollup", icon="bi-bar-chart-steps"))
        if can_create_announcements(user):
            _add(_item("New Announcement", "announcements:create_announcement", "bi-megaphone"))

    if not actions and not can_manage_finances(user) and not can_view_members(user):
        _add(_item("Announcements", "announcements:announcement_list", "bi-newspaper"))

    # Keep hero to primary CTAs; calendar lives under Church Life.
    if role in ("member", "members") and len(actions) < 3:
        _add(_item("Member portal", "portal:home", "bi-people"))
        _add(_item("Upcoming", "announcements:upcoming_calendar", "bi-calendar-heart"))
    elif role in ("member", "members"):
        _add(_item("Member portal", "portal:home", "bi-people"))
    return actions[:6]


def apply_pinned_quick_actions(request, actions):
    """Reorder quick actions using session-pinned labels (max 3)."""
    pinned = request.session.get("dashboard_pinned_labels") or []
    if not pinned or not actions:
        return actions
    by_label = {a.get("label"): a for a in actions}
    ordered = []
    for label in pinned:
        item = by_label.get(label)
        if item and item not in ordered:
            ordered.append(item)
    for item in actions:
        if item not in ordered:
            ordered.append(item)
    return ordered[:6]


def get_nav_badges(request):
    """Lightweight badge counts for primary nav menus (mobile + desktop)."""
    user = request.user
    if not user.is_authenticated or getattr(user, "is_platform_user", False):
        return {}
    badges = {}
    if can_approve_transactions(user):
        pending = selectors.pending_transactions_for_request_count(request)
        if pending:
            badges["finance"] = pending
    if can_approve_announcements(user):
        from announcements.services import pending_for_user

        pending_ann = pending_for_user(user).count()
        if pending_ann:
            badges["communications"] = pending_ann
    if can_approve_minutes(user):
        from meetings.workflow import pending_minutes_for_user

        pending_mins = pending_minutes_for_user(user).count()
        if pending_mins:
            badges["people"] = pending_mins
    return badges


def get_alerts(request, user):
    """Actionable alert items for the dashboard banner."""
    from church_system.currency import currency_symbol

    alerts = []
    church = get_active_church(request)
    symbol = currency_symbol()

    if can_approve_transactions(user):
        pending = selectors.pending_transactions_for_request_count(request)
        if pending:
            alerts.append({
                "level": "warning",
                "text": f"{pending} transaction(s) awaiting approval.",
                "url_name": "transactions:pending_approvals",
            })

    if church and can_manage_finances(user):
        from transactions.services import get_working_day_status

        wd = get_working_day_status(church)
        if not wd["is_open"]:
            alerts.append({
                "level": "warning",
                "text": "No working day is open. Open the day before recording transactions.",
                "url_name": "transactions:period_list",
            })

        now = timezone.now()
        current_locked = selectors.locked_period_exists(church, now.year, now.month)
        if current_locked:
            alerts.append({
                "level": "info",
                "text": f"Financial period {now.strftime('%B %Y')} is locked.",
                "url_name": "transactions:period_list",
            })

        prior_month = (now.replace(day=1) - relativedelta(months=1)).date().replace(day=1)
        overdue = selectors.overdue_cutoff_for_church(church, prior_month)
        if overdue and overdue.total_payable > 0:
            alerts.append({
                "level": "danger",
                "text": (
                    f"Remittance overdue for {prior_month.strftime('%B %Y')} "
                    f"({symbol}{overdue.total_payable:,.2f} payable)."
                ),
                "url_name": "dashboard:cutoff",
            })

    if can_approve_announcements(user):
        from announcements.services import pending_for_user

        pending_ann = pending_for_user(user).count()
        if pending_ann:
            alerts.append({
                "level": "secondary",
                "text": f"{pending_ann} announcement(s) pending approval.",
                "url_name": "announcements:pending_approvals",
            })

    if can_approve_minutes(user):
        from meetings.workflow import pending_minutes_for_user

        pending_mins = pending_minutes_for_user(user).count()
        if pending_mins:
            alerts.append({
                "level": "warning",
                "text": f"{pending_mins} meeting minute(s) pending approval.",
                "url_name": "meetings:pending_minutes",
            })

    if not user.church and user.requires_church:
        alerts.append({
            "level": "danger",
            "text": "Your account is not assigned to a church.",
            "url_name": "accounts:profile",
        })

    return alerts


def get_hierarchy_rollup(request, user):
    """District-level financial roll-up for overseers, district pastors, and admins."""
    manageable = get_manageable_churches(user)
    if not manageable.exists():
        return []

    now, _, month_start_date = _month_bounds()
    church_rows = selectors.manageable_church_district_rows(manageable)
    if not church_rows:
        return []

    church_ids = [r["id"] for r in church_rows]
    district_church_counts = {}
    district_names = {}
    for row in church_rows:
        did = row["district_id"]
        if did is None:
            continue
        district_church_counts[did] = district_church_counts.get(did, 0) + 1
        district_names[did] = row["district__name"]

    aggregates = selectors.district_remit_income_aggregates(church_ids, month_start_date)

    by_district = {}
    for did in district_church_counts:
        by_district[did] = {
            "tithe": Decimal("0"),
            "combined": Decimal("0"),
            "remittance_payable": Decimal("0"),
        }

    for row in aggregates:
        did = row["transaction__church__district_id"]
        if did not in by_district:
            continue
        amount = abs(row["total"] or Decimal("0"))
        acc = row["account__account_type"]
        if acc in selectors.TITHE_GIVING_TYPES:
            by_district[did]["tithe"] += amount
        elif acc in selectors.COMBINED_GIVING_TYPES:
            by_district[did]["combined"] += amount
        elif acc in REMIT_PAYABLE_TYPES:
            by_district[did]["remittance_payable"] += amount

    rows = []
    for did, counts in district_church_counts.items():
        data = by_district.get(did, {})
        tithe = data.get("tithe", Decimal("0"))
        combined = data.get("combined", Decimal("0"))
        remit = data.get("remittance_payable", Decimal("0"))
        rows.append({
            "district": district_names.get(did, "—"),
            "church_count": counts,
            "tithe": tithe,
            "combined": combined,
            "remittance_payable": remit,
            "total": tithe + combined,
        })

    return sorted(rows, key=lambda r: r["remittance_payable"] or r["total"], reverse=True)[:12]


def get_compliance_snapshot(request, user, *, church_ids=None, manageable=None):
    """Organization compliance indicators for executive dashboard."""
    if manageable is None:
        manageable = get_manageable_churches(user)
    if church_ids is None:
        if not manageable.exists():
            return {}
        church_ids = list(manageable.values_list("id", flat=True))
    elif not church_ids:
        return {}

    now = timezone.now()
    prior_month = (now.replace(day=1) - relativedelta(months=1)).date().replace(day=1)

    overdue_qs = selectors.overdue_cutoffs_for_churches(church_ids, prior_month)
    overdue = overdue_qs[:5]

    locked_periods = selectors.locked_periods_count(church_ids, now.year, now.month)

    working_day_issues = 0
    if can_manage_finances(user):
        open_ids = selectors.open_working_day_church_ids(church_ids)
        working_day_issues = sum(1 for cid in church_ids if cid not in open_ids)

    return {
        "overdue_remittances": [
            {
                "church": row.church.name,
                "month": row.month.strftime("%B %Y"),
                "amount": row.payable,
            }
            for row in overdue
        ],
        "overdue_count": overdue_qs.count(),
        "locked_periods": locked_periods,
        "working_day_issues": working_day_issues,
    }


def get_executive_kpis(
    request,
    user,
    *,
    church_ids=None,
    manageable=None,
    compliance=None,
    active_church=None,
):
    """
    Organization KPIs for Mission Control.

    Churches / members / action items stay hierarchy-wide.
    Finance MTD figures follow the toolbar church when one is selected; otherwise they roll up the full scope.
    Remittance payable uses the same per-church cut-off logic as the cut-off page.
    """
    if manageable is None:
        manageable = get_manageable_churches(user)
    if church_ids is None:
        if not manageable.exists():
            return None
        church_ids = list(manageable.values_list("id", flat=True))
    elif not church_ids:
        return None

    now, _, month_start_date = _month_bounds()

    if active_church is not None and active_church.pk in set(church_ids):
        finance_church_ids = [active_church.pk]
        finance_scope_label = active_church.name
        finance_scope = "church"
    else:
        finance_church_ids = church_ids
        finance_scope_label = f"{len(church_ids)} churches"
        finance_scope = "scope"

    if compliance is None:
        compliance = get_compliance_snapshot(
            request, user, church_ids=church_ids, manageable=manageable
        )

    from dashboard import metrics

    return metrics.build_executive_finance_bundle(
        church_ids=church_ids,
        finance_church_ids=finance_church_ids,
        finance_scope_label=finance_scope_label,
        manageable=manageable,
        month_start_date=month_start_date,
        period_label=now.strftime("%B %Y"),
        compliance=compliance,
        finance_scope=finance_scope,
    )


def get_action_queue(request, user):
    """Prioritized operational action queue for the control center."""
    queue = []
    church = get_active_church(request)
    manageable = get_manageable_churches(user)
    church_ids = list(manageable.values_list("id", flat=True)) if manageable.exists() else []

    def _add(priority, title, subtitle, *, kind="", count=0, url_name="", icon="bi-circle", report_key="", url_suffix=""):
        queue.append({
            "kind": kind,
            "priority": priority,
            "priority_score": {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(priority, 0),
            "title": title,
            "subtitle": subtitle,
            "count": count,
            "url_name": url_name,
            "url_suffix": url_suffix,
            "report_key": report_key,
            "icon": icon,
        })

    if can_approve_transactions(user) and church_ids:
        pending = selectors.pending_transactions_for_churches_count(church_ids)
        if pending:
            _add(
                "high",
                "Transaction approvals",
                "Awaiting pastor or treasury sign-off",
                kind="transaction_approvals",
                count=pending,
                url_name="transactions:pending_approvals",
                icon="bi-check2-circle",
            )

    if church_ids:
        prior_month = (timezone.now().replace(day=1) - relativedelta(months=1)).date().replace(day=1)
        overdue = selectors.overdue_cutoff_count(church_ids, prior_month)
        if overdue:
            _add(
                "critical",
                "Overdue remittances",
                f"{prior_month.strftime('%B %Y')} district remittance not transferred",
                kind="overdue_remittances",
                count=overdue,
                url_name="dashboard:cutoff",
                icon="bi-exclamation-octagon",
            )

    if can_approve_announcements(user):
        from announcements.services import pending_for_user

        pending_ann = pending_for_user(user).count()
        if pending_ann:
            _add(
                "medium",
                "Announcement approvals",
                "Church Life items awaiting review",
                kind="announcement_approvals",
                count=pending_ann,
                url_name="announcements:pending_approvals",
                icon="bi-megaphone",
            )

    if can_approve_minutes(user):
        from meetings.workflow import pending_minutes_for_user

        pending_mins = pending_minutes_for_user(user).count()
        if pending_mins:
            _add(
                "medium",
                "Meeting minutes",
                "Minutes pending pastoral approval",
                kind="meeting_minutes",
                count=pending_mins,
                url_name="meetings:pending_minutes",
                icon="bi-journal-text",
            )

    if church_ids and user_has_asset_approval(user):
        pending_assets = selectors.pending_assets_for_churches_count(church_ids)
        if pending_assets:
            _add(
                "medium",
                "Fixed asset approvals",
                "Capital acquisitions awaiting activation",
                kind="asset_approvals",
                count=pending_assets,
                url_name="assets:asset_list",
                url_suffix="?status=PENDING_APPROVAL",
                icon="bi-box-seam",
            )

    if can_manage_members(user) or can_view_members(user):
        if church:
            transfers = selectors.pending_transfers_for_church(church)
        elif church_ids:
            transfers = selectors.pending_transfers_for_church_ids(church_ids)
        else:
            transfers = selectors.pending_transfers_for_church(None)
        transfer_count = transfers.count()
        if transfer_count:
            _add(
                "low",
                "Member transfers",
                "Membership moves awaiting processing",
                kind="member_transfers",
                count=transfer_count,
                url_name="members:transfer_list",
                icon="bi-arrow-left-right",
            )

    if church and can_manage_finances(user):
        from transactions.services import get_working_day_status

        if not get_working_day_status(church)["is_open"]:
            _add(
                "high",
                "Working day closed",
                "Open the business day before recording transactions",
                kind="working_day_closed",
                url_name="transactions:period_list",
                icon="bi-calendar-x",
            )

    if not user.church and user.requires_church:
        _add(
            "critical",
            "Church assignment missing",
            "Contact an administrator to assign your account",
            kind="church_assignment_missing",
            url_name="accounts:profile",
            icon="bi-person-exclamation",
        )

    queue.sort(key=lambda item: item["priority_score"], reverse=True)
    return queue[:12]


CONTROL_CENTER_QUEUE_OMIT = frozenset({"transaction_approvals", "overdue_remittances"})
MY_ACTION_QUEUE_KINDS = frozenset({
    "transaction_approvals",
    "announcement_approvals",
    "meeting_minutes",
    "working_day_closed",
    "church_assignment_missing",
    "member_transfers",
    "asset_approvals",
})


def filter_action_queue_for_control_center(queue):
    """Drop items already surfaced in Mission Control KPIs and compliance panel."""
    return [item for item in queue if item.get("kind") not in CONTROL_CENTER_QUEUE_OMIT]


def filter_action_queue_mine(queue):
    """Items the signed-in user is most likely responsible for."""
    return [item for item in queue if item.get("kind") in MY_ACTION_QUEUE_KINDS]


def user_has_asset_approval(user):
    from permissions.checks import can_approve_assets, can_manage_assets

    return can_approve_assets(user) or can_manage_assets(user)


def get_church_leaderboard(request, user, limit=8):
    """Rank churches in scope by MTD giving performance."""
    from django.urls import reverse

    manageable = get_manageable_churches(user).select_related("district")
    if not manageable.exists():
        return []

    _, _, month_start_date = _month_bounds()
    church_ids = list(manageable.values_list("id", flat=True))

    totals = selectors.church_mtd_giving_totals(church_ids, month_start_date)
    member_counts = selectors.member_counts_by_church(church_ids)

    rows = []
    for church in manageable:
        mtd = totals.get(church.id, Decimal("0"))
        rows.append({
            "church_id": church.id,
            "church": church.name,
            "district": church.district.name if church.district_id else "—",
            "members": member_counts.get(church.id, 0),
            "mtd_giving": mtd,
            "focus_url": f"{reverse('dashboard:home')}?church={church.id}",
        })

    rows.sort(key=lambda r: r["mtd_giving"], reverse=True)
    return rows[:limit]


def get_organization_health(request, user, *, compliance=None, kpis=None, pastoral=None):
    """Traffic-light health summary for mission control header."""
    if compliance is None:
        compliance = get_compliance_snapshot(request, user)
    if kpis is None:
        kpis = get_executive_kpis(request, user) or {}
    pastoral = pastoral or {}
    overdue = compliance.get("overdue_count", 0)
    pending = kpis.get("pending_transactions", 0)
    locked = compliance.get("locked_periods", 0)
    working = compliance.get("working_day_issues", 0)
    visitor_stale = pastoral.get("visitor_stale", 0)
    open_transfers = pastoral.get("open_transfers", 0)
    attendance_delta = pastoral.get("attendance_delta")

    if overdue > 0:
        overall = "critical"
        label = "Attention required"
    elif pending > 5 or working > 0 or visitor_stale > 3:
        overall = "warning"
        label = "Items pending"
    elif attendance_delta is not None and attendance_delta < -5:
        overall = "warning"
        label = "Attendance dip"
    elif open_transfers > 5:
        overall = "warning"
        label = "Transfer backlog"
    elif pastoral.get("new_portal_submissions", 0) > 0:
        overall = "warning"
        label = "Pastoral inbox"
    else:
        overall = "healthy"
        label = "Operating normally"

    return {
        "status": overall,
        "label": label,
        "overdue_remittances": overdue,
        "pending_approvals": pending,
        "locked_periods": locked,
        "working_day_issues": working,
        "visitor_stale": visitor_stale,
        "open_transfers": open_transfers,
        "new_portal_submissions": pastoral.get("new_portal_submissions", 0),
    }


def get_secretary_summary(request):
    """Meeting and communication metrics for secretary dashboard."""
    church = get_active_church(request)
    if not church:
        return {}
    now = timezone.now()
    upcoming_qs = selectors.upcoming_meetings_for_church(church, now)
    return {
        "upcoming_meetings": upcoming_qs.count(),
        "next_meetings": upcoming_qs[:5],
    }


def get_this_week_pulse(request):
    """
    Pastoral 'This Week Pulse' — who needs care in the next 7 days.

    Open visitor follow-ups, birthdays, pending transfers, and meetings.
    Requires an active church and member-view permission.
    """
    from datetime import timedelta

    from announcements.calendar_services import attach_calendar_urls, get_upcoming_birthdays
    from django.urls import reverse

    user = request.user
    church = get_active_church(request)
    if not church:
        return None
    if not (can_view_members(user) or can_manage_members(user)):
        return None

    today = timezone.localdate()
    week_end = today + timedelta(days=6)
    now = timezone.now()

    visitors_qs = selectors.open_visitors_for_church(church, limit=5)
    visitor_count = selectors.open_visitors_count_for_church(church)
    visitors = [
        {
            "title": f"{v.first_name} {v.last_name}".strip(),
            "subtitle": f"{v.follow_up_status} · visited {v.visit_date.strftime('%b %d').replace(' 0', ' ')}",
            "url": reverse("members:visitor_edit", kwargs={"pk": v.pk}),
            "status": v.follow_up_status,
        }
        for v in visitors_qs
    ]

    birthdays_raw = get_upcoming_birthdays(request, days=7, limit=8)
    birthdays_raw = attach_calendar_urls(birthdays_raw)
    birthdays = [
        {
            "title": item["title"],
            "subtitle": item.get("subtitle") or "",
            "url": item.get("url") or "",
            "date": item.get("date"),
        }
        for item in birthdays_raw
    ]

    transfers_qs = selectors.pending_transfers_preview_for_church(church, limit=5)
    transfer_count = selectors.pending_transfers_for_church(church).count()
    transfers = []
    for t in transfers_qs:
        direction = "in" if t.to_church_id == church.pk else "out"
        other = t.from_church.name if direction == "in" else t.to_church.name
        transfers.append({
            "title": str(t.member),
            "subtitle": f"{'From' if direction == 'in' else 'To'} {other}",
            "url": reverse("members:transfer_list"),
            "direction": direction,
        })

    meetings = []
    meeting_count = 0
    if can_view_meetings(user) or can_manage_meetings(user):
        meetings_qs = selectors.meetings_this_week_for_church(church, now=now, limit=5)
        meetings = [
            {
                "title": m.title,
                "subtitle": timezone.localtime(m.scheduled_at).strftime("%a %b %d · %I:%M %p"),
                "url": reverse("meetings:detail", kwargs={"pk": m.pk}),
                "when": m.scheduled_at,
            }
            for m in meetings_qs
        ]
        from meetings.models import Meeting, MeetingStatus

        meeting_count = Meeting.objects.filter(
            church=church,
            scheduled_at__gte=now,
            scheduled_at__lte=now + timedelta(days=7),
            status=MeetingStatus.SCHEDULED,
        ).count()

    counts = {
        "visitors": visitor_count,
        "birthdays": len(birthdays),
        "transfers": transfer_count,
        "meetings": meeting_count,
    }
    has_items = any(counts.values())

    return {
        "week_label": f"{today:%b %d} – {week_end:%b %d}".replace(" 0", " "),
        "church_name": church.name,
        "counts": counts,
        "visitors": visitors,
        "birthdays": birthdays,
        "transfers": transfers,
        "meetings": meetings,
        "has_items": has_items,
        "total_open": sum(counts.values()),
    }


def build_home_context(request):
    """Assemble full dashboard context for the home view."""
    from dashboard import metrics
    from dashboard.scope import resolve_dashboard_scope, scope_selection_banner
    from dashboard.widgets import build_kpi_widgets

    user = request.user
    role = get_dashboard_role(user)
    show_finance = (
        can_manage_finances(user)
        or can_view_dashboard_finance(user)
        or can_approve_transactions(user)
    )
    show_treasury_ops = show_finance or can_view_transactions(user)
    show_members = can_view_members(user) or can_manage_members(user)
    show_admin = can_view_all_churches(user) or user.is_superuser
    show_hierarchy = role in ("admin", "overseer", "district_overseer") or show_admin
    is_control_center = role in ("admin", "overseer", "district_overseer")

    scope = resolve_dashboard_scope(request)
    scope_banner = scope_selection_banner(scope, user)

    actions = apply_pinned_quick_actions(request, get_quick_actions(user))
    alerts = get_alerts(request, user)
    show_finance_charts = show_finance and role in (
        "treasury",
        "admin",
        "finance",
        "overseer",
        "district_overseer",
        "leadership",
    )
    show_member_kpis = show_members and role in ("secretary", "members", "member", "leadership")
    show_upcoming_panel = role in ("secretary", "leadership", "members", "member")
    show_announcements_panel = role not in ("treasury",)
    show_this_week_pulse = show_members and role in (
        "secretary", "leadership", "members", "admin", "overseer", "district_overseer",
    )
    # Mission Control finance KPIs live in the top strip; net MTD is on the workspace bar.

    # One primary work surface: teller for treasury ops, otherwise action queue.
    show_teller = False
    if show_treasury_ops:
        church = get_active_church(request)
        show_teller = bool(church) and role == "treasury"
    primary_work = "teller" if show_teller else "queue"
    show_action_queue = True
    # Treasury: teller leads; queue stays but does not compete for first attention.
    show_action_queue_sidebar = primary_work == "teller"

    action_queue_full = get_action_queue(request, user)
    if is_control_center:
        action_queue = filter_action_queue_for_control_center(action_queue_full)
        action_queue_scope = []
    else:
        mine = filter_action_queue_mine(action_queue_full)
        action_queue = mine if mine else action_queue_full
        action_queue_scope = action_queue_full if len(action_queue_full) > len(action_queue) else []

    context = {
        "dashboard_role": role,
        "role_label": user.get_role_display(),
        "role_focus": get_role_focus(role),
        "current_time": timezone.now(),
        "quick_actions": actions[:3],
        "quick_actions_more": [],
        "alerts": alerts[:3],
        "alerts_extra_count": max(0, len(alerts) - 3),
        "action_queue": action_queue,
        "action_queue_scope": action_queue_scope,
        "quick_actions_all": actions,
        "show_finance": show_finance,
        "show_finance_charts": show_finance_charts,
        "show_member_kpis": show_member_kpis,
        "show_upcoming_panel": show_upcoming_panel,
        "show_announcements_panel": show_announcements_panel,
        "show_this_week_pulse": show_this_week_pulse,
        "show_leaderboard": is_control_center,
        "show_members": show_members,
        "show_admin": show_admin,
        "show_hierarchy": show_hierarchy,
        "is_control_center": is_control_center,
        "dashboard_scope": scope,
        "scope_banner": scope_banner,
        "emphasize_approvals": role == "leadership",
        "primary_work": primary_work,
        "show_action_queue": show_action_queue,
        "show_action_queue_sidebar": show_action_queue_sidebar,
        "show_role_focus_chips": False,
    }

    if is_control_center:
        manageable = get_manageable_churches(user)
        church_ids = list(manageable.values_list("id", flat=True)) if manageable.exists() else []
        compliance = get_compliance_snapshot(
            request, user, church_ids=church_ids, manageable=manageable
        )
        active_church = get_active_church(request)
        executive_kpis = get_executive_kpis(
            request,
            user,
            church_ids=church_ids,
            manageable=manageable,
            compliance=compliance,
            active_church=active_church,
        )
        context["executive_kpis"] = executive_kpis
        context["compliance_snapshot"] = compliance
        context["church_leaderboard"] = get_church_leaderboard(request, user)
        context["org_health"] = get_organization_health(
            request, user, compliance=compliance, kpis=executive_kpis or {}
        )

    if show_hierarchy:
        context["hierarchy_rollup"] = get_hierarchy_rollup(request, user)

    if role == "secretary" or user.role == UserRole.SECRETARY:
        context.update(get_secretary_summary(request))

    if show_finance:
        context.update(get_financial_summary(request))

    if is_control_center and context.get("executive_kpis"):
        ek = context["executive_kpis"]
        context["tithe_total"] = ek["mtd_tithe"]
        context["combined_total"] = ek["mtd_combined"]
        context["monthly_cutoff_total"] = ek["mtd_remittance_payable"]
        context["church_income_total"] = ek["mtd_income"]
        context["expense_total"] = ek["mtd_expense"]
        context["net_balance"] = ek["mtd_net"]

    if show_treasury_ops:
        church = get_active_church(request)
        if church:
            from transactions.treasury import get_cash_position, get_teller_daily_summary

            context["cash_position"] = get_cash_position(church)
            context["teller_console"] = get_teller_daily_summary(church)
            context["show_teller_console"] = True
            context["suppress_workspace_cash"] = False
        else:
            context["show_teller_console"] = False
            context["suppress_workspace_cash"] = False
    else:
        context["show_teller_console"] = False
        context["suppress_workspace_cash"] = False

    if show_members:
        context.update(get_member_summary(request))

    if show_this_week_pulse:
        context["this_week_pulse"] = get_this_week_pulse(request)
    else:
        context["this_week_pulse"] = None

    if show_admin:
        context.update(get_admin_summary(user))

    context["recent_announcements"] = visible_announcements(request.user).order_by("-created_at")[:5]

    from announcements.calendar_services import (
        attach_calendar_urls,
        calendar_summary_counts_from_items,
        get_communications_calendar,
    )

    upcoming = get_communications_calendar(request, days=30, limit=8)
    upcoming = attach_calendar_urls(upcoming)
    if not can_view_members(user) and not can_manage_members(user):
        for item in upcoming:
            if item["kind"] == "birthday":
                item["url"] = ""
    context["upcoming_preview"] = upcoming
    # Counts for the preview window — derived from already-fetched items (no re-query)
    context["upcoming_counts"] = calendar_summary_counts_from_items(upcoming)

    if role == "member":
        context["member_home_kpis"] = {
            "announcements": len(context["recent_announcements"]),
            "upcoming": context["upcoming_counts"].get("total", 0),
        }

    finance_bundle = context.get("executive_kpis")
    if finance_bundle is None and scope.church_ids:
        manageable = get_manageable_churches(user)
        church_ids = list(scope.church_ids)
        now, _, month_start_date = _month_bounds()
        compliance = {}
        if show_finance:
            compliance = get_compliance_snapshot(
                request, user, church_ids=church_ids, manageable=manageable
            )
        if show_finance and scope.finance_church_ids:
            finance_bundle = metrics.build_executive_finance_bundle(
                church_ids=church_ids,
                finance_church_ids=list(scope.finance_church_ids),
                finance_scope_label=scope.finance_scope_label,
                manageable=manageable,
                month_start_date=month_start_date,
                period_label=now.strftime("%B %Y"),
                compliance=compliance or {"overdue_count": 0, "locked_periods": 0},
                finance_scope="church" if scope.level == "CHURCH" else "scope",
            )
        elif show_members:
            finance_bundle = {
                "member_count": metrics.aggregate_member_count(scope.church_ids),
            }

    context["dashboard_kpi_widgets"] = build_kpi_widgets(
        user=user,
        dashboard_role=role,
        scope=scope,
        finance_bundle=finance_bundle,
        pending_transfers=context.get("pending_transfers", 0),
        member_home_kpis=context.get("member_home_kpis"),
        is_control_center=is_control_center,
    )

    if show_finance_charts and scope.finance_church_ids:
        labels, income, expense = metrics.income_expense_trend_chart(list(scope.finance_church_ids))
        context["trend_labels"] = labels
        context["income_data"] = income
        context["expense_data"] = expense
        context["show_finance_chart"] = True
    else:
        context["show_finance_chart"] = False

    if scope.level == "CHURCH" and scope.primary_church:
        context["has_active_church"] = True
    elif context.get("has_active_church") is None:
        context["has_active_church"] = bool(get_active_church(request))

    from dashboard import home_panels

    context["notification_inbox"] = home_panels.get_notification_inbox(user)
    context["attendance_panel"] = home_panels.get_attendance_panel(request)
    context["visitor_funnel"] = home_panels.get_visitor_funnel_panel(request)
    context["settlement_strip"] = home_panels.get_settlement_strip(request, list(scope.church_ids))
    context["budget_glance"] = home_panels.get_budget_glance(request)
    context["recent_activity"] = home_panels.get_recent_activity_panel(
        request, list(scope.finance_church_ids or scope.church_ids)
    )
    if role in ("member", "members", "leadership"):
        context["member_role_extras"] = home_panels.get_member_role_extras(request)
    else:
        context["member_role_extras"] = None
    context["dashboard_coaching"] = home_panels.get_dashboard_coaching_hints(context)
    context["portal_staff_alerts"] = home_panels.get_portal_staff_alerts(request)
    if role in ("member", "members"):
        context["member_portal_banner"] = home_panels.get_member_portal_banner(user)
    else:
        context["member_portal_banner"] = None

    if is_control_center and context.get("org_health") is not None:
        from portal.spiritual_services import count_new_submissions_scope

        pastoral = {"new_portal_submissions": count_new_submissions_scope(user, request)}
        church_ref = scope.primary_church or get_active_church(request)
        if church_ref and show_members:
            funnel = selectors.visitor_funnel_counts_for_church(church_ref)
            pastoral["visitor_stale"] = funnel.get("stale", 0)
            pastoral["open_transfers"] = context.get("pending_transfers") or 0
            snap = selectors.worship_attendance_snapshot_for_church(church_ref)
            if snap and not snap.get("empty") and snap.get("delta") is not None:
                pastoral["attendance_delta"] = snap["delta"]
        context["org_health"] = get_organization_health(
            request,
            user,
            compliance=context.get("compliance_snapshot"),
            kpis=context.get("executive_kpis") or {},
            pastoral=pastoral,
        )

    return context
