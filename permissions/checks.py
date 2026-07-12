"""Authorization check helpers — delegate to the permission matrix."""

from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from permissions.roles import (
    APPROVE_ANNOUNCEMENT_ROLES,
    APPROVAL_ROLES,
    FINANCIAL_ROLES,
    HIERARCHY_ROLES,
    MEMBER_MANAGEMENT_ROLES,
    PERMISSION_ADMIN_ROLES,
    USER_MANAGEMENT_ROLES,
    UserRole,
)
from permissions.services import user_has_permission
from permissions.superadmin import is_superadmin


def user_has_role(user, roles):
    if not user.is_authenticated:
        return False
    if is_superadmin(user):
        return True
    return user.role in roles


def can_view_members(user):
    return user_has_permission(user, "view_members")


def can_manage_members(user):
    return user_has_permission(user, "manage_members")


def can_view_meetings(user):
    return user_has_permission(user, "view_meetings")


def can_manage_meetings(user):
    return user_has_permission(user, "manage_meetings")


def can_manage_finances(user):
    return user_has_permission(user, "manage_finances")


def can_approve_transactions(user):
    return user_has_permission(user, "approve_transactions")


def can_view_all_churches(user):
    return user_has_permission(user, "view_all_churches")


def can_manage_organization(user):
    return user_has_permission(user, "manage_organization")


def can_view_activity_logs(user):
    return user_has_permission(user, "view_activity_logs")


def can_manage_users(user):
    return user_has_permission(user, "manage_users")


def can_approve_announcements(user):
    return user_has_permission(user, "approve_announcements")


def can_create_announcements(user):
    return user_has_permission(user, "create_announcements")


def can_approve_minutes(user):
    return user_has_permission(user, "approve_minutes")


def can_view_reports(user):
    return user_has_permission(user, "view_reports")


def can_manage_permissions(user):
    return user_has_permission(user, "manage_permissions")


def can_manage_remittance_policy(user):
    return user_has_permission(user, "manage_remittance_policy")


def can_manage_payroll(user):
    return user_has_permission(user, "manage_payroll")


def can_approve_payroll(user):
    return user_has_permission(user, "approve_payroll")


def can_post_payroll(user):
    return user_has_permission(user, "post_payroll")


def can_pay_payroll(user):
    return user_has_permission(user, "pay_payroll")


def can_view_own_payslips(user):
    return user_has_permission(user, "view_payslips")


def can_manage_payroll_policy(user):
    return user_has_permission(user, "manage_payroll_policy")


def can_manage_assets(user):
    return user_has_permission(user, "manage_assets")


def can_approve_assets(user):
    return user_has_permission(user, "approve_assets")


def can_manage_asset_policy(user):
    return user_has_permission(user, "manage_asset_policy")


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not user_has_role(request.user, set(roles)):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def permission_required(codename):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not user_has_permission(request.user, codename):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def any_permission_required(*codenames):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not any(user_has_permission(request.user, c) for c in codenames):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def financial_required(view_func):
    return user_passes_test(can_manage_finances)(view_func)


def manage_users_required(view_func):
    return user_passes_test(can_manage_users)(view_func)


def permissions_admin_required(view_func):
    return user_passes_test(can_manage_permissions)(view_func)


__all__ = [
    "UserRole",
    "FINANCIAL_ROLES",
    "APPROVAL_ROLES",
    "HIERARCHY_ROLES",
    "MEMBER_MANAGEMENT_ROLES",
    "USER_MANAGEMENT_ROLES",
    "APPROVE_ANNOUNCEMENT_ROLES",
    "PERMISSION_ADMIN_ROLES",
    "is_superadmin",
    "user_has_role",
    "user_has_permission",
    "can_view_members",
    "can_manage_members",
    "can_view_meetings",
    "can_manage_meetings",
    "can_manage_finances",
    "can_approve_transactions",
    "can_view_all_churches",
    "can_manage_organization",
    "can_manage_members",
    "can_manage_users",
    "can_approve_announcements",
    "can_create_announcements",
    "can_approve_minutes",
    "can_view_reports",
    "can_view_activity_logs",
    "can_manage_permissions",
    "can_manage_remittance_policy",
    "can_manage_payroll",
    "can_approve_payroll",
    "can_post_payroll",
    "can_pay_payroll",
    "can_view_own_payslips",
    "can_manage_payroll_policy",
    "can_manage_assets",
    "can_approve_assets",
    "can_manage_asset_policy",
    "role_required",
    "permission_required",
    "any_permission_required",
    "financial_required",
    "manage_users_required",
    "permissions_admin_required",
]
