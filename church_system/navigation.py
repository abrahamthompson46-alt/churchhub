"""
Central navigation registry for ChurchHub.

Top bar: ChurchHub brand + utilities.
Menu bar: Home, Members, Finance, Reports, Church Life, Organization, Administration.

Internal menu ids (people, communications, settings) stay stable for badges and CSS.
"""

from permissions.checks import (
    can_approve_announcements,
    can_approve_minutes,
    can_archive_announcements,
    can_create_announcements,
    can_add_members,
    can_invite_users,
    can_manage_asset_policy,
    can_manage_assets,
    can_manage_baptisms,
    can_manage_contribution_campaigns,
    can_manage_budgets,
    can_manage_church_history,
    can_manage_departments,
    can_manage_expenses,
    can_manage_families,
    can_manage_finances,
    can_manage_giving,
    can_manage_gl_categories,
    can_manage_institution_branding,
    can_manage_leadership,
    can_manage_ledger_entries,
    can_manage_meetings,
    can_manage_members,
    can_manage_organization,
    can_manage_overrides,
    can_manage_payroll,
    can_manage_payroll_policy,
    can_manage_permissions,
    can_manage_receipts,
    can_record_contributions,
    can_manage_reconciliation,
    can_manage_remittance_policy,
    can_manage_settlements,
    can_manage_spiritual_gifts,
    can_manage_member_configuration,
    can_manage_member_lookups,
    can_manage_occupations,
    can_manage_users,
    can_manage_welfare_cases,
    can_manage_working_day,
    can_onboard_churches,
    can_run_cutoff,
    can_transfer_members,
    can_view_activity_logs,
    can_view_all_churches,
    can_view_announcements,
    can_view_assets,
    can_view_audit_log,
    can_view_budgets,
    can_view_contribution_reports,
    can_view_church_history,
    can_view_dashboard_finance,
    can_view_finance_reports,
    can_view_giving,
    can_view_ledger,
    can_view_meetings,
    can_view_member_records,
    can_view_members,
    can_view_own_payslips,
    can_view_payroll,
    can_view_pending_approvals,
    can_view_permission_audit,
    can_view_reconciliation,
    can_view_remittance,
    can_view_reports,
    can_view_transactions,
    can_view_welfare,
)
from permissions.superadmin import is_superadmin
from sitecontrol.services import church_has_feature
from sitecontrol.registration_services import institution_invites_allowed, institution_onboarding_allowed
from reports.registry import REPORT_CATALOG


def _church_feature(church, feature, user=None):
    if user and is_superadmin(user):
        return True
    # Fail closed: without church context, gated features are unavailable.
    if not church:
        return False
    return church_has_feature(church, feature)


def _item(label, url_name="", icon="", report_key="", query=""):
    return {
        "label": label,
        "url_name": url_name,
        "icon": icon,
        "report_key": report_key,
        "query": query,
    }


def _link(menu_id, label, icon, url_name):
    return {"type": "link", "id": menu_id, "label": label, "icon": icon, "url_name": url_name}


def _dropdown(menu_id, label, icon, sections=None, items=None):
    entry = {"type": "dropdown", "id": menu_id, "label": label, "icon": icon}
    if sections:
        entry["sections"] = sections
    if items:
        entry["items"] = items
    return entry


def _section(title, items, theme="default"):
    return {"title": title, "theme": theme, "items": items}


def _can_access_finance(user):
    return (
        can_view_transactions(user)
        or can_manage_finances(user)
        or can_view_ledger(user)
        or can_view_budgets(user)
        or can_manage_budgets(user)
        or can_view_remittance(user)
        or can_manage_remittance_policy(user)
        or can_manage_settlements(user)
        or can_view_welfare(user)
        or can_view_payroll(user)
        or can_view_assets(user)
        or can_manage_payroll(user)
        or can_manage_assets(user)
        or can_manage_receipts(user)
        or can_manage_expenses(user)
        or can_view_pending_approvals(user)
        or can_view_reconciliation(user)
        or can_manage_reconciliation(user)
        or can_manage_ledger_entries(user)
        or can_manage_gl_categories(user)
        or can_manage_asset_policy(user)
    )


def _can_access_people(user):
    return (
        can_view_members(user)
        or can_manage_members(user)
        or can_add_members(user)
        or can_transfer_members(user)
        or can_manage_baptisms(user)
        or can_manage_departments(user)
        or can_manage_families(user)
        or can_manage_leadership(user)
        or can_manage_spiritual_gifts(user)
        or can_view_member_records(user)
        or can_view_meetings(user)
        or can_manage_meetings(user)
    )


def _can_access_communications(user):
    return (
        can_view_announcements(user)
        or can_create_announcements(user)
        or can_approve_announcements(user)
        or can_view_church_history(user)
        or can_manage_church_history(user)
    )


def _can_access_reports(user):
    return (
        can_view_reports(user)
        or can_view_members(user)
        or can_manage_members(user)
        or can_view_finance_reports(user)
        or can_view_audit_log(user)
        or can_view_budgets(user)
        or can_view_giving(user)
        or can_manage_finances(user)
    )


def _can_access_financial_tools(user):
    return (
        can_view_finance_reports(user)
        or can_view_audit_log(user)
        or can_view_budgets(user)
        or can_view_giving(user)
    )


def _finance_sections(user, active_church=None):
    """Daily treasury first — most users post receipts more than they open the GL."""
    sections = []

    treasury_items = []
    if can_manage_receipts(user):
        treasury_items.append(_item("Record Receipt", "transactions:record_receipt", "bi-plus-circle"))
    if can_manage_expenses(user):
        treasury_items.append(_item("Record Expense", "transactions:record_expense", "bi-dash-circle"))
    if can_view_pending_approvals(user):
        treasury_items.append(_item("Pending Approvals", "transactions:pending_approvals", "bi-hourglass-split"))
    if can_view_transactions(user):
        treasury_items.append(_item("Transactions", "transactions:transaction_list", "bi-list-check"))
    if treasury_items:
        sections.append(_section("Daily treasury", treasury_items, "treasury"))

    if can_view_ledger(user) and _church_feature(active_church, "ledger", user):
        ledger_items = []
        if can_manage_ledger_entries(user):
            ledger_items.extend([
                _item("Journal Entry", "ledger:entry", "bi-journal-plus"),
                _item("Journals", "ledger:entries", "bi-journal-check"),
            ])
        ledger_items.append(_item("General Ledger", "ledger:index", "bi-journal-text"))
        ledger_items.append(_item("By Category", "ledger:category_report", "bi-bar-chart"))
        if can_view_ledger(user):
            ledger_items.append(_item("Chart of Accounts", "ledger:accounts", "bi-journal-bookmark"))
        if can_manage_gl_categories(user):
            ledger_items.append(_item("Posting Categories", "ledger:categories", "bi-tags"))
        sections.append(_section("Books", ledger_items, "accounting"))

    planning_items = []
    if (
        (can_view_budgets(user) or can_manage_budgets(user))
        and _church_feature(active_church, "budgets", user)
    ):
        planning_items.append(_item("Budgets", "budgets:list", "bi-calculator"))
    if can_view_reconciliation(user) or can_manage_reconciliation(user):
        planning_items.append(_item("Bank Reconciliation", "transactions:reconciliation_list", "bi-bank"))
    if planning_items:
        sections.append(_section("Planning & cash", planning_items, "planning"))

    if (
        _church_feature(active_church, "remittance", user)
        or can_manage_settlements(user)
    ) and (
        can_view_remittance(user)
        or can_manage_remittance_policy(user)
        or can_manage_settlements(user)
        or can_view_welfare(user)
    ):
        remittance_items = []
        if can_manage_remittance_policy(user) and _church_feature(active_church, "remittance", user):
            remittance_items.append(_item("Remittance Policies", "remittance:index", "bi-percent"))
        if can_manage_settlements(user):
            remittance_items.append(
                _item("Settlement Desk", "remittance:settlements", "bi-arrow-up-right-circle")
            )
        if _church_feature(active_church, "remittance", user) and (
            can_manage_expenses(user) or can_manage_receipts(user) or can_manage_finances(user)
        ):
            remittance_items.append(_item("Remittance Payment", "transactions:record_remittance", "bi-bank"))
        if can_view_welfare(user) and _church_feature(active_church, "remittance", user):
            remittance_items.append(_item("Welfare", "remittance:welfare", "bi-heart-pulse"))
        if remittance_items:
            sections.append(_section("Remittance & welfare", remittance_items, "remittance"))

    if (can_view_payroll(user) or can_manage_payroll(user)) and _church_feature(active_church, "payroll", user):
        payroll_items = [_item("Dashboard", "payroll:index", "bi-currency-exchange")]
        if can_manage_payroll(user):
            payroll_items.extend([
                _item("Employees", "payroll:employee_list", "bi-person-badge"),
                _item("Pay Runs", "payroll:run_list", "bi-calendar2-check"),
                _item("Roll-up", "payroll:hierarchy", "bi-bar-chart-steps"),
                _item("Policies", "payroll:policy_index", "bi-sliders"),
            ])
        sections.append(_section("Payroll", payroll_items, "payroll"))

    if (
        can_view_assets(user) or can_manage_assets(user) or can_manage_asset_policy(user)
    ) and _church_feature(active_church, "assets", user):
        asset_items = [_item("Register", "assets:index", "bi-box-seam")]
        if can_manage_assets(user):
            asset_items.extend([
                _item("All Assets", "assets:asset_list", "bi-list-ul"),
                _item("New Asset", "assets:asset_create", "bi-plus-circle"),
                _item("Activity Log", "assets:activity_log", "bi-journal-text"),
            ])
        if can_manage_asset_policy(user):
            asset_items.extend([
                _item("Categories", "assets:category_list", "bi-tags"),
                _item("Depreciation", "assets:run_depreciation", "bi-calendar-month"),
                _item("Policy", "assets:policy_edit", "bi-sliders"),
            ])
        if can_view_all_churches(user):
            asset_items.append(_item("Roll-up", "assets:hierarchy", "bi-bar-chart-steps"))
        sections.append(_section("Fixed Assets", asset_items, "assets"))

    giving_items = []
    if _church_feature(active_church, "contribution_campaigns", user) and (
        can_view_contribution_reports(user)
        or can_manage_contribution_campaigns(user)
        or can_record_contributions(user)
        or can_manage_finances(user)
    ):
        giving_items.append(_item("Contribution Campaigns", "contributions:campaign_list", "bi-bullseye"))
        if can_manage_contribution_campaigns(user) or can_manage_finances(user):
            giving_items.append(_item("New Campaign", "contributions:campaign_create", "bi-plus-circle"))
    if giving_items:
        sections.append(_section("Contribution campaigns", giving_items, "giving"))

    return sections


def _people_sections(user):
    member_items = []
    if can_view_members(user) or can_manage_members(user):
        member_items.append(_item("Member Directory", "members:list", "bi-list-ul"))
    if can_add_members(user):
        member_items.append(_item("Add Member", "members:add", "bi-person-plus"))
    if can_view_members(user) or can_manage_members(user):
        member_items.append(_item("Visitors", "members:visitor_list", "bi-person-heart"))
    if can_transfer_members(user):
        member_items.append(_item("Transfers", "members:transfer_list", "bi-arrow-left-right"))
    if can_manage_baptisms(user) or can_view_members(user):
        member_items.append(_item("Baptism Register", "members:baptism_register", "bi-droplet"))

    sections = []
    if member_items:
        sections.append(_section("Directory", member_items, "people"))

    group_items = []
    if can_manage_departments(user) or can_view_members(user):
        group_items.append(_item("Departments", "members:department_list", "bi-diagram-2"))
    if can_manage_families(user) or can_view_members(user):
        group_items.append(_item("Families", "members:family_list", "bi-house-heart"))
    if can_manage_leadership(user) or can_view_members(user):
        group_items.append(_item("Leadership", "members:leadership_list", "bi-award"))
    if can_manage_spiritual_gifts(user) or can_view_members(user):
        group_items.append(_item("Spiritual Gifts", "members:spiritual_gift_list", "bi-stars"))
    if group_items:
        sections.append(_section("Households & ministries", group_items, "groups"))

    if can_view_meetings(user) or can_manage_meetings(user):
        meeting_items = [_item("Meetings", "meetings:list", "bi-calendar-event")]
        if can_manage_meetings(user):
            meeting_items.extend([
                _item("Schedule Meeting", "meetings:create", "bi-plus-circle"),
                _item("Attendance", "meetings:attendance_list", "bi-calendar-check"),
            ])
        if can_approve_minutes(user):
            meeting_items.append(_item("Pending Minutes", "meetings:pending_minutes", "bi-hourglass-split"))
        sections.append(_section("Meetings & attendance", meeting_items, "meetings"))

    if can_view_member_records(user):
        sections.append(_section("Membership records", [
            _item("Life Events", "members:record_list", "bi-journal-text"),
        ], "records"))

    return sections


def _reports_sections(user, active_church=None):
    sections = [
        _section("Report Center", [
            _item("Browse All Reports", "reports:index", "bi-grid"),
        ], "reports"),
    ]

    membership_reports = []
    finance_reports = []
    from reports.services import user_may_access_report

    for key, meta in REPORT_CATALOG.items():
        if not user_may_access_report(user, key, active_church=active_church):
            continue
        entry = _item(meta["label"], icon=meta["icon"], report_key=key)
        if meta["permission"] == "members":
            membership_reports.append(entry)
        else:
            finance_reports.append(entry)

    if membership_reports:
        sections.append(_section("Membership", membership_reports, "people"))

    if _can_access_financial_tools(user):
        if finance_reports:
            sections.append(_section("Financial", finance_reports, "analytics"))

        financial_tools = []
        if can_view_finance_reports(user):
            financial_tools.append(
                _item(
                    "Church Financial Overview",
                    "transactions:financial_dashboard",
                    "bi-file-earmark-bar-graph",
                )
            )
        # Budget vs Actual lives only in Report Center catalog (budget_vs_actual) —
        # do not duplicate a second destination to budgets:list.
        if can_view_audit_log(user):
            financial_tools.append(_item("Finance Audit Log", "transactions:audit_log", "bi-shield-check"))
        if financial_tools:
            sections.append(_section("Statements", financial_tools, "treasury"))

        giving_items = []
        if can_view_giving(user) or can_manage_giving(user):
            giving_items.append(_item("Member Giving", "giving:index", "bi-cash-stack"))
        if can_view_welfare(user) or can_manage_welfare_cases(user):
            giving_items.append(
                _item("Member Welfare Statement", "reports:welfare_statement", "bi-heart-pulse")
            )
        if giving_items:
            sections.append(_section("Giving", giving_items, "giving"))

    return sections


def get_main_navigation(user, active_church=None):
    if not user.is_authenticated:
        return []

    nav = []
    home_items = [_item("Overview", "dashboard:home", "bi-speedometer2")]
    if can_run_cutoff(user) or can_view_dashboard_finance(user):
        home_items.append(_item("Monthly Cut-off", "dashboard:cutoff", "bi-calendar-check"))
    if can_manage_working_day(user):
        home_items.append(_item("Working day", "transactions:period_list", "bi-calendar2-week"))
    if len(home_items) == 1:
        nav.append(_link("home", "Home", "bi-house-door", "dashboard:home"))
    else:
        nav.append(_dropdown(
            "home", "Home", "bi-house-door",
            sections=[_section("Dashboard", home_items, "primary")],
        ))

    if _can_access_people(user):
        people_sections = _people_sections(user)
        if people_sections:
            nav.append(_dropdown("people", "Members", "bi-people", sections=people_sections))

    if _can_access_finance(user):
        finance_sections = _finance_sections(user, active_church)
        if finance_sections:
            nav.append(_dropdown("finance", "Finance", "bi-wallet2", sections=finance_sections))

    if _can_access_reports(user):
        nav.append(_dropdown("reports", "Reports", "bi-bar-chart-line", sections=_reports_sections(user, active_church)))

    if _can_access_communications(user):
        comm_sections = []
        calendar_items = []
        if can_view_announcements(user):
            calendar_items.append(
                _item("Upcoming", "announcements:upcoming_calendar", "bi-calendar-heart")
            )
        if can_approve_announcements(user):
            calendar_items.append(
                _item("Pending Announcements", "announcements:pending_approvals", "bi-hourglass-split")
            )
        if calendar_items:
            comm_sections.append(_section("Calendar", calendar_items, "calendar"))

        publishing_items = []
        if can_view_announcements(user) or can_archive_announcements(user):
            publishing_items.append(_item("All Announcements", "announcements:announcement_list", "bi-megaphone"))
        if can_create_announcements(user):
            publishing_items.append(_item("New Announcement", "announcements:create_announcement", "bi-pencil-square"))
        if publishing_items:
            comm_sections.append(_section("Announcements", publishing_items, "communications"))

        if can_create_announcements(user) or can_view_announcements(user):
            comm_sections.append(_section("My Work", [
                _item("My Submissions", "announcements:my_announcements", "bi-inbox"),
            ], "records"))

        history_items = []
        if can_view_church_history(user) or can_manage_church_history(user):
            history_items.append(
                _item("Church History", "organization:church_history_list", "bi-journal-richtext")
            )
        if can_manage_church_history(user):
            history_items.append(
                _item("Add History Entry", "organization:church_history_create", "bi-journal-plus")
            )
        if history_items:
            comm_sections.append(_section("Church History", history_items, "history"))

        if comm_sections:
            nav.append(_dropdown("communications", "Church Life", "bi-broadcast", sections=comm_sections))

    if can_view_all_churches(user):
        org_sections = [
            _section("Browse", [
                _item("Organization Tree", "organization:hierarchy", "bi-diagram-3"),
                _item("All Units Directory", "organization:directory", "bi-list-ul"),
                _item("Churches", "organization:directory", "bi-building", query="level=church"),
                _item("Conferences", "organization:directory", "bi-globe", query="level=conference"),
                _item("Zones", "organization:directory", "bi-layers", query="level=zone"),
                _item("Districts", "organization:directory", "bi-pin-map", query="level=district"),
                _item("Unions", "organization:directory", "bi-globe2", query="level=union"),
            ], "hierarchy"),
        ]
        if institution_onboarding_allowed() and can_onboard_churches(user):
            org_sections.append(_section("Onboarding", [
                _item("Onboard Church", "organization:church_onboard", "bi-building-add"),
                _item("Add Conference", "organization:conference_create", "bi-globe"),
            ], "onboarding"))
        if can_manage_organization(user):
            org_sections.append(_section("Add Structure", [
                _item("General Conference", "organization:general_conference_create", "bi-building"),
                _item("Union", "organization:union_create", "bi-globe2"),
                _item("Zone", "organization:zone_create", "bi-layers"),
                _item("District", "organization:district_create", "bi-pin-map"),
            ], "structure"))
        nav.append(_dropdown("organization", "Organization", "bi-diagram-3", sections=org_sections))

    settings_sections = []

    config_items = []
    if (
        can_manage_member_configuration(user)
        or can_manage_occupations(user)
        or can_manage_member_lookups(user)
        or can_manage_members(user)
    ):
        config_items.append(_item("Configuration", "members:configuration", "bi-sliders"))
    if can_manage_occupations(user) or can_manage_members(user):
        config_items.append(_item("Occupations", "members:occupation_list", "bi-briefcase"))
    if can_manage_member_lookups(user) or can_manage_members(user):
        config_items.append(_item("Member lists", "members:member_lookup_list", "bi-list-ul"))
    if config_items:
        settings_sections.append(_section("Configuration", config_items, "config"))

    ucc_items = []
    if can_manage_users(user):
        ucc_items.append(_item("Users & Access", "accounts:user_list", "bi-shield-lock"))
    elif can_manage_permissions(user):
        ucc_items.append(_item("Users & Access", "permissions:index", "bi-shield-lock"))
    if can_invite_users(user) and institution_invites_allowed():
        ucc_items.append(_item("Invite User", "accounts:invite_user", "bi-envelope-plus"))
    if can_view_activity_logs(user):
        ucc_items.append(_item("Activity Log", "accounts:activity_log", "bi-journal-text"))
    if can_manage_permissions(user):
        ucc_items.append(_item("Access overview", "permissions:index", "bi-shield-check"))
        ucc_items.append(_item("Role Matrix", "permissions:matrix", "bi-grid-3x3-gap"))
    if can_manage_overrides(user):
        ucc_items.append(_item("Permission Overrides", "permissions:override_list", "bi-sliders"))
    if can_view_permission_audit(user):
        ucc_items.append(_item("Permission Audit", "permissions:audit_log", "bi-journal-check"))
    if ucc_items:
        settings_sections.append(_section("Users & access", ucc_items, "users"))

    if can_manage_institution_branding(user):
        settings_sections.append(_section("Institution", [
            _item("Institution branding", "accounts:institution_branding", "bi-palette"),
        ], "institution"))

    if can_manage_working_day(user):
        settings_sections.append(_section("Treasury & calendar", [
            _item("Working Days & Periods", "transactions:period_list", "bi-calendar-event"),
        ], "calendar"))

    policy_items = []
    if can_manage_remittance_policy(user) and _church_feature(active_church, "remittance", user):
        policy_items.append(_item("Remittance policies", "remittance:index", "bi-percent"))
    if can_manage_payroll_policy(user) and _church_feature(active_church, "payroll", user):
        policy_items.append(_item("Payroll policies", "payroll:policy_index", "bi-sliders"))
    if can_manage_asset_policy(user) and _church_feature(active_church, "assets", user):
        policy_items.append(_item("Asset depreciation policy", "assets:policy_edit", "bi-box-seam"))
    if policy_items:
        settings_sections.append(_section("Module policies", policy_items, "policies"))

    books_items = []
    if can_view_ledger(user) and _church_feature(active_church, "ledger", user):
        books_items.append(_item("Chart of Accounts", "ledger:accounts", "bi-journal-bookmark"))
    if can_manage_gl_categories(user) and _church_feature(active_church, "ledger", user):
        books_items.append(_item("Posting Categories", "ledger:categories", "bi-tags"))
    if books_items:
        settings_sections.append(_section("Books setup", books_items, "books"))

    if settings_sections:
        nav.append(_dropdown("settings", "Administration", "bi-gear-wide-connected", sections=settings_sections))

    return nav


def get_account_navigation(user):
    if not user.is_authenticated:
        return []
    if getattr(user, "is_platform_user", False):
        return [
            _item("Platform Control", "sitecontrol:dashboard", "bi-sliders2"),
            _item("Logout", "dashboard:logout", "bi-box-arrow-right"),
        ]
    items = [
        _item("My Profile", "accounts:profile", "bi-person-circle"),
        _item("Notifications", "dashboard:notifications", "bi-bell"),
    ]
    if can_view_own_payslips(user):
        items.insert(1, _item("My Payslips", "payroll:my_payslips", "bi-receipt"))
    items.append(_item("Logout", "dashboard:logout", "bi-box-arrow-right"))
    return items


REPORT_RELATED_VIEWS = frozenset({
    "reports:index",
    "reports:run",
    "transactions:financial_dashboard",
    "transactions:budget_report",
    "transactions:audit_log",
    "giving:index",
})


def resolve_module_key(namespace, current_view=""):
    if current_view in REPORT_RELATED_VIEWS or namespace == "reports":
        return "reports"
    if current_view in (
        "organization:church_history_list",
        "organization:church_history_create",
        "organization:church_history_detail",
        "organization:church_history_edit",
    ):
        return "communications"
    if current_view in (
        "transactions:period_list",
        "dashboard:cutoff",
        "members:configuration",
        "members:occupation_list",
        "members:occupation_add",
        "members:occupation_edit",
        "members:occupation_delete",
        "members:member_lookup_list",
        "members:member_lookup_add",
        "members:member_lookup_edit",
        "permissions:index",
        "permissions:audit_log",
    ):
        if current_view == "dashboard:cutoff":
            return "home"
        return "settings"
    if current_view == "dashboard:home":
        return "home"
    ns_map = {
        "members": "people",
        "meetings": "people",
        "transactions": "finance",
        "budgets": "finance",
        "ledger": "finance",
        "remittance": "finance",
        "payroll": "finance",
        "assets": "finance",
        "giving": "reports",
        "announcements": "communications",
        "organization": "organization",
        "accounts": "settings",
        "permissions": "settings",
        "portal": None,
        "dashboard": None,
    }
    return ns_map.get(namespace)


MODULE_TABS = {
    # Home dashboard links live in the main nav Home dropdown — no duplicate strip.
    "people": [
        _item("Directory", "members:list", "bi-list-ul"),
        _item("Visitors", "members:visitor_list", "bi-person-heart"),
        _item("Families", "members:family_list", "bi-house-heart"),
        _item("Departments", "members:department_list", "bi-diagram-2"),
        _item("Leadership", "members:leadership_list", "bi-award"),
        _item("Gifts", "members:spiritual_gift_list", "bi-stars"),
        _item("Baptisms", "members:baptism_register", "bi-droplet"),
        _item("Meetings", "meetings:list", "bi-calendar-event"),
        _item("Transfers", "members:transfer_list", "bi-arrow-left-right"),
        _item("Records", "members:record_list", "bi-journal-text"),
    ],
    "finance": [
        _item("Receipts", "transactions:record_receipt", "bi-plus-circle"),
        _item("Pending", "transactions:pending_approvals", "bi-hourglass-split"),
        _item("Transactions", "transactions:transaction_list", "bi-list-check"),
        _item("Journals", "ledger:entry", "bi-journal-plus"),
        _item("Budgets", "budgets:list", "bi-calculator"),
        _item("Remittance", "remittance:index", "bi-percent"),
        _item("Reconcile", "transactions:reconciliation_list", "bi-bank"),
        _item("Ledger", "ledger:index", "bi-journal-text"),
        _item("Payroll", "payroll:index", "bi-currency-exchange"),
        _item("Assets", "assets:index", "bi-box-seam"),
    ],
    "communications": [
        _item("Upcoming", "announcements:upcoming_calendar", "bi-calendar-heart"),
        _item("Announcements", "announcements:announcement_list", "bi-megaphone"),
        _item("New", "announcements:create_announcement", "bi-pencil-square"),
        _item("My Posts", "announcements:my_announcements", "bi-inbox"),
        _item("History", "organization:church_history_list", "bi-journal-richtext"),
    ],
    "reports": [
        _item("Center", "reports:index", "bi-grid"),
        _item("Overview", "transactions:financial_dashboard", "bi-file-earmark-bar-graph"),
        _item("Giving", "giving:index", "bi-cash-stack"),
        _item("Audit", "transactions:audit_log", "bi-shield-check"),
    ],
    "organization": [
        _item("Hierarchy", "organization:hierarchy", "bi-diagram-3"),
        _item("Directory", "organization:directory", "bi-list-ul"),
        _item("Churches", "organization:directory", "bi-building", query="level=church"),
        _item("Onboard", "organization:church_onboard", "bi-building-add"),
    ],
    "settings": [
        _item("Configuration", "members:configuration", "bi-sliders"),
        _item("Occupations", "members:occupation_list", "bi-briefcase"),
        _item("Lists", "members:member_lookup_list", "bi-list-ul"),
        _item("Users", "accounts:user_list", "bi-shield-lock"),
        _item("Invite", "accounts:invite_user", "bi-envelope-plus"),
        _item("Activity", "accounts:activity_log", "bi-journal-text"),
        _item("Matrix", "permissions:matrix", "bi-grid-3x3-gap"),
        _item("Overrides", "permissions:override_list", "bi-sliders2"),
        _item("Perm Audit", "permissions:audit_log", "bi-journal-check"),
        _item("Working Days", "transactions:period_list", "bi-calendar-event"),
    ],
}

# Role-pruned finance tabs (url_name allow-lists). Admins / overseers keep full set.
FINANCE_TABS_TREASURY = frozenset({
    "transactions:record_receipt",
    "transactions:pending_approvals",
    "transactions:transaction_list",
    "ledger:entry",
    "budgets:list",
    "remittance:index",
})
FINANCE_TABS_LEADERSHIP = frozenset({
    "transactions:record_receipt",
    "transactions:pending_approvals",
    "transactions:transaction_list",
    "remittance:index",
    "budgets:list",
})


def _prune_finance_tabs(user, tabs):
    """Keep finance module tabs role-relevant; permission filter already applied."""
    from accounts.models import UserRole

    if user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN,
        UserRole.GENERAL_OVERSEER,
        UserRole.DISTRICT_PASTOR,
    ):
        # Cap dense mega-modules at six daily tabs for everyone.
        priority = [
            "transactions:record_receipt",
            "transactions:pending_approvals",
            "transactions:transaction_list",
            "ledger:entry",
            "budgets:list",
            "remittance:index",
            "transactions:reconciliation_list",
            "ledger:index",
            "payroll:index",
            "assets:index",
        ]
        by_name = {t.get("url_name"): t for t in tabs}
        return [by_name[name] for name in priority if name in by_name][:6]

    if user.role == UserRole.TREASURY:
        allow = FINANCE_TABS_TREASURY
    elif user.role == UserRole.LOCAL_PASTOR:
        allow = FINANCE_TABS_LEADERSHIP
    else:
        allow = FINANCE_TABS_TREASURY | {"payroll:index", "assets:index", "transactions:reconciliation_list"}
        priority = [
            "transactions:record_receipt",
            "transactions:pending_approvals",
            "transactions:transaction_list",
            "ledger:entry",
            "remittance:index",
            "budgets:list",
            "transactions:reconciliation_list",
            "payroll:index",
            "assets:index",
            "ledger:index",
        ]
        by_name = {t.get("url_name"): t for t in tabs if t.get("url_name") in allow}
        return [by_name[name] for name in priority if name in by_name][:6]

    return [t for t in tabs if t.get("url_name") in allow]


MODULE_LABELS = {
    "home": "Home",
    "people": "Members",
    "finance": "Finance",
    "communications": "Church Life",
    "reports": "Reports",
    "organization": "Organization",
    "settings": "Administration",
}


def get_page_eyebrow(module_key, module_tabs, current_view="", report_key=""):
    """Section › Page crumb for module chrome (skip bare Home overview)."""
    if not module_key:
        return None
    if module_key == "home" and current_view in ("", "dashboard:home"):
        return None
    section = MODULE_LABELS.get(module_key, module_key.replace("_", " ").title())
    if module_key == "home" and current_view == "dashboard:cutoff":
        return {"section": "Dashboard", "page": "Monthly Cut-off"}
    page = None
    for tab in module_tabs or []:
        if tab.get("report_key") and report_key and tab["report_key"] == report_key:
            page = tab["label"]
            break
        if not tab.get("report_key") and tab.get("url_name") == current_view:
            page = tab["label"]
            break
    return {"section": section, "page": page}


def annotate_nav_badges(nav, badges):
    if not badges:
        return nav
    for menu in nav:
        count = badges.get(menu.get("id"))
        if count:
            menu["badge"] = count
    return nav


def _tab_allowed(user, url_name, active_church=None):
    """Return True if the module tab URL is allowed for this user."""
    checkers = {
        "dashboard:home": lambda: True,
        "dashboard:cutoff": lambda: can_run_cutoff(user) or can_view_dashboard_finance(user),
        "members:configuration": lambda: (
            can_manage_member_configuration(user)
            or can_manage_occupations(user)
            or can_manage_member_lookups(user)
            or can_manage_members(user)
        ),
        "members:occupation_list": lambda: can_manage_occupations(user) or can_manage_members(user),
        "members:member_lookup_list": lambda: can_manage_member_lookups(user) or can_manage_members(user),
        "members:list": lambda: can_view_members(user) or can_manage_members(user),
        "members:add": lambda: can_add_members(user),
        "members:visitor_list": lambda: can_view_members(user) or can_manage_members(user),
        "members:department_list": lambda: can_manage_departments(user) or can_view_members(user),
        "members:family_list": lambda: can_manage_families(user) or can_view_members(user),
        "members:leadership_list": lambda: can_manage_leadership(user) or can_view_members(user),
        "members:spiritual_gift_list": lambda: can_manage_spiritual_gifts(user) or can_view_members(user),
        "members:baptism_register": lambda: can_manage_baptisms(user) or can_view_members(user),
        "meetings:list": lambda: can_view_meetings(user) or can_manage_meetings(user),
        "members:transfer_list": lambda: can_transfer_members(user),
        "members:record_list": lambda: can_view_member_records(user),
        "ledger:index": lambda: can_view_ledger(user) and _church_feature(active_church, "ledger", user),
        "ledger:accounts": lambda: can_view_ledger(user) and _church_feature(active_church, "ledger", user),
        "ledger:categories": lambda: (
            can_manage_gl_categories(user) or can_view_ledger(user)
        ) and _church_feature(active_church, "ledger", user),
        "ledger:entry": lambda: can_manage_ledger_entries(user) and _church_feature(active_church, "ledger", user),
        "transactions:record_receipt": lambda: can_manage_receipts(user),
        "transactions:record_expense": lambda: can_manage_expenses(user),
        "transactions:record_remittance": lambda: can_manage_expenses(user) or can_manage_receipts(user) or can_manage_finances(user),
        "transactions:transaction_list": lambda: can_view_transactions(user),
        "transactions:pending_approvals": lambda: can_view_pending_approvals(user),
        "budgets:list": lambda: can_view_budgets(user) or can_manage_budgets(user),
        "transactions:reconciliation_list": lambda: (
            can_view_reconciliation(user) or can_manage_reconciliation(user)
        ),
        "remittance:index": lambda: (
            (
                can_view_remittance(user)
                or can_manage_remittance_policy(user)
                or can_manage_settlements(user)
            )
            and _church_feature(active_church, "remittance", user)
        ),
        "remittance:settlements": lambda: (
            can_manage_finances(user)
            or can_manage_settlements(user)
            or can_manage_remittance_policy(user)
        ),
        "payroll:index": lambda: (
            (can_view_payroll(user) or can_manage_payroll(user))
            and _church_feature(active_church, "payroll", user)
        ),
        "assets:index": lambda: (
            (can_view_assets(user) or can_manage_assets(user) or can_manage_asset_policy(user))
            and _church_feature(active_church, "assets", user)
        ),
        "announcements:upcoming_calendar": lambda: can_view_announcements(user),
        "announcements:announcement_list": lambda: (
            can_view_announcements(user) or can_archive_announcements(user)
        ),
        "announcements:create_announcement": lambda: can_create_announcements(user),
        "announcements:my_announcements": lambda: (
            can_view_announcements(user) or can_create_announcements(user)
        ),
        "announcements:pending_approvals": lambda: can_approve_announcements(user),
        "organization:church_history_list": lambda: (
            can_view_church_history(user) or can_manage_church_history(user)
        ),
        "organization:church_history_create": lambda: can_manage_church_history(user),
        "reports:index": lambda: _can_access_reports(user),
        "transactions:financial_dashboard": lambda: can_view_finance_reports(user),
        "giving:index": lambda: can_view_giving(user) or can_manage_giving(user),
        "transactions:audit_log": lambda: can_view_audit_log(user),
        "organization:hierarchy": lambda: can_view_all_churches(user),
        "organization:directory": lambda: can_view_all_churches(user),
        "organization:church_onboard": lambda: (
            can_onboard_churches(user) and institution_onboarding_allowed()
        ),
        "accounts:user_list": lambda: can_manage_users(user),
        "accounts:invite_user": lambda: can_invite_users(user) and institution_invites_allowed(),
        "accounts:activity_log": lambda: can_view_activity_logs(user),
        "transactions:period_list": lambda: can_manage_working_day(user),
        "permissions:index": lambda: can_manage_permissions(user),
        "permissions:matrix": lambda: can_manage_permissions(user),
        "permissions:override_list": lambda: can_manage_permissions(user),
        "permissions:audit_log": lambda: can_manage_permissions(user),
    }
    check = checkers.get(url_name)
    if check is None:
        return False
    return check()


def get_module_tabs(user, namespace, current_view="", active_church=None):
    if not user.is_authenticated:
        return None, None

    module_key = resolve_module_key(namespace, current_view)
    if not module_key:
        return None, None

    tabs = [
        t for t in MODULE_TABS.get(module_key, [])
        if _tab_allowed(user, t.get("url_name", ""), active_church)
    ]

    if module_key == "people" and not _can_access_people(user):
        return None, None

    if module_key == "finance" and not _can_access_finance(user):
        return None, None
    if module_key == "finance" and not _church_feature(active_church, "budgets", user):
        tabs = [t for t in tabs if t.get("url_name") != "budgets:list"]
    if module_key == "finance":
        tabs = _prune_finance_tabs(user, tabs)

    if module_key == "reports" and not _can_access_reports(user):
        return None, None

    if module_key == "communications":
        if not _can_access_communications(user):
            return None, None
        if can_approve_announcements(user):
            pending = _item("Pending", "announcements:pending_approvals", "bi-hourglass-split")
            if _tab_allowed(user, pending["url_name"], active_church):
                tabs.append(pending)

    if module_key == "organization" and not can_view_all_churches(user):
        return None, None

    if module_key == "settings" and not (
        can_manage_users(user)
        or can_invite_users(user)
        or can_view_activity_logs(user)
        or can_manage_permissions(user)
        or can_manage_overrides(user)
        or can_view_permission_audit(user)
        or can_manage_working_day(user)
        or can_manage_member_configuration(user)
        or can_manage_occupations(user)
        or can_manage_member_lookups(user)
        or can_manage_members(user)
    ):
        return None, None

    # Report catalog lives in Report Center — do not inflate sticky tabs.

    if not tabs and module_key != "reports":
        return None, None

    return module_key, tabs


def nav_item_is_active(item, current_view, report_key=""):
    if item.get("report_key"):
        return current_view == "reports:run" and item["report_key"] == report_key
    return current_view == item.get("url_name")
