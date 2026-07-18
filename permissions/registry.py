"""Canonical permission catalog for the role-permission matrix.

Expand freely — seed via `python manage.py seed_permissions` (or --reset).
Broad legacy codes keep working via `implies` so existing role grants remain valid.
"""

_ROLE_TREE = {
    "SUPER_ADMIN", "GENERAL_OVERSEER", "UNION_ADMIN", "CONFERENCE_ADMIN",
    "ZONE_DIRECTOR", "DISTRICT_PASTOR",
}
_ROLE_ALL_STAFF = _ROLE_TREE | {
    "LOCAL_PASTOR", "SECRETARY", "TREASURY",
}
_ROLE_LEADERSHIP = _ROLE_TREE | {"LOCAL_PASTOR"}
_ROLE_HIERARCHY = set(_ROLE_TREE)
_ROLE_TREASURY_OPS = {"SUPER_ADMIN", "GENERAL_OVERSEER", "CONFERENCE_ADMIN", "TREASURY"}
_ROLE_POLICY = {"SUPER_ADMIN", "GENERAL_OVERSEER", "UNION_ADMIN", "CONFERENCE_ADMIN"}
_ROLE_READ = _ROLE_ALL_STAFF | {"BOARD_MEMBER"}


PERMISSION_REGISTRY = {
    # ── Members (12) ──────────────────────────────────────────────
    "view_members": {
        "name": "View Members",
        "category": "Members",
        "description": "Read member directory, profiles, and pastoral records.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER", "MEMBER"},
    },
    "manage_members": {
        "name": "Manage Members",
        "category": "Members",
        "description": "Full member write access (implies add/edit/transfer/groups).",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": [
            "view_members", "add_members", "edit_members", "export_members",
            "transfer_members", "process_transfers", "manage_baptisms",
            "manage_departments", "manage_families", "manage_leadership",
            "manage_spiritual_gifts", "view_member_records", "manage_member_records",
        ],
    },
    "add_members": {
        "name": "Add Members",
        "category": "Members",
        "description": "Create new member records.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "edit_members": {
        "name": "Edit Members",
        "category": "Members",
        "description": "Update existing member profiles and status.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "export_members": {
        "name": "Export Members",
        "category": "Members",
        "description": "Download member lists and pastoral data exports.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "transfer_members": {
        "name": "Request Member Transfers",
        "category": "Members",
        "description": "Initiate member transfer requests.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "process_transfers": {
        "name": "Process Member Transfers",
        "category": "Members",
        "description": "Approve, complete, or reject member transfers.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_members"],
    },
    "manage_baptisms": {
        "name": "Manage Baptisms",
        "category": "Members",
        "description": "Record and maintain baptism register entries.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "manage_departments": {
        "name": "Manage Departments",
        "category": "Members",
        "description": "Create and edit church departments.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "manage_families": {
        "name": "Manage Families",
        "category": "Members",
        "description": "Create and edit family households.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "manage_leadership": {
        "name": "Manage Leadership Roles",
        "category": "Members",
        "description": "Assign church leadership positions.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "manage_spiritual_gifts": {
        "name": "Manage Spiritual Gifts",
        "category": "Members",
        "description": "Maintain spiritual gift catalogs and member gifts.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "view_member_records": {
        "name": "View Member Records",
        "category": "Members",
        "description": "Read pastoral and disciplinary member records.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY", "BOARD_MEMBER"},
        "implies": ["view_members"],
    },
    "manage_member_records": {
        "name": "Manage Member Records",
        "category": "Members",
        "description": "Create and edit pastoral member records.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_member_records"],
    },

    # ── Meetings (6) ──────────────────────────────────────────────
    "view_meetings": {
        "name": "View Meetings",
        "category": "Meetings",
        "description": "Search and read meeting minutes, decisions, and attachments.",
        "default_roles": _ROLE_READ,
    },
    "manage_meetings": {
        "name": "Manage Meetings",
        "category": "Meetings",
        "description": "Schedule meetings, draft minutes, record attendance and decisions.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_meetings", "manage_attendance", "submit_minutes"],
    },
    "manage_attendance": {
        "name": "Manage Meeting Attendance",
        "category": "Meetings",
        "description": "Record attendance for scheduled meetings.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_meetings"],
    },
    "submit_minutes": {
        "name": "Submit Meeting Minutes",
        "category": "Meetings",
        "description": "Submit drafted minutes for approval.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_meetings"],
    },
    "approve_minutes": {
        "name": "Approve Meeting Minutes",
        "category": "Meetings",
        "description": "Review and approve submitted meeting minutes.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_meetings"],
    },
    "export_minutes": {
        "name": "Export Meeting Minutes",
        "category": "Meetings",
        "description": "Download or print approved minutes packages.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_meetings"],
    },

    # ── Finance / Transactions (14) ───────────────────────────────
    "view_transactions": {
        "name": "View Transactions",
        "category": "Finance",
        "description": "Browse transaction lists and receipts.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_finances": {
        "name": "Manage Finances",
        "category": "Finance",
        "description": "Legacy finance ops gate (implies receipts, expenses, ledgers).",
        "default_roles": _ROLE_ALL_STAFF,
        "implies": [
            "view_transactions", "manage_receipts", "manage_expenses",
            "view_ledger", "manage_ledger_entries", "manage_gl_categories",
            "manage_chart_of_accounts", "view_budgets", "manage_budgets",
            "view_giving", "manage_giving", "view_remittance", "manage_settlements",
            "view_welfare", "manage_welfare_cases", "view_audit_log",
            "view_pending_approvals", "view_reconciliation", "view_dashboard_finance",
            "export_transactions", "export_budgets", "export_giving",
        ],
    },
    "manage_receipts": {
        "name": "Record Receipts",
        "category": "Finance",
        "description": "Record tithes, offerings, and other receipts.",
        "default_roles": _ROLE_ALL_STAFF,
        "implies": ["view_transactions"],
    },
    "manage_expenses": {
        "name": "Record Expenses",
        "category": "Finance",
        "description": "Record church expenses.",
        "default_roles": _ROLE_ALL_STAFF,
        "implies": ["view_transactions"],
    },
    "view_pending_approvals": {
        "name": "View Pending Approvals",
        "category": "Finance",
        "description": "See the pending transaction approval queue.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_transactions"],
    },
    "approve_transactions": {
        "name": "Approve Transactions",
        "category": "Finance",
        "description": "Approve or reject pending financial transactions.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": [
            "view_transactions", "view_pending_approvals", "void_transactions",
            "reject_transactions", "manage_working_day", "lock_periods",
            "approve_welfare", "disburse_welfare",
        ],
    },
    "reject_transactions": {
        "name": "Reject Transactions",
        "category": "Finance",
        "description": "Reject pending financial transactions.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_pending_approvals"],
    },
    "void_transactions": {
        "name": "Void Transactions",
        "category": "Finance",
        "description": "Void approved financial transactions.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_transactions"],
    },
    "view_reconciliation": {
        "name": "View Bank Reconciliation",
        "category": "Finance",
        "description": "View bank reconciliation worksheets.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_reconciliation": {
        "name": "Manage Bank Reconciliation",
        "category": "Finance",
        "description": "Create and update bank reconciliations.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR", "DISTRICT_PASTOR"},
        "implies": ["view_reconciliation"],
    },
    "finalize_reconciliation": {
        "name": "Finalize Bank Reconciliation",
        "category": "Finance",
        "description": "Finalize and lock a completed reconciliation.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["manage_reconciliation"],
    },
    "view_audit_log": {
        "name": "View Finance Audit Log",
        "category": "Finance",
        "description": "Review financial audit trail events.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY", "BOARD_MEMBER"},
    },
    "manage_working_day": {
        "name": "Manage Working Day",
        "category": "Finance",
        "description": "Open and close the church business day.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "lock_periods": {
        "name": "Lock Financial Periods",
        "category": "Finance",
        "description": "Lock monthly financial periods.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "unlock_periods": {
        "name": "Unlock Financial Periods",
        "category": "Finance",
        "description": "Unlock previously locked periods.",
        "default_roles": _ROLE_POLICY | {"DISTRICT_PASTOR"},
    },
    "run_cutoff": {
        "name": "Run Monthly Cut-off",
        "category": "Finance",
        "description": "Generate monthly remittance cut-off summaries.",
        "default_roles": _ROLE_ALL_STAFF,
        "implies": ["view_transactions"],
    },
    "export_transactions": {
        "name": "Export Transactions",
        "category": "Finance",
        "description": "Export transaction registers to CSV/Excel.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_transactions"],
    },

    # ── Ledger (6) ────────────────────────────────────────────────
    "view_ledger": {
        "name": "View Ledger",
        "category": "Ledger",
        "description": "Browse general ledger entries and category reports.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_ledger_entries": {
        "name": "Post Ledger Entries",
        "category": "Ledger",
        "description": "Create and confirm category-driven GL journal entries.",
        "default_roles": _ROLE_ALL_STAFF,
        "implies": ["view_ledger"],
    },
    "manage_gl_categories": {
        "name": "Manage GL Categories",
        "category": "Ledger",
        "description": "Create and edit ledger posting category templates.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR"},
        "implies": ["view_ledger"],
    },
    "manage_chart_of_accounts": {
        "name": "Manage Chart of Accounts",
        "category": "Ledger",
        "description": "Create and edit GL accounts for the church chart of accounts.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR"},
        "implies": ["view_ledger"],
    },
    "export_ledger": {
        "name": "Export Ledger",
        "category": "Ledger",
        "description": "Export GL registers and category summaries.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_ledger"],
    },
    "view_trial_balance": {
        "name": "View Trial Balance",
        "category": "Ledger",
        "description": "Access trial balance and account balances.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_ledger"],
    },

    # ── Remittance (8) ────────────────────────────────────────────
    "view_remittance": {
        "name": "View Remittance",
        "category": "Remittance",
        "description": "View remittance policies and settlement summaries.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_remittance_policy": {
        "name": "Manage Remittance Policies",
        "category": "Remittance",
        "description": "Configure retain and remit percentages per hierarchy level.",
        "default_roles": _ROLE_POLICY,
        "implies": ["view_remittance"],
    },
    "manage_settlements": {
        "name": "Manage Settlements",
        "category": "Remittance",
        "description": "Create and edit remittance settlement batches.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR", "DISTRICT_PASTOR"},
        "implies": ["view_remittance"],
    },
    "post_settlements": {
        "name": "Post Settlements",
        "category": "Remittance",
        "description": "Post settlement batches to the ledger.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR"},
        "implies": ["manage_settlements"],
    },
    "view_welfare": {
        "name": "View Welfare Cases",
        "category": "Remittance",
        "description": "Browse welfare case records.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_welfare_cases": {
        "name": "Manage Welfare Cases",
        "category": "Remittance",
        "description": "Create and update welfare assistance cases.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY", "TREASURY"},
        "implies": ["view_welfare"],
    },
    "approve_welfare": {
        "name": "Approve Welfare Cases",
        "category": "Remittance",
        "description": "Approve welfare requests for disbursement.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_welfare"],
    },
    "disburse_welfare": {
        "name": "Disburse Welfare",
        "category": "Remittance",
        "description": "Record welfare disbursement payments.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR"},
        "implies": ["view_welfare"],
    },

    # ── Payroll (8) ───────────────────────────────────────────────
    "view_payroll": {
        "name": "View Payroll",
        "category": "Payroll",
        "description": "View payroll dashboard and run summaries.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR", "DISTRICT_PASTOR", "BOARD_MEMBER"},
    },
    "manage_payroll": {
        "name": "Manage Payroll",
        "category": "Payroll",
        "description": "Maintain employees, compensation, and prepare payroll runs.",
        "default_roles": _ROLE_TREASURY_OPS,
        "implies": ["view_payroll", "export_payroll"],
    },
    "approve_payroll": {
        "name": "Approve Payroll",
        "category": "Payroll",
        "description": "Approve calculated payroll runs before posting.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_payroll"],
    },
    "post_payroll": {
        "name": "Post Payroll",
        "category": "Payroll",
        "description": "Post approved payroll to the general ledger.",
        "default_roles": _ROLE_TREASURY_OPS,
        "implies": ["view_payroll"],
    },
    "pay_payroll": {
        "name": "Pay Payroll",
        "category": "Payroll",
        "description": "Record bank payment for posted payroll runs.",
        "default_roles": _ROLE_TREASURY_OPS,
        "implies": ["view_payroll"],
    },
    "view_payslips": {
        "name": "View Payslips",
        "category": "Payroll",
        "description": "View own payslips via employee self-service.",
        "default_roles": _ROLE_ALL_STAFF | {"MEMBER"},
    },
    "manage_payroll_policy": {
        "name": "Manage Payroll Policies",
        "category": "Payroll",
        "description": "Configure PAYE bands and statutory contribution rules.",
        "default_roles": _ROLE_POLICY,
        "implies": ["view_payroll"],
    },
    "export_payroll": {
        "name": "Export Payroll",
        "category": "Payroll",
        "description": "Export payroll registers and statutory filings.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR"},
        "implies": ["view_payroll"],
    },

    # ── Assets (6) ────────────────────────────────────────────────
    "view_assets": {
        "name": "View Fixed Assets",
        "category": "Assets",
        "description": "Browse the fixed asset register.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_assets": {
        "name": "Manage Fixed Assets",
        "category": "Assets",
        "description": "Create and maintain fixed asset records and maintenance logs.",
        "default_roles": _ROLE_TREASURY_OPS | {"SECRETARY"},
        "implies": ["view_assets", "export_assets"],
    },
    "approve_assets": {
        "name": "Approve Fixed Assets",
        "category": "Assets",
        "description": "Approve asset acquisitions before they become active.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_assets"],
    },
    "dispose_assets": {
        "name": "Dispose Fixed Assets",
        "category": "Assets",
        "description": "Record asset disposal and write-offs.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_assets"],
    },
    "manage_asset_policy": {
        "name": "Manage Asset Policies",
        "category": "Assets",
        "description": "Configure depreciation methods, categories, and ledger posting.",
        "default_roles": _ROLE_TREASURY_OPS,
        "implies": ["view_assets"],
    },
    "export_assets": {
        "name": "Export Assets",
        "category": "Assets",
        "description": "Export fixed asset registers and depreciation reports.",
        "default_roles": _ROLE_TREASURY_OPS | {"SECRETARY", "LOCAL_PASTOR"},
        "implies": ["view_assets"],
    },

    # ── Budgets (5) ───────────────────────────────────────────────
    "view_budgets": {
        "name": "View Budgets",
        "category": "Budgets",
        "description": "View church budget plans and variance.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_budgets": {
        "name": "Manage Budgets",
        "category": "Budgets",
        "description": "Create and edit budget lines.",
        "default_roles": _ROLE_TREASURY_OPS | {"LOCAL_PASTOR", "DISTRICT_PASTOR"},
        "implies": ["view_budgets"],
    },
    "approve_budgets": {
        "name": "Approve Budgets",
        "category": "Budgets",
        "description": "Approve annual or departmental budgets.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_budgets"],
    },
    "lock_budgets": {
        "name": "Lock Budgets",
        "category": "Budgets",
        "description": "Lock approved budgets against further edits.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_budgets"],
    },
    "export_budgets": {
        "name": "Export Budgets",
        "category": "Budgets",
        "description": "Export budget vs actual reports.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_budgets"],
    },

    # ── Giving (4) ────────────────────────────────────────────────
    "view_giving": {
        "name": "View Giving",
        "category": "Giving",
        "description": "View member giving statements and summaries.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_giving": {
        "name": "Manage Giving Statements",
        "category": "Giving",
        "description": "Generate and manage member giving statements.",
        "default_roles": _ROLE_TREASURY_OPS | {"SECRETARY", "LOCAL_PASTOR"},
        "implies": ["view_giving"],
    },
    "view_own_giving": {
        "name": "View Own Giving",
        "category": "Giving",
        "description": "Members may view their personal giving history.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER", "MEMBER"},
    },
    "export_giving": {
        "name": "Export Giving",
        "category": "Giving",
        "description": "Export giving statements and donor summaries.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_giving"],
    },

    # ── Announcements (5) ─────────────────────────────────────────
    "view_announcements": {
        "name": "View Announcements",
        "category": "Announcements",
        "description": "Browse published announcements and calendar.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER", "MEMBER"},
    },
    "create_announcements": {
        "name": "Create Announcements",
        "category": "Announcements",
        "description": "Draft and submit church announcements for approval.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY", "MEMBER"},
        "implies": ["view_announcements"],
    },
    "approve_announcements": {
        "name": "Approve Announcements",
        "category": "Announcements",
        "description": "Approve or reject church announcements before publishing.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["view_announcements"],
    },
    "archive_announcements": {
        "name": "Archive Announcements",
        "category": "Announcements",
        "description": "Archive or unpublish announcements.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_announcements"],
    },
    "export_announcements": {
        "name": "Export Announcements",
        "category": "Announcements",
        "description": "Export announcement archives.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_announcements"],
    },

    # ── Reports (8) ───────────────────────────────────────────────
    "view_reports": {
        "name": "View Reports",
        "category": "Reports",
        "description": "Access the report center catalog.",
        "default_roles": _ROLE_READ,
    },
    "view_member_reports": {
        "name": "View Member Reports",
        "category": "Reports",
        "description": "Run membership analytics reports.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY", "BOARD_MEMBER"},
        "implies": ["view_reports"],
    },
    "view_finance_reports": {
        "name": "View Finance Reports",
        "category": "Reports",
        "description": "Run financial analytics reports.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_reports"],
    },
    "view_hierarchy_reports": {
        "name": "View Hierarchy Reports",
        "category": "Reports",
        "description": "Run district/zone/conference roll-up reports.",
        "default_roles": _ROLE_HIERARCHY | {"BOARD_MEMBER"},
        "implies": ["view_reports"],
    },
    "run_advanced_reports": {
        "name": "Run Advanced Reports",
        "category": "Reports",
        "description": "Access advanced / feature-gated analytics.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
        "implies": ["view_reports"],
    },
    "export_reports_csv": {
        "name": "Export Reports (CSV)",
        "category": "Reports",
        "description": "Download report results as CSV.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_reports"],
    },
    "export_reports_excel": {
        "name": "Export Reports (Excel)",
        "category": "Reports",
        "description": "Download report results as Excel.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_reports"],
    },
    "export_reports_pdf": {
        "name": "Export Reports (PDF)",
        "category": "Reports",
        "description": "Download report results as PDF.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
        "implies": ["view_reports"],
    },

    # ── Organization (8) ──────────────────────────────────────────
    "view_all_churches": {
        "name": "View All Churches",
        "category": "Organization",
        "description": "Switch church context and view hierarchy-wide data.",
        "default_roles": _ROLE_HIERARCHY,
    },
    "switch_church_context": {
        "name": "Switch Church Context",
        "category": "Organization",
        "description": "Change the active church in the UI.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": ["view_all_churches"],
    },
    "manage_organization": {
        "name": "Manage Organization",
        "category": "Organization",
        "description": "Create and edit conference, zone, district, and church records.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": [
            "view_all_churches", "manage_conferences", "manage_zones",
            "manage_districts", "manage_churches", "onboard_churches",
        ],
    },
    "manage_conferences": {
        "name": "Manage Conferences",
        "category": "Organization",
        "description": "Create and edit conference records.",
        "default_roles": _ROLE_POLICY | {"GENERAL_OVERSEER"},
        "implies": ["view_all_churches"],
    },
    "manage_zones": {
        "name": "Manage Zones",
        "category": "Organization",
        "description": "Create and edit zone records.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": ["view_all_churches"],
    },
    "manage_districts": {
        "name": "Manage Districts",
        "category": "Organization",
        "description": "Create and edit district records.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": ["view_all_churches"],
    },
    "manage_churches": {
        "name": "Manage Churches",
        "category": "Organization",
        "description": "Create and edit church records.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": ["view_all_churches"],
    },
    "onboard_churches": {
        "name": "Onboard Churches",
        "category": "Organization",
        "description": "Run full hierarchy church onboarding.",
        "default_roles": _ROLE_HIERARCHY,
        "implies": ["manage_churches"],
    },

    # ── Administration / Users (6) ────────────────────────────────
    "manage_users": {
        "name": "Manage Users",
        "category": "Administration",
        "description": "Invite users, assign roles, and activate or deactivate accounts.",
        "default_roles": _ROLE_LEADERSHIP,
        "implies": ["invite_users", "assign_roles", "deactivate_users", "view_activity_logs"],
    },
    "invite_users": {
        "name": "Invite Users",
        "category": "Administration",
        "description": "Send institution user invitations.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "assign_roles": {
        "name": "Assign User Roles",
        "category": "Administration",
        "description": "Change roles for managed users.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "deactivate_users": {
        "name": "Activate / Deactivate Users",
        "category": "Administration",
        "description": "Enable or disable institution user accounts.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "view_activity_logs": {
        "name": "View Activity Logs",
        "category": "Administration",
        "description": "Review login, role change, and account audit events.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "impersonate_users": {
        "name": "Impersonate Users",
        "category": "Administration",
        "description": "Temporarily act as another institution user (audited).",
        "default_roles": _ROLE_POLICY,
    },

    # ── Permissions (4) ───────────────────────────────────────────
    "manage_permissions": {
        "name": "Manage Permissions",
        "category": "Administration",
        "description": "Edit the role-permission matrix and user permission overrides.",
        "default_roles": _ROLE_POLICY,
        "implies": ["manage_overrides", "view_permission_audit", "export_permission_matrix"],
    },
    "manage_overrides": {
        "name": "Manage Permission Overrides",
        "category": "Administration",
        "description": "Grant or deny per-user permission overrides.",
        "default_roles": _ROLE_POLICY,
    },
    "view_permission_audit": {
        "name": "View Permission Audit",
        "category": "Administration",
        "description": "Review permission matrix and override audit history.",
        "default_roles": _ROLE_POLICY | {"DISTRICT_PASTOR"},
    },
    "export_permission_matrix": {
        "name": "Export Permission Matrix",
        "category": "Administration",
        "description": "Download the role-permission matrix as CSV.",
        "default_roles": _ROLE_POLICY,
    },

    # ── Dashboard (3) ─────────────────────────────────────────────
    "view_dashboard": {
        "name": "View Dashboard",
        "category": "Dashboard",
        "description": "Access the main church dashboard home.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER", "MEMBER"},
    },
    "view_dashboard_finance": {
        "name": "View Finance Dashboard Widgets",
        "category": "Dashboard",
        "description": "See finance KPIs and cut-off widgets on the dashboard.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "view_dashboard_admin": {
        "name": "View Admin Dashboard Widgets",
        "category": "Dashboard",
        "description": "See leadership/admin command-center widgets.",
        "default_roles": _ROLE_LEADERSHIP,
    },
}


def registry_default_roles(codename):
    meta = PERMISSION_REGISTRY.get(codename, {})
    return set(meta.get("default_roles", set()))


def registry_implies(codename):
    return list(PERMISSION_REGISTRY.get(codename, {}).get("implies", []))


def registry_conflicts(codename):
    return list(PERMISSION_REGISTRY.get(codename, {}).get("conflicts_with", []))


def registry_count():
    return len(PERMISSION_REGISTRY)
