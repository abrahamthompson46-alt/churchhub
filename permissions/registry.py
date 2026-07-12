"""Canonical permission catalog for the role-permission matrix."""

_ROLE_ALL_STAFF = {
    "SUPER_ADMIN", "GENERAL_OVERSEER", "DISTRICT_PASTOR", "LOCAL_PASTOR",
    "SECRETARY", "TREASURY",
}
_ROLE_LEADERSHIP = {
    "SUPER_ADMIN", "GENERAL_OVERSEER", "DISTRICT_PASTOR", "LOCAL_PASTOR",
}
_ROLE_HIERARCHY = {"SUPER_ADMIN", "GENERAL_OVERSEER", "DISTRICT_PASTOR"}

PERMISSION_REGISTRY = {
    "view_members": {
        "name": "View Members",
        "category": "Members",
        "description": "Read member directory, profiles, and pastoral records.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER", "MEMBER"},
    },
    "manage_members": {
        "name": "Manage Members",
        "category": "Members",
        "description": "Add, edit, transfer members; manage departments and families.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_members"],
    },
    "view_meetings": {
        "name": "View Meetings",
        "category": "Members",
        "description": "Search and read meeting minutes, decisions, and attachments.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "manage_meetings": {
        "name": "Manage Meetings",
        "category": "Members",
        "description": "Schedule meetings, draft minutes, record attendance and decisions.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY"},
        "implies": ["view_meetings"],
    },
    "approve_minutes": {
        "name": "Approve Meeting Minutes",
        "category": "Members",
        "description": "Review and approve submitted board and church meeting minutes.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "manage_finances": {
        "name": "Manage Finances",
        "category": "Finance",
        "description": "Record receipts, expenses, and access financial operations.",
        "default_roles": _ROLE_ALL_STAFF,
    },
    "approve_transactions": {
        "name": "Approve Transactions",
        "category": "Finance",
        "description": "Approve, void, and lock financial transactions.",
        "default_roles": _ROLE_LEADERSHIP,
        "conflicts_with": [],
    },
    "view_reports": {
        "name": "View Reports",
        "category": "Finance",
        "description": "Access the report center and export permitted analytics.",
        "default_roles": _ROLE_ALL_STAFF | {"BOARD_MEMBER"},
    },
    "view_all_churches": {
        "name": "View All Churches",
        "category": "Organization",
        "description": "Switch church context and view hierarchy-wide data.",
        "default_roles": _ROLE_HIERARCHY,
    },
    "manage_organization": {
        "name": "Manage Organization",
        "category": "Organization",
        "description": "Create and edit conference, zone, district, and church records.",
        "default_roles": _ROLE_HIERARCHY,
    },
    "manage_users": {
        "name": "Manage Users",
        "category": "Administration",
        "description": "Invite users, assign roles, and activate or deactivate accounts.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "view_activity_logs": {
        "name": "View Activity Logs",
        "category": "Administration",
        "description": "Review login, role change, and account audit events.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "create_announcements": {
        "name": "Create Announcements",
        "category": "Announcements",
        "description": "Draft and submit church announcements for approval.",
        "default_roles": _ROLE_LEADERSHIP | {"SECRETARY", "MEMBER"},
    },
    "approve_announcements": {
        "name": "Approve Announcements",
        "category": "Announcements",
        "description": "Approve or reject church announcements before publishing.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "manage_permissions": {
        "name": "Manage Permissions",
        "category": "Administration",
        "description": "Edit the role-permission matrix and user permission overrides.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER"},
    },
    "manage_remittance_policy": {
        "name": "Manage Remittance Policies",
        "category": "Finance",
        "description": "Configure retain and remit percentages per hierarchy level.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER"},
    },
    "manage_payroll": {
        "name": "Manage Payroll",
        "category": "Payroll",
        "description": "Maintain employees, compensation, and prepare payroll runs.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER", "TREASURY"},
    },
    "approve_payroll": {
        "name": "Approve Payroll",
        "category": "Payroll",
        "description": "Approve calculated payroll runs before posting.",
        "default_roles": _ROLE_LEADERSHIP,
    },
    "post_payroll": {
        "name": "Post Payroll",
        "category": "Payroll",
        "description": "Post approved payroll to the general ledger.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER", "TREASURY"},
    },
    "pay_payroll": {
        "name": "Pay Payroll",
        "category": "Payroll",
        "description": "Record bank payment for posted payroll runs.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER", "TREASURY"},
    },
    "view_payslips": {
        "name": "View Payslips",
        "category": "Payroll",
        "description": "View own payslips via employee self-service.",
        "default_roles": _ROLE_ALL_STAFF | {"SECRETARY", "MEMBER"},
    },
    "manage_payroll_policy": {
        "name": "Manage Payroll Policies",
        "category": "Payroll",
        "description": "Configure PAYE bands and statutory contribution rules.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER"},
    },
    "manage_assets": {
        "name": "Manage Fixed Assets",
        "category": "Finance",
        "description": "Create and maintain fixed asset records and maintenance logs.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER", "TREASURY", "SECRETARY"},
    },
    "approve_assets": {
        "name": "Approve Fixed Assets",
        "category": "Finance",
        "description": "Approve asset acquisitions before they become active.",
        "default_roles": _ROLE_LEADERSHIP | {"TREASURY"},
    },
    "manage_asset_policy": {
        "name": "Manage Asset Policies",
        "category": "Finance",
        "description": "Configure depreciation methods, categories, and ledger posting options.",
        "default_roles": {"SUPER_ADMIN", "GENERAL_OVERSEER", "TREASURY"},
    },
}


def registry_default_roles(codename):
    meta = PERMISSION_REGISTRY.get(codename, {})
    return set(meta.get("default_roles", set()))


def registry_implies(codename):
    return list(PERMISSION_REGISTRY.get(codename, {}).get("implies", []))


def registry_conflicts(codename):
    return list(PERMISSION_REGISTRY.get(codename, {}).get("conflicts_with", []))
