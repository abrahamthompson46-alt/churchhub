"""Dashboard widget registry — KPIs follow role, permission, and church vs subtree scope."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from permissions.roles import UserRole
from permissions.checks import (
    can_approve_transactions,
    can_manage_finances,
    can_manage_members,
    can_manage_receipts,
    can_run_cutoff,
    can_view_members,
    can_view_pending_approvals,
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
        "action_items",
        "mtd_tithe",
        "mtd_combined",
        "remittance_payable",
        "active_members",
    ),
    "district": (
        "churches",
        "action_items",
        "giving_mtd",
        "remittance_payable",
        "pending_transfers",
        "active_members",
    ),
    "pastoral": (
        "pending_approvals",
        "pending_transfers",
        "active_members",
        "income_mtd",
        "remittance_payable",
    ),
    "treasury": (
        "income_mtd",
        "expense_mtd",
        "mtd_tithe",
        "remittance_payable",
        "pending_approvals",
        "action_items",
    ),
    "secretary": (
        "active_members",
        "pending_transfers",
        "pending_approvals",
    ),
    "member": ("announcements", "upcoming"),
}


def layout_profile_for_role(dashboard_role: str) -> str:
    return LAYOUT_PROFILES.get(dashboard_role, "pastoral")


def user_can_use_finance_kpis(user) -> bool:
    """Money cards for operational finance roles — not clerks or members."""
    role = getattr(user, "role", "")
    if role in {UserRole.SECRETARY, UserRole.MEMBER}:
        return False
    return (
        can_manage_finances(user)
        or can_approve_transactions(user)
        or can_manage_receipts(user)
        or can_run_cutoff(user)
    )


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
    empty_cta="",
):
    return {
        "id": widget_id,
        "type": "kpi",
        "label": label,
        "value": value,
        "value_is_money": True,
        "hint": hint,
        "empty_cta": empty_cta,
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
        "empty_cta": "",
    }


def _receipts_url(user) -> str:
    if can_manage_receipts(user):
        return "transactions:record_receipt"
    return "transactions:transaction_list"


def _zero_receipt_cta(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if amount == 0:
        return "Open the business day, then record a receipt."
    return ""


def build_kpi_widgets(
    *,
    user,
    dashboard_role,
    scope,
    finance_bundle,
    pending_transfers=0,
    member_home_kpis=None,
    is_control_center=False,
    remittance_enabled=True,
):
    """Permission- and scope-filtered KPI cards with operational destinations."""
    widgets = {}
    hint_scope = scope.finance_scope_label
    period = finance_bundle.get("period_label", "MTD") if finance_bundle else "MTD"
    subtree = scope.level == "SUBTREE"

    can_money = user_can_use_finance_kpis(user)
    show_members = can_view_members(user) or can_manage_members(user)

    if is_control_center and finance_bundle:
        widgets["churches"] = _count_widget(
            "churches",
            "Churches",
            finance_bundle["church_count"],
            f"{finance_bundle.get('district_count', 0)} districts · {hint_scope}",
            "organization:hierarchy",
        )
        widgets["action_items"] = _count_widget(
            "action_items",
            "Action items",
            finance_bundle["action_items"],
            f"{finance_bundle['pending_transactions']} pending · {finance_bundle['overdue_remittances']} overdue",
            "transactions:pending_approvals",
            card_class="cc-kpi-card--danger" if finance_bundle["action_items"] else "",
        )

    if show_members and finance_bundle is not None:
        member_hint = f"Across {hint_scope}" if subtree else "This church"
        widgets["active_members"] = _count_widget(
            "active_members",
            "Active members",
            finance_bundle.get("member_count", 0),
            member_hint,
            "members:list",
        )

    if show_members and pending_transfers:
        widgets["pending_transfers"] = _count_widget(
            "pending_transfers",
            "Pending transfers",
            pending_transfers,
            "Needs attention",
            "members:transfer_list",
            card_class="cc-kpi-card--warning",
        )

    pending_txn = (finance_bundle or {}).get("pending_transactions") or 0
    if pending_txn and (
        can_approve_transactions(user) or can_view_pending_approvals(user)
    ):
        widgets["pending_approvals"] = _count_widget(
            "pending_approvals",
            "Pending approvals",
            pending_txn,
            hint_scope,
            "transactions:pending_approvals",
            card_class="cc-kpi-card--warning",
        )

    finance_ready = (
        can_money
        and finance_bundle
        and scope.finance_church_ids
        and "mtd_tithe" in finance_bundle
    )

    compare = finance_bundle.get("compare_label", "prior month") if finance_bundle else ""

    if finance_ready:

        def _delta(key):
            return finance_bundle.get(f"{key}_delta_pct")

        receipts_url = _receipts_url(user)
        giving_total = finance_bundle["mtd_tithe"] + finance_bundle["mtd_combined"]

        if subtree:
            widgets["giving_mtd"] = _money_widget(
                "giving_mtd",
                "Giving MTD",
                giving_total,
                f"{hint_scope} · {period}",
                "reports:run",
                card_class="cc-kpi-card--primary",
                report_key="hierarchy_rollup",
                delta_pct=_delta("mtd_tithe"),
                compare_label=compare,
                empty_cta=_zero_receipt_cta(giving_total),
            )
        else:
            widgets["mtd_tithe"] = _money_widget(
                "mtd_tithe",
                "Tithe MTD",
                finance_bundle["mtd_tithe"],
                f"{hint_scope} · {period}",
                receipts_url,
                card_class="cc-kpi-card--primary",
                delta_pct=_delta("mtd_tithe"),
                compare_label=compare,
                empty_cta=_zero_receipt_cta(finance_bundle["mtd_tithe"]),
            )
            widgets["mtd_combined"] = _money_widget(
                "mtd_combined",
                "Combined MTD",
                finance_bundle["mtd_combined"],
                f"{hint_scope} · {period}",
                receipts_url,
                card_class="cc-kpi-card--accent",
                delta_pct=_delta("mtd_combined"),
                compare_label=compare,
                empty_cta=_zero_receipt_cta(finance_bundle["mtd_combined"]),
            )

        if not subtree:
            widgets["income_mtd"] = _money_widget(
                "income_mtd",
                "Income MTD",
                finance_bundle["mtd_income"],
                f"{hint_scope} · receipts",
                receipts_url,
                card_class="cc-kpi-card--success",
                delta_pct=_delta("mtd_income"),
                compare_label=compare,
                empty_cta=_zero_receipt_cta(finance_bundle["mtd_income"]),
            )
            widgets["expense_mtd"] = _money_widget(
                "expense_mtd",
                "Expenses MTD",
                finance_bundle["mtd_expense"],
                f"{hint_scope} · {period}",
                "transactions:transaction_list",
                card_class="cc-kpi-card--danger",
                delta_pct=_delta("mtd_expense"),
                compare_label=compare,
            )

        if remittance_enabled:
            widgets["remittance_payable"] = _money_widget(
                "remittance_payable",
                "Remittance payable",
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
    return [widgets[key] for key in order if key in widgets]
