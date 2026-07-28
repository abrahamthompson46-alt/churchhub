"""Dashboard widget registry — one KPI definition for all roles."""

from __future__ import annotations

from decimal import Decimal

from permissions.checks import (
    can_approve_transactions,
    can_manage_finances,
    can_view_dashboard_finance,
    can_view_members,
    can_manage_members,
)

LAYOUT_PROFILES = {
    "admin": "executive",
    "overseer": "executive",
    "district_overseer": "district",
    "treasury": "treasury",
    "finance": "treasury",
    "secretary": "secretary",
    "leadership": "pastoral",
    "members": "pastoral",
    "member": "member",
}

WIDGET_ORDER = {
    "executive": (
        "churches",
        "active_members",
        "mtd_tithe",
        "mtd_combined",
        "remittance_payable",
        "action_items",
    ),
    "district": (
        "mtd_tithe",
        "mtd_combined",
        "remittance_payable",
        "active_members",
        "action_items",
        "churches",
    ),
    "pastoral": (
        "action_items",
        "pending_transfers",
        "active_members",
        "mtd_tithe",
        "mtd_combined",
        "income_mtd",
        "expense_mtd",
    ),
    "treasury": (
        "mtd_tithe",
        "mtd_combined",
        "income_mtd",
        "expense_mtd",
        "remittance_payable",
        "action_items",
    ),
    "secretary": (
        "active_members",
        "pending_transfers",
        "action_items",
        "mtd_tithe",
        "mtd_combined",
    ),
    "member": ("announcements", "upcoming"),
}


def layout_profile_for_role(dashboard_role: str) -> str:
    return LAYOUT_PROFILES.get(dashboard_role, "pastoral")


def _money_widget(
    widget_id,
    label,
    value,
    hint,
    url_name,
    card_class="",
    report_key="",
    delta_pct=None,
    compare_label="",
):
    return {
        "id": widget_id,
        "type": "kpi",
        "label": label,
        "value": value,
        "value_is_money": True,
        "hint": hint,
        "url_name": url_name,
        "report_key": report_key,
        "card_class": card_class,
        "delta_pct": delta_pct,
        "compare_label": compare_label,
    }


def _count_widget(widget_id, label, value, hint, url_name, card_class="", report_key=""):
    return {
        "id": widget_id,
        "type": "kpi",
        "label": label,
        "value": value,
        "value_is_money": False,
        "hint": hint,
        "url_name": url_name,
        "report_key": report_key,
        "card_class": card_class,
    }


def build_kpi_widgets(
    *,
    user,
    dashboard_role,
    scope,
    finance_bundle,
    pending_transfers=0,
    member_home_kpis=None,
    is_control_center=False,
):
    """
    Permission-filtered KPI cards; same widgets for church and subtree (labels differ).
    """
    widgets = {}
    hint_scope = scope.finance_scope_label
    period = finance_bundle.get("period_label", "MTD") if finance_bundle else "MTD"

    can_fin = can_manage_finances(user) or can_view_dashboard_finance(user)
    can_fin = can_fin or can_approve_transactions(user)
    show_members = can_view_members(user) or can_manage_members(user)

    if is_control_center and finance_bundle:
        widgets["churches"] = _count_widget(
            "churches",
            "Churches",
            finance_bundle["church_count"],
            f"{finance_bundle.get('district_count', 0)} districts",
            "organization:hierarchy",
        )
        widgets["action_items"] = _count_widget(
            "action_items",
            "Action Items",
            finance_bundle["action_items"],
            f"{finance_bundle['pending_transactions']} txn · {finance_bundle['overdue_remittances']} overdue",
            "transactions:pending_approvals",
            card_class="cc-kpi-card--danger",
        )

    if show_members and finance_bundle is not None:
        member_hint = "Across scope" if scope.level == "SUBTREE" else "Directory"
        widgets["active_members"] = _count_widget(
            "active_members",
            "Active Members",
            finance_bundle.get("member_count", 0),
            member_hint,
            "members:list",
        )

    if show_members and pending_transfers and not is_control_center:
        widgets["pending_transfers"] = _count_widget(
            "pending_transfers",
            "Pending Transfers",
            pending_transfers,
            "Needs attention",
            "members:transfer_list",
            card_class="cc-kpi-card--warning",
        )

    finance_ready = (
        can_fin
        and finance_bundle
        and scope.finance_church_ids
        and "mtd_tithe" in finance_bundle
    )

    compare = finance_bundle.get("compare_label", "prior month") if finance_bundle else ""

    if finance_ready:

        def _delta(key):
            return finance_bundle.get(f"{key}_delta_pct")

        widgets["mtd_tithe"] = _money_widget(
            "mtd_tithe",
            "Tithe MTD",
            finance_bundle["mtd_tithe"],
            f"{hint_scope} · {period}",
            "reports:run",
            card_class="cc-kpi-card--primary",
            report_key="hierarchy_rollup" if is_control_center else "tithe_report",
            delta_pct=_delta("mtd_tithe"),
            compare_label=compare,
        )
        widgets["mtd_combined"] = _money_widget(
            "mtd_combined",
            "Combined MTD",
            finance_bundle["mtd_combined"],
            f"{hint_scope} · {period}",
            "reports:run",
            card_class="cc-kpi-card--accent",
            report_key="hierarchy_rollup" if is_control_center else "financial_summary",
            delta_pct=_delta("mtd_combined"),
            compare_label=compare,
        )
        widgets["income_mtd"] = _money_widget(
            "income_mtd",
            "Income MTD",
            finance_bundle["mtd_income"],
            "All receipts",
            "transactions:transaction_list",
            card_class="cc-kpi-card--success",
            delta_pct=_delta("mtd_income"),
            compare_label=compare,
        )
        widgets["expense_mtd"] = _money_widget(
            "expense_mtd",
            "Expenses MTD",
            finance_bundle["mtd_expense"],
            period,
            "transactions:transaction_list",
            card_class="cc-kpi-card--danger",
            delta_pct=_delta("mtd_expense"),
            compare_label=compare,
        )
        widgets["remittance_payable"] = _money_widget(
            "remittance_payable",
            "Remittance Payable",
            finance_bundle["mtd_remittance_payable"],
            f"{hint_scope} · MTD",
            "dashboard:cutoff",
            card_class="cc-kpi-card--warning",
        )

    if member_home_kpis:
        widgets["announcements"] = _count_widget(
            "announcements",
            "Announcements",
            member_home_kpis.get("announcements", 0),
            "Recent",
            "announcements:announcement_list",
        )
        widgets["upcoming"] = _count_widget(
            "upcoming",
            "Upcoming",
            member_home_kpis.get("upcoming", 0),
            "Next 30 days",
            "announcements:upcoming_calendar",
            card_class="cc-kpi-card--accent",
        )

    order = WIDGET_ORDER.get(layout_profile_for_role(dashboard_role), WIDGET_ORDER["pastoral"])
    ordered = []
    seen = set()
    for key in order:
        if key in widgets:
            ordered.append(widgets[key])
            seen.add(key)
    for key, widget in widgets.items():
        if key not in seen:
            ordered.append(widget)
    return ordered
