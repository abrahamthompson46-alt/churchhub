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


def _p(user, codename):
    return user_has_permission(user, codename)


# ── Members ───────────────────────────────────────────────────────
def can_view_members(user): return _p(user, "view_members")
def can_manage_members(user): return _p(user, "manage_members")
def can_add_members(user): return _p(user, "add_members")
def can_edit_members(user): return _p(user, "edit_members")
def can_export_members(user): return _p(user, "export_members")
def can_transfer_members(user): return _p(user, "transfer_members")
def can_process_transfers(user): return _p(user, "process_transfers")
def can_manage_baptisms(user): return _p(user, "manage_baptisms")
def can_manage_departments(user): return _p(user, "manage_departments")
def can_manage_families(user): return _p(user, "manage_families")
def can_manage_leadership(user): return _p(user, "manage_leadership")
def can_manage_spiritual_gifts(user): return _p(user, "manage_spiritual_gifts")
def can_view_member_records(user): return _p(user, "view_member_records")
def can_manage_member_records(user): return _p(user, "manage_member_records")

# ── Meetings ──────────────────────────────────────────────────────
def can_view_meetings(user): return _p(user, "view_meetings")
def can_manage_meetings(user): return _p(user, "manage_meetings")
def can_manage_attendance(user): return _p(user, "manage_attendance")
def can_submit_minutes(user): return _p(user, "submit_minutes")
def can_approve_minutes(user): return _p(user, "approve_minutes")
def can_export_minutes(user): return _p(user, "export_minutes")

# ── Finance ───────────────────────────────────────────────────────
def can_view_transactions(user): return _p(user, "view_transactions")
def can_manage_finances(user): return _p(user, "manage_finances")
def can_manage_receipts(user): return _p(user, "manage_receipts")
def can_manage_expenses(user): return _p(user, "manage_expenses")
def can_view_pending_approvals(user): return _p(user, "view_pending_approvals")
def can_approve_transactions(user): return _p(user, "approve_transactions")
def can_reject_transactions(user): return _p(user, "reject_transactions")
def can_void_transactions(user): return _p(user, "void_transactions")
def can_view_reconciliation(user): return _p(user, "view_reconciliation")
def can_manage_reconciliation(user): return _p(user, "manage_reconciliation")
def can_finalize_reconciliation(user): return _p(user, "finalize_reconciliation")
def can_view_audit_log(user): return _p(user, "view_audit_log")
def can_manage_working_day(user): return _p(user, "manage_working_day")
def can_lock_periods(user): return _p(user, "lock_periods")
def can_unlock_periods(user): return _p(user, "unlock_periods")
def can_run_cutoff(user): return _p(user, "run_cutoff")
def can_export_transactions(user): return _p(user, "export_transactions")

# ── Ledger ────────────────────────────────────────────────────────
def can_view_ledger(user): return _p(user, "view_ledger")
def can_manage_ledger_entries(user): return _p(user, "manage_ledger_entries")
def can_manage_gl_categories(user): return _p(user, "manage_gl_categories")
def can_manage_chart_of_accounts(user): return _p(user, "manage_chart_of_accounts")
def can_export_ledger(user): return _p(user, "export_ledger")
def can_view_trial_balance(user): return _p(user, "view_trial_balance")

# ── Remittance ────────────────────────────────────────────────────
def can_view_remittance(user): return _p(user, "view_remittance")
def can_manage_remittance_policy(user): return _p(user, "manage_remittance_policy")
def can_manage_settlements(user): return _p(user, "manage_settlements")
def can_post_settlements(user): return _p(user, "post_settlements")
def can_view_welfare(user): return _p(user, "view_welfare")
def can_manage_welfare_cases(user): return _p(user, "manage_welfare_cases")
def can_approve_welfare(user): return _p(user, "approve_welfare")
def can_disburse_welfare(user): return _p(user, "disburse_welfare")

# ── Payroll ───────────────────────────────────────────────────────
def can_view_payroll(user): return _p(user, "view_payroll")
def can_manage_payroll(user): return _p(user, "manage_payroll")
def can_approve_payroll(user): return _p(user, "approve_payroll")
def can_post_payroll(user): return _p(user, "post_payroll")
def can_pay_payroll(user): return _p(user, "pay_payroll")
def can_view_own_payslips(user): return _p(user, "view_payslips")
def can_manage_payroll_policy(user): return _p(user, "manage_payroll_policy")
def can_export_payroll(user): return _p(user, "export_payroll")

# ── Assets ────────────────────────────────────────────────────────
def can_view_assets(user): return _p(user, "view_assets")
def can_manage_assets(user): return _p(user, "manage_assets")
def can_approve_assets(user): return _p(user, "approve_assets")
def can_dispose_assets(user): return _p(user, "dispose_assets")
def can_manage_asset_policy(user): return _p(user, "manage_asset_policy")
def can_export_assets(user): return _p(user, "export_assets")

# ── Budgets / Giving ──────────────────────────────────────────────
def can_view_budgets(user): return _p(user, "view_budgets")
def can_manage_budgets(user): return _p(user, "manage_budgets")
def can_approve_budgets(user): return _p(user, "approve_budgets")
def can_lock_budgets(user): return _p(user, "lock_budgets")
def can_export_budgets(user): return _p(user, "export_budgets")
def can_view_giving(user): return _p(user, "view_giving")
def can_manage_giving(user): return _p(user, "manage_giving")
def can_view_own_giving(user): return _p(user, "view_own_giving")
def can_export_giving(user): return _p(user, "export_giving")

# ── Announcements ─────────────────────────────────────────────────
def can_view_announcements(user): return _p(user, "view_announcements")
def can_create_announcements(user): return _p(user, "create_announcements")
def can_approve_announcements(user): return _p(user, "approve_announcements")
def can_archive_announcements(user): return _p(user, "archive_announcements")
def can_export_announcements(user): return _p(user, "export_announcements")

# ── Reports ───────────────────────────────────────────────────────
def can_view_reports(user): return _p(user, "view_reports")
def can_view_member_reports(user): return _p(user, "view_member_reports")
def can_view_finance_reports(user): return _p(user, "view_finance_reports")
def can_view_hierarchy_reports(user): return _p(user, "view_hierarchy_reports")
def can_run_advanced_reports(user): return _p(user, "run_advanced_reports")
def can_export_reports_csv(user): return _p(user, "export_reports_csv")
def can_export_reports_excel(user): return _p(user, "export_reports_excel")
def can_export_reports_pdf(user): return _p(user, "export_reports_pdf")

# ── Organization ──────────────────────────────────────────────────
def can_view_all_churches(user): return _p(user, "view_all_churches")
def can_switch_church_context(user): return _p(user, "switch_church_context")
def can_manage_organization(user): return _p(user, "manage_organization")
def can_manage_conferences(user): return _p(user, "manage_conferences")
def can_manage_zones(user): return _p(user, "manage_zones")
def can_manage_districts(user): return _p(user, "manage_districts")
def can_manage_churches(user): return _p(user, "manage_churches")
def can_onboard_churches(user): return _p(user, "onboard_churches")

# ── Users / Permissions ───────────────────────────────────────────
def can_manage_users(user): return _p(user, "manage_users")
def can_invite_users(user): return _p(user, "invite_users")
def can_assign_roles(user): return _p(user, "assign_roles")
def can_deactivate_users(user): return _p(user, "deactivate_users")
def can_view_activity_logs(user): return _p(user, "view_activity_logs")
def can_impersonate_users(user): return _p(user, "impersonate_users")
def can_manage_permissions(user): return _p(user, "manage_permissions")
def can_manage_overrides(user): return _p(user, "manage_overrides")
def can_view_permission_audit(user): return _p(user, "view_permission_audit")
def can_export_permission_matrix(user): return _p(user, "export_permission_matrix")

# ── Dashboard ─────────────────────────────────────────────────────
def can_view_dashboard(user): return _p(user, "view_dashboard")
def can_view_dashboard_finance(user): return _p(user, "view_dashboard_finance")
def can_view_dashboard_admin(user): return _p(user, "view_dashboard_admin")


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
    return user_passes_test(
        lambda u: can_manage_finances(u) or can_view_transactions(u) or can_manage_receipts(u)
    )(view_func)


def manage_users_required(view_func):
    return user_passes_test(can_manage_users)(view_func)


def permissions_admin_required(view_func):
    return user_passes_test(can_manage_permissions)(view_func)


def permission_flags(user):
    """Dict of can_* → bool for template context / button visibility."""
    if not user or not user.is_authenticated:
        return {}
    flags = {}
    for name, fn in globals().items():
        if name.startswith("can_") and callable(fn):
            try:
                flags[name] = bool(fn(user))
            except Exception:
                flags[name] = False
    return flags


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
    "permission_flags",
    "role_required",
    "permission_required",
    "any_permission_required",
    "financial_required",
    "manage_users_required",
    "permissions_admin_required",
] + [n for n in globals() if n.startswith("can_")]
