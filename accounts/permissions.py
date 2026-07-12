"""
Backward-compatible re-exports.

Prefer `from permissions.checks import ...` in new code.
This module remains for legacy imports only.
"""

from permissions.checks import (  # noqa: F401
    APPROVAL_ROLES,
    APPROVE_ANNOUNCEMENT_ROLES,
    FINANCIAL_ROLES,
    HIERARCHY_ROLES,
    MEMBER_MANAGEMENT_ROLES,
    PERMISSION_ADMIN_ROLES,
    USER_MANAGEMENT_ROLES,
    UserRole,
    any_permission_required,
    can_approve_announcements,
    can_approve_assets,
    can_approve_minutes,
    can_approve_payroll,
    can_approve_transactions,
    can_create_announcements,
    can_manage_asset_policy,
    can_manage_assets,
    can_manage_finances,
    can_manage_meetings,
    can_manage_members,
    can_manage_organization,
    can_manage_payroll,
    can_manage_payroll_policy,
    can_manage_permissions,
    can_manage_remittance_policy,
    can_manage_users,
    can_pay_payroll,
    can_post_payroll,
    can_view_activity_logs,
    can_view_all_churches,
    can_view_meetings,
    can_view_members,
    can_view_own_payslips,
    can_view_reports,
    financial_required,
    is_superadmin,
    manage_users_required,
    permission_required,
    permissions_admin_required,
    role_required,
    user_has_permission,
    user_has_role,
)
from permissions.scoping import get_manageable_churches, get_manageable_users  # noqa: F401
