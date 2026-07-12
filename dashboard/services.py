"""Dashboard services — role context, metrics, notifications."""

import json
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounts.models import UserRole
from announcements.models import Announcement
from announcements.services import visible_announcements
from church_system.church_scope import filter_by_church, get_active_church
from church_system.denomination_scope import get_user_denomination
from dashboard.models import Notification
from members.models import Member, MemberTransfer, TransferStatus
from organization.models import Conference, District
from permissions.checks import (
    can_approve_announcements,
    can_approve_minutes,
    can_approve_transactions,
    can_create_announcements,
    can_manage_finances,
    can_manage_meetings,
    can_manage_members,
    can_manage_users,
    can_view_all_churches,
    can_view_meetings,
    can_view_members,
)
from permissions.scoping import get_manageable_churches
from transactions.models import FinancialPeriod, MonthlyCutoff, Transaction, TransactionLine

REMIT_PAYABLE_TYPES = ("TITHE_REMIT_PAYABLE", "COMBINED_REMIT_PAYABLE")
INCOME_REMIT_TYPES = ("TITHE", "COMBINED")


def notify_user(user, title, message, category="INFO", action_url=""):
    """Create an in-app notification for a user."""
    if not user or not user.is_active:
        return None
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        category=category,
        action_url=action_url,
    )


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
    return abs(
        lines_qs.filter(account__account_type=acc_type).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )


def _compute_remittance_payable_mtd(church, month_start_date):
    """Sum remittance payable GL lines for a church/month without creating MonthlyCutoff."""
    approved_filter = {
        "transaction__church": church,
        "transaction__approval_status": "APPROVED",
        "transaction__is_voided": False,
        "transaction__date__month": month_start_date.month,
        "transaction__date__year": month_start_date.year,
    }
    tithe = abs(
        TransactionLine.objects.filter(
            account__account_type="TITHE_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    combined = abs(
        TransactionLine.objects.filter(
            account__account_type="COMBINED_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return tithe, combined, tithe + combined


def get_financial_summary(request):
    """Core financial KPIs for finance dashboards (MTD primary)."""
    now, month_start, month_start_date = _month_bounds()
    transactions = filter_by_church(Transaction.objects.all(), request)
    approved = transactions.filter(approval_status="APPROVED", is_voided=False)
    mtd_approved = approved.filter(date__gte=month_start_date)
    mtd_lines = TransactionLine.objects.filter(transaction__in=mtd_approved)
    all_time_lines = TransactionLine.objects.filter(transaction__in=approved)

    tithe_total = _sum_account_type(mtd_lines, "TITHE")
    combined_total = _sum_account_type(mtd_lines, "COMBINED")
    income_total = _sum_account_type(mtd_lines, "INCOME")
    expense_total = _sum_account_type(mtd_lines, "EXPENSE")

    church = get_active_church(request)
    monthly_cutoff_total = Decimal("0")
    if church:
        existing = MonthlyCutoff.objects.filter(church=church, month=month_start_date).first()
        if existing:
            monthly_cutoff_total = existing.total_payable
        else:
            _, _, monthly_cutoff_total = _compute_remittance_payable_mtd(church, month_start_date)
    else:
        monthly_cutoff_total = abs(
            mtd_lines.filter(account__account_type__in=REMIT_PAYABLE_TYPES).aggregate(
                t=Sum("amount")
            )["t"]
            or Decimal("0")
        )

    six_months_ago = (now - relativedelta(months=5)).replace(day=1)
    six_months_ago_date = (
        timezone.localdate(six_months_ago) if timezone.is_aware(six_months_ago) else six_months_ago.date()
    )
    trend_qs = (
        all_time_lines.filter(
            transaction__date__gte=six_months_ago_date,
            account__account_type__in=["INCOME", "EXPENSE"],
        )
        .annotate(month=TruncMonth("transaction__date"))
        .values("month", "account__account_type")
        .annotate(total=Sum("amount"))
    )

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

    return {
        "kpi_period_label": "Month to date",
        "cutoff_metric_label": "Remittance payable (MTD)",
        "tithe_total": tithe_total,
        "combined_total": combined_total,
        "church_income_total": income_total,
        "expense_total": expense_total,
        "net_balance": income_total - expense_total,
        "monthly_cutoff_total": monthly_cutoff_total,
        "tithe_total_all_time": _sum_account_type(all_time_lines, "TITHE"),
        "combined_total_all_time": _sum_account_type(all_time_lines, "COMBINED"),
        "pending_count": transactions.filter(approval_status="PENDING").count(),
        "recent_transactions": approved.select_related("church").order_by("-date")[:5],
        "trend_labels": json.dumps(trend_labels),
        "income_data": json.dumps(income_data),
        "expense_data": json.dumps(expense_data),
        "has_active_church": bool(church),
    }


def get_member_summary(request):
    members = filter_by_church(Member.objects.all(), request)
    active_church = get_active_church(request)
    transfers = MemberTransfer.objects.filter(status=TransferStatus.PENDING)
    if active_church:
        transfers = transfers.filter(Q(from_church=active_church) | Q(to_church=active_church))

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

    user_denom = get_user_denomination(user)
    conferences = Conference.objects.filter(id__in=conference_ids)
    if user_denom:
        conferences = conferences.filter(denomination=user_denom)

    pending_ann = Announcement.objects.filter(
        is_approved=False, is_archived=False, is_rejected=False
    )
    if church_ids:
        pending_ann = pending_ann.filter(
            Q(church_id__in=church_ids) | Q(church__isnull=True)
        )
    elif user_denom:
        pending_ann = pending_ann.filter(
            Q(church__district__zone__conference__denomination=user_denom)
            | Q(church__isnull=True)
        )
    else:
        pending_ann = pending_ann.none() if not user.is_superuser else pending_ann

    return {
        "conference_count": conferences.count(),
        "church_count": len(church_ids),
        "district_count": District.objects.filter(id__in=district_ids).count(),
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
        _add(_item("Ledger Entry", "ledger:entry", "bi-journal-plus"))
        _add(_item("Monthly Cut-off", "dashboard:cutoff", "bi-calendar-check"))
        _add(_item("Pending Approvals", "transactions:pending_approvals", "bi-hourglass-split"))
        if user.church_id and church_has_feature(user.church, "remittance"):
            _add(_item("Remittance", "transactions:record_remittance", "bi-send"))
    elif role == "secretary":
        if can_manage_members(user):
            _add(_item("Add Member", "members:add", "bi-person-plus"))
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
            _add(_item("Members", "members:list", "bi-people"))
    elif role in ("overseer", "district_overseer", "admin"):
        _add(_item("Organization", "organization:hierarchy", "bi-diagram-3"))
        _add(_item("Roll-up Report", report_key="hierarchy_rollup", icon="bi-bar-chart-steps"))
        _add(_item("Churches", "organization:hierarchy", "bi-building"))
    else:
        if can_manage_finances(user):
            _add(_item("Ledger Entry", "ledger:entry", "bi-journal-plus"))
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
            _add(_item("News Queue", "announcements:pending_approvals", "bi-megaphone"))
        if can_manage_users(user):
            _add(_item("Invite User", "accounts:invite_user", "bi-envelope-plus"))
        if can_view_all_churches(user):
            _add(_item("Organization", "organization:hierarchy", "bi-diagram-3"))
            _add(_item("Roll-up Report", report_key="hierarchy_rollup", icon="bi-bar-chart-steps"))
        if can_create_announcements(user):
            _add(_item("New Announcement", "announcements:create_announcement", "bi-megaphone"))

    if not actions and not can_manage_finances(user) and not can_view_members(user):
        _add(_item("Announcements", "announcements:announcement_list", "bi-newspaper"))

    _add(_item("Upcoming", "announcements:upcoming_calendar", "bi-calendar-heart"))
    return actions


def get_alerts(request, user):
    """Actionable alert items for the dashboard banner."""
    alerts = []
    church = get_active_church(request)

    if can_approve_transactions(user):
        pending = filter_by_church(
            Transaction.objects.filter(approval_status="PENDING"), request
        ).count()
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
        current_locked = FinancialPeriod.objects.filter(
            church=church, year=now.year, month=now.month, is_locked=True
        ).exists()
        if current_locked:
            alerts.append({
                "level": "info",
                "text": f"Financial period {now.strftime('%B %Y')} is locked.",
                "url_name": "transactions:period_list",
            })

        prior_month = (now.replace(day=1) - relativedelta(months=1)).date().replace(day=1)
        overdue = MonthlyCutoff.objects.filter(
            church=church, month=prior_month, transferred=False
        ).first()
        if overdue and overdue.total_payable > 0:
            alerts.append({
                "level": "danger",
                "text": (
                    f"Remittance overdue for {prior_month.strftime('%B %Y')} "
                    f"(₵ {overdue.total_payable:,.2f} payable)."
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
    church_rows = list(
        manageable.values("id", "district_id", "district__name")
    )
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

    base_lines = TransactionLine.objects.filter(
        transaction__church_id__in=church_ids,
        transaction__date__gte=month_start_date,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        account__account_type__in=REMIT_PAYABLE_TYPES + INCOME_REMIT_TYPES,
    )

    aggregates = (
        base_lines.values("transaction__church__district_id", "account__account_type")
        .annotate(total=Sum("amount"))
    )

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
        if acc == "TITHE":
            by_district[did]["tithe"] += amount
        elif acc == "COMBINED":
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


def get_compliance_snapshot(request, user):
    """Organization compliance indicators for executive dashboard."""
    manageable = get_manageable_churches(user)
    if not manageable.exists():
        return {}

    church_ids = list(manageable.values_list("id", flat=True))
    now = timezone.now()
    prior_month = (now.replace(day=1) - relativedelta(months=1)).date().replace(day=1)

    overdue_qs = MonthlyCutoff.objects.filter(
        church_id__in=church_ids,
        month=prior_month,
        transferred=False,
    ).annotate(payable=F("total_tithe") + F("total_combined")).filter(
        payable__gt=0
    ).select_related("church").order_by("-payable")

    overdue = overdue_qs[:5]

    locked_periods = FinancialPeriod.objects.filter(
        church_id__in=church_ids,
        year=now.year,
        month=now.month,
        is_locked=True,
    ).count()

    working_day_issues = 0
    if can_manage_finances(user):
        from transactions.services import get_working_day_status

        for church in manageable:
            if not get_working_day_status(church)["is_open"]:
                working_day_issues += 1

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


def get_executive_kpis(request, user):
    """Organization-wide KPIs for CEO / overseer control center."""
    manageable = get_manageable_churches(user)
    if not manageable.exists():
        return None

    church_ids = list(manageable.values_list("id", flat=True))
    now, _, month_start_date = _month_bounds()

    mtd_lines = TransactionLine.objects.filter(
        transaction__church_id__in=church_ids,
        transaction__date__gte=month_start_date,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
    )

    mtd_tithe = _sum_account_type(mtd_lines, "TITHE")
    mtd_combined = _sum_account_type(mtd_lines, "COMBINED")
    mtd_income = _sum_account_type(mtd_lines, "INCOME")
    mtd_expense = _sum_account_type(mtd_lines, "EXPENSE")
    mtd_remit = abs(
        mtd_lines.filter(account__account_type__in=REMIT_PAYABLE_TYPES).aggregate(
            t=Sum("amount")
        )["t"]
        or Decimal("0")
    )

    pending_txn = Transaction.objects.filter(
        church_id__in=church_ids,
        approval_status="PENDING",
    ).count()

    member_count = Member.objects.filter(
        church_id__in=church_ids,
        is_active=True,
    ).count()

    compliance = get_compliance_snapshot(request, user)

    return {
        "period_label": now.strftime("%B %Y"),
        "church_count": len(church_ids),
        "district_count": manageable.values("district_id").distinct().count(),
        "member_count": member_count,
        "mtd_tithe": mtd_tithe,
        "mtd_combined": mtd_combined,
        "mtd_income": mtd_income,
        "mtd_expense": mtd_expense,
        "mtd_remittance_payable": mtd_remit,
        "mtd_net": mtd_income - mtd_expense,
        "pending_transactions": pending_txn,
        "overdue_remittances": compliance.get("overdue_count", 0),
        "locked_periods": compliance.get("locked_periods", 0),
        "action_items": pending_txn + compliance.get("overdue_count", 0),
    }


def get_action_queue(request, user):
    """Prioritized operational action queue for the control center."""
    queue = []
    church = get_active_church(request)
    manageable = get_manageable_churches(user)
    church_ids = list(manageable.values_list("id", flat=True)) if manageable.exists() else []

    def _add(priority, title, subtitle, *, count=0, url_name="", icon="bi-circle", report_key="", url_suffix=""):
        queue.append({
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
        pending = Transaction.objects.filter(
            church_id__in=church_ids,
            approval_status="PENDING",
        ).count()
        if pending:
            _add(
                "high",
                "Transaction approvals",
                "Awaiting pastor or treasury sign-off",
                count=pending,
                url_name="transactions:pending_approvals",
                icon="bi-check2-circle",
            )

    if church_ids:
        prior_month = (timezone.now().replace(day=1) - relativedelta(months=1)).date().replace(day=1)
        overdue = MonthlyCutoff.objects.filter(
            church_id__in=church_ids,
            month=prior_month,
            transferred=False,
        ).annotate(payable=F("total_tithe") + F("total_combined")).filter(
            payable__gt=0
        ).count()
        if overdue:
            _add(
                "critical",
                "Overdue remittances",
                f"{prior_month.strftime('%B %Y')} district remittance not transferred",
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
                "Communications awaiting review",
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
                count=pending_mins,
                url_name="meetings:pending_minutes",
                icon="bi-journal-text",
            )

    if church_ids and user_has_asset_approval(user):
        from assets.models import FixedAsset

        pending_assets = FixedAsset.objects.filter(
            church_id__in=church_ids,
            status="PENDING_APPROVAL",
        ).count()
        if pending_assets:
            _add(
                "medium",
                "Fixed asset approvals",
                "Capital acquisitions awaiting activation",
                count=pending_assets,
                url_name="assets:asset_list",
                url_suffix="?status=PENDING_APPROVAL",
                icon="bi-box-seam",
            )

    if can_manage_members(user) or can_view_members(user):
        transfers = MemberTransfer.objects.filter(status=TransferStatus.PENDING)
        if church:
            transfers = transfers.filter(Q(from_church=church) | Q(to_church=church))
        elif church_ids:
            transfers = transfers.filter(
                Q(from_church_id__in=church_ids) | Q(to_church_id__in=church_ids)
            )
        transfer_count = transfers.count()
        if transfer_count:
            _add(
                "low",
                "Member transfers",
                "Membership moves awaiting processing",
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
                url_name="transactions:period_list",
                icon="bi-calendar-x",
            )

    if not user.church and user.requires_church:
        _add(
            "critical",
            "Church assignment missing",
            "Contact an administrator to assign your account",
            url_name="accounts:profile",
            icon="bi-person-exclamation",
        )

    queue.sort(key=lambda item: item["priority_score"], reverse=True)
    return queue[:12]


def user_has_asset_approval(user):
    from permissions.checks import can_approve_assets, can_manage_assets

    return can_approve_assets(user) or can_manage_assets(user)


def get_church_leaderboard(request, user, limit=8):
    """Rank churches in scope by MTD giving performance."""
    manageable = get_manageable_churches(user).select_related("district")
    if not manageable.exists():
        return []

    _, _, month_start_date = _month_bounds()
    church_ids = list(manageable.values_list("id", flat=True))

    line_aggs = (
        TransactionLine.objects.filter(
            transaction__church_id__in=church_ids,
            transaction__date__gte=month_start_date,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__account_type__in=INCOME_REMIT_TYPES,
        )
        .values("transaction__church_id")
        .annotate(total=Sum("amount"))
    )
    totals = {
        row["transaction__church_id"]: abs(row["total"] or Decimal("0"))
        for row in line_aggs
    }

    member_aggs = (
        Member.objects.filter(church_id__in=church_ids, is_active=True)
        .values("church_id")
        .annotate(count=Count("id"))
    )
    member_counts = {row["church_id"]: row["count"] for row in member_aggs}

    rows = []
    for church in manageable:
        mtd = totals.get(church.id, Decimal("0"))
        rows.append({
            "church": church.name,
            "district": church.district.name if church.district_id else "—",
            "members": member_counts.get(church.id, 0),
            "mtd_giving": mtd,
        })

    rows.sort(key=lambda r: r["mtd_giving"], reverse=True)
    return rows[:limit]


def get_organization_health(request, user):
    """Traffic-light health summary for mission control header."""
    compliance = get_compliance_snapshot(request, user)
    kpis = get_executive_kpis(request, user) or {}
    overdue = compliance.get("overdue_count", 0)
    pending = kpis.get("pending_transactions", 0)
    locked = compliance.get("locked_periods", 0)
    working = compliance.get("working_day_issues", 0)

    if overdue > 0:
        overall = "critical"
        label = "Attention required"
    elif pending > 5 or working > 0:
        overall = "warning"
        label = "Items pending"
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
    }


def get_secretary_summary(request):
    """Meeting and communication metrics for secretary dashboard."""
    from meetings.models import Meeting, MeetingStatus

    church = get_active_church(request)
    if not church:
        return {}
    now = timezone.now()
    upcoming_qs = Meeting.objects.filter(
        church=church,
        scheduled_at__gte=now,
        status=MeetingStatus.SCHEDULED,
    ).order_by("scheduled_at")
    return {
        "upcoming_meetings": upcoming_qs.count(),
        "next_meetings": upcoming_qs[:5],
    }


def build_home_context(request):
    """Assemble full dashboard context for the home view."""
    user = request.user
    role = get_dashboard_role(user)
    show_finance = can_manage_finances(user)
    show_members = can_view_members(user) or can_manage_members(user)
    show_admin = can_view_all_churches(user) or user.is_superuser
    show_hierarchy = role in ("admin", "overseer", "district_overseer") or show_admin
    is_control_center = role in ("admin", "overseer", "district_overseer")

    context = {
        "dashboard_role": role,
        "role_label": user.get_role_display(),
        "role_focus": get_role_focus(role),
        "current_time": timezone.now(),
        "quick_actions": get_quick_actions(user),
        "alerts": get_alerts(request, user),
        "action_queue": get_action_queue(request, user),
        "show_finance": show_finance,
        "show_members": show_members,
        "show_admin": show_admin,
        "show_hierarchy": show_hierarchy,
        "is_control_center": is_control_center,
        "emphasize_approvals": role == "leadership",
    }

    if is_control_center:
        context["executive_kpis"] = get_executive_kpis(request, user)
        context["compliance_snapshot"] = get_compliance_snapshot(request, user)
        context["church_leaderboard"] = get_church_leaderboard(request, user)
        context["org_health"] = get_organization_health(request, user)

    if show_hierarchy:
        context["hierarchy_rollup"] = get_hierarchy_rollup(request, user)

    if role == "secretary" or user.role == UserRole.SECRETARY:
        context.update(get_secretary_summary(request))

    if show_finance:
        context.update(get_financial_summary(request))

    if show_members:
        context.update(get_member_summary(request))

    if show_admin:
        context.update(get_admin_summary(user))

    context["recent_announcements"] = visible_announcements(request.user).order_by("-created_at")[:5]

    from announcements.calendar_services import (
        attach_calendar_urls,
        calendar_summary_counts,
        get_communications_calendar,
    )

    upcoming = get_communications_calendar(request, days=30, limit=8)
    upcoming = attach_calendar_urls(upcoming)
    if not can_view_members(user) and not can_manage_members(user):
        for item in upcoming:
            if item["kind"] == "birthday":
                item["url"] = ""
    context["upcoming_preview"] = upcoming
    # Lighter preview window already limited; counts use same 30-day window
    context["upcoming_counts"] = calendar_summary_counts(request, days=30)

    return context
