"""

Central navigation registry for ChurchHub.



Top bar: ChurchHub brand + utilities.

Menu bar: Home, People, Finance, Reports, Communications, Organization, Settings.

"""



from permissions.checks import (

    can_approve_announcements,

    can_approve_minutes,

    can_approve_transactions,

    can_create_announcements,

    can_manage_asset_policy,

    can_manage_assets,

    can_manage_finances,

    can_manage_meetings,

    can_manage_members,

    can_manage_organization,

    can_manage_payroll,

    can_manage_permissions,

    can_manage_remittance_policy,

    can_manage_users,

    can_view_all_churches,

    can_view_meetings,

    can_view_members,

    can_view_own_payslips,

    can_view_reports,

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





def _item(label, url_name="", icon="", report_key=""):

    return {

        "label": label,

        "url_name": url_name,

        "icon": icon,

        "report_key": report_key,

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

        sections.append(_section("Membership Analytics", membership_reports, "people"))



    if can_manage_finances(user):

        financial_tools = [

            _item("Financial Statement", "transactions:financial_dashboard", "bi-file-earmark-bar-graph"),

            _item("Budget vs Actual", "budgets:list", "bi-pie-chart"),

            _item("Finance Audit Log", "transactions:audit_log", "bi-shield-check"),

        ]

        if finance_reports:

            sections.append(_section("Financial Analytics", finance_reports, "analytics"))

        sections.append(_section("Financial Statements", financial_tools, "treasury"))

        sections.append(_section("Giving", [

            _item("Member Giving", "giving:index", "bi-cash-stack"),

            _item("Member Welfare Statement", "reports:welfare_statement", "bi-heart-pulse"),

        ], "giving"))



    return sections





def get_main_navigation(user, active_church=None):

    if not user.is_authenticated:

        return []



    nav = []

    home_items = [_item("Overview", "dashboard:home", "bi-speedometer2")]

    if can_manage_finances(user):

        home_items.append(_item("Monthly Cut-off", "dashboard:cutoff", "bi-calendar-check"))

    if len(home_items) == 1:

        nav.append(_link("home", "Home", "bi-house-door", "dashboard:home"))

    else:

        nav.append(_dropdown(

            "home", "Home", "bi-house-door",

            sections=[_section("Dashboard", home_items, "primary")],

        ))



    if can_view_members(user) or can_manage_members(user):

        nav.append(_dropdown(

            "people", "People", "bi-people",

            sections=[

                _section("Members", [

                    _item("Directory", "members:list", "bi-list-ul"),

                ] + ([
                    _item("Add Member", "members:add", "bi-person-plus"),
                    _item("Transfers", "members:transfer_list", "bi-arrow-left-right"),
                ] if can_manage_members(user) else []) + [

                    _item("Baptisms", "members:baptism_register", "bi-droplet"),

                ], "people"),

                _section("Groups & Care", [

                    _item("Departments", "members:department_list", "bi-diagram-2"),

                    _item("Families", "members:family_list", "bi-house-heart"),

                    _item("Leadership", "members:leadership_list", "bi-award"),

                    _item("Spiritual Gifts", "members:spiritual_gift_list", "bi-stars"),

                ], "groups"),

            ] + ([
                _section("Meetings", [

                    _item("All Meetings", "meetings:list", "bi-calendar-event"),

                ] + ([
                    _item("Schedule", "meetings:create", "bi-plus-circle"),
                    _item("Attendance", "meetings:attendance_list", "bi-calendar-check"),
                ] if can_manage_meetings(user) else []) + ([
                    _item("Pending Minutes", "meetings:pending_minutes", "bi-hourglass-split"),
                ] if can_approve_minutes(user) else []), "meetings"),
            ] if can_view_meetings(user) or can_manage_meetings(user) else []) + [

                _section("Records", [

                    _item("Member Records", "members:record_list", "bi-journal-text"),

                ], "records"),

            ],

        ))



    if can_manage_finances(user):

        finance_sections = [

            _section("Accounting", [

                _item("General Ledger", "ledger:index", "bi-journal-text"),

                _item("New Entry", "ledger:entry", "bi-journal-plus"),

                _item("GL Entries", "ledger:entries", "bi-journal-check"),

                _item("By Category", "ledger:category_report", "bi-bar-chart"),

                _item("Categories", "ledger:categories", "bi-tags"),

            ], "accounting") if _church_feature(active_church, "ledger", user) else None,

            _section("Treasury", [

                _item("Pending Approvals", "transactions:pending_approvals", "bi-hourglass-split"),

                _item("Transactions", "transactions:transaction_list", "bi-list-check"),

                _item("Record Receipt", "transactions:record_receipt", "bi-plus-circle"),

                _item("Record Expense", "transactions:record_expense", "bi-dash-circle"),

            ], "treasury"),

            _section("Planning", [

                _item("Budgets", "budgets:list", "bi-calculator"),

                _item("Reconciliation", "transactions:reconciliation_list", "bi-bank"),

            ], "planning") if _church_feature(active_church, "budgets", user) else _section("Planning", [

                _item("Reconciliation", "transactions:reconciliation_list", "bi-bank"),

            ], "planning"),

        ]

        if _church_feature(active_church, "remittance", user):

            finance_sections.append(_section("Remittance", [

                _item("Policies", "remittance:index", "bi-percent"),

                _item("Settlements", "remittance:settlements", "bi-arrow-up-right-circle"),

                _item("Welfare", "remittance:welfare", "bi-heart-pulse"),

            ], "remittance"))

        if can_manage_payroll(user) and _church_feature(active_church, "payroll", user):

            finance_sections.append(_section("Payroll", [

                _item("Dashboard", "payroll:index", "bi-currency-exchange"),

                _item("Employees", "payroll:employee_list", "bi-person-badge"),

                _item("Pay Runs", "payroll:run_list", "bi-calendar2-check"),

                _item("Roll-up", "payroll:hierarchy", "bi-bar-chart-steps"),

                _item("Policies", "payroll:policy_index", "bi-sliders"),

            ], "payroll"))

        if (can_manage_assets(user) or can_manage_asset_policy(user)) and _church_feature(active_church, "assets", user):

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

            finance_sections.append(_section("Fixed Assets", asset_items, "assets"))

        nav.append(_dropdown("finance", "Finance", "bi-wallet2", sections=[s for s in finance_sections if s]))



    if can_view_reports(user) or can_manage_finances(user) or can_view_members(user) or can_manage_members(user):

        nav.append(_dropdown("reports", "Reports", "bi-bar-chart-line", sections=_reports_sections(user, active_church)))



    comm_sections = [

        _section("Calendar", [

            _item("Upcoming Events & Birthdays", "announcements:upcoming_calendar", "bi-calendar-heart"),

        ], "calendar"),

        _section("Publishing", [

            _item("All Announcements", "announcements:announcement_list", "bi-megaphone"),

        ] + ([
            _item("Create New", "announcements:create_announcement", "bi-pencil-square"),
        ] if can_create_announcements(user) else []), "communications"),

        _section("My Work", [

            _item("My Submissions", "announcements:my_announcements", "bi-inbox"),

        ], "records"),

    ]

    if can_approve_announcements(user):

        comm_sections[0]["items"].append(

            _item("Pending Approval", "announcements:pending_approvals", "bi-hourglass-split")

        )

    nav.append(_dropdown("communications", "Communications", "bi-broadcast", sections=comm_sections))



    if can_view_all_churches(user):

        org_sections = [

            _section("Hierarchy", [

                _item("Organization Tree", "organization:hierarchy", "bi-diagram-3"),

            ], "hierarchy"),

        ]

        if institution_onboarding_allowed():

            org_sections.append(_section("Onboarding", [

                _item("Onboard Church", "organization:church_onboard", "bi-building-add"),

                _item("Add Conference", "organization:conference_create", "bi-globe"),

            ], "onboarding"))

        if can_manage_organization(user):

            org_sections.append(_section("Structure", [

                _item("General Conference", "organization:general_conference_create", "bi-building"),

                _item("Union", "organization:union_create", "bi-globe2"),

                _item("Zone", "organization:zone_create", "bi-layers"),

                _item("District", "organization:district_create", "bi-pin-map"),

            ], "structure"))

        nav.append(_dropdown("organization", "Organization", "bi-diagram-3", sections=org_sections))



    settings_sections = []

    if can_manage_users(user):

        user_items = [_item("Users", "accounts:user_list", "bi-people-fill")]

        if institution_invites_allowed():

            user_items.append(_item("Invite User", "accounts:invite_user", "bi-envelope-plus"))

        user_items.append(_item("Activity Log", "accounts:activity_log", "bi-journal-text"))

        settings_sections.append(_section("Users & Activity", user_items, "users"))



    if can_manage_permissions(user):

        settings_sections.append(_section("Security", [

            _item("Permissions", "permissions:index", "bi-shield-lock"),

            _item("Role Matrix", "permissions:matrix", "bi-grid-3x3-gap"),

            _item("Overrides", "permissions:override_list", "bi-sliders"),

            _item("Permission Audit", "permissions:audit_log", "bi-journal-check"),

        ], "security"))



    if can_approve_transactions(user):

        settings_sections.append(_section("Church Calendar", [

            _item("Working Day & Periods", "transactions:period_list", "bi-calendar-event"),

        ], "calendar"))



    if settings_sections:

        nav.append(_dropdown("settings", "Settings", "bi-gear-wide-connected", sections=settings_sections))



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

    if current_view in ("transactions:period_list", "dashboard:cutoff"):

        return "settings" if current_view == "transactions:period_list" else "home"

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

        "dashboard": None,

    }

    return ns_map.get(namespace)





MODULE_TABS = {

    "home": [

        _item("Overview", "dashboard:home", "bi-speedometer2"),

        _item("Cut-off", "dashboard:cutoff", "bi-calendar-check"),

    ],

    "people": [

        _item("Directory", "members:list", "bi-list-ul"),

        _item("Add", "members:add", "bi-person-plus"),

        _item("Departments", "members:department_list", "bi-diagram-2"),

        _item("Families", "members:family_list", "bi-house-heart"),

        _item("Meetings", "meetings:list", "bi-calendar-event"),

        _item("Transfers", "members:transfer_list", "bi-arrow-left-right"),

        _item("Records", "members:record_list", "bi-journal-text"),

    ],

    "finance": [

        _item("Ledger", "ledger:index", "bi-journal-text"),

        _item("Entry", "ledger:entry", "bi-journal-plus"),

        _item("Transactions", "transactions:transaction_list", "bi-list-check"),

        _item("Pending", "transactions:pending_approvals", "bi-hourglass-split"),

        _item("Budgets", "budgets:list", "bi-calculator"),

        _item("Reconcile", "transactions:reconciliation_list", "bi-bank"),

        _item("Remittance", "remittance:index", "bi-percent"),

        _item("Payroll", "payroll:index", "bi-currency-exchange"),

        _item("Assets", "assets:index", "bi-box-seam"),

    ],

    "communications": [

        _item("Upcoming", "announcements:upcoming_calendar", "bi-calendar-heart"),

        _item("Published", "announcements:announcement_list", "bi-megaphone"),

        _item("Create", "announcements:create_announcement", "bi-pencil-square"),

        _item("My Posts", "announcements:my_announcements", "bi-inbox"),

    ],

    "reports": [

        _item("Center", "reports:index", "bi-grid"),

        _item("Statement", "transactions:financial_dashboard", "bi-file-earmark-bar-graph"),

        _item("Budget", "budgets:list", "bi-pie-chart"),

        _item("Giving", "giving:index", "bi-cash-stack"),

        _item("Audit", "transactions:audit_log", "bi-shield-check"),

    ],

    "organization": [

        _item("Hierarchy", "organization:hierarchy", "bi-diagram-3"),

        _item("Onboard", "organization:church_onboard", "bi-building-add"),

    ],

    "settings": [

        _item("Users", "accounts:user_list", "bi-people-fill"),

        _item("Invite", "accounts:invite_user", "bi-envelope-plus"),

        _item("Activity", "accounts:activity_log", "bi-journal-text"),

        _item("Calendar", "transactions:period_list", "bi-calendar-event"),

        _item("Permissions", "permissions:index", "bi-shield-lock"),

        _item("Matrix", "permissions:matrix", "bi-grid-3x3-gap"),

    ],

}





def get_module_tabs(user, namespace, current_view="", active_church=None):

    if not user.is_authenticated:

        return None, None



    module_key = resolve_module_key(namespace, current_view)

    if not module_key:

        return None, None



    tabs = list(MODULE_TABS.get(module_key, []))

    if module_key == "home" and not can_manage_finances(user):

        tabs = [t for t in tabs if t["url_name"] != "dashboard:cutoff"]

    if module_key == "people":
        if not (can_view_members(user) or can_manage_members(user)):
            return None, None
        if not can_manage_members(user):
            tabs = [t for t in tabs if t["url_name"] != "members:add"]
        if not (can_view_meetings(user) or can_manage_meetings(user)):
            tabs = [t for t in tabs if t["url_name"] != "meetings:list"]

    if module_key == "finance" and not can_manage_finances(user):

        return None, None

    if module_key == "finance" and not _church_feature(active_church, "budgets", user):
        tabs = [t for t in tabs if t["url_name"] != "budgets:list"]

    if module_key == "finance" and not _church_feature(active_church, "ledger", user):
        tabs = [t for t in tabs if not str(t.get("url_name", "")).startswith("ledger:")]

    if module_key == "reports" and not (can_view_reports(user) or can_manage_finances(user) or can_view_members(user)):

        return None, None

    if module_key == "settings" and not (

        can_manage_users(user) or can_manage_permissions(user) or can_approve_transactions(user)

    ):

        return None, None

    if module_key == "organization" and not can_view_all_churches(user):

        return None, None



    if module_key == "communications" and can_approve_announcements(user):

        tabs.append(_item("Pending", "announcements:pending_approvals", "bi-hourglass-split"))

    if module_key == "communications" and not can_create_announcements(user):
        tabs = [t for t in tabs if t["url_name"] != "announcements:create_announcement"]



    if module_key == "reports":

        from reports.services import user_may_access_report

        for key, meta in REPORT_CATALOG.items():

            if not user_may_access_report(user, key, active_church=active_church):

                continue

            tabs.append(_item(meta["label"], icon=meta["icon"], report_key=key))



    return module_key, tabs





def nav_item_is_active(item, current_view, report_key=""):

    if item.get("report_key"):

        return current_view == "reports:run" and item["report_key"] == report_key

    return current_view == item.get("url_name")


