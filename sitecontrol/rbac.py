"""Platform operator roles and capability-based access control."""

from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

PLATFORM_ROLES = [
    ("OWNER", "Platform Owner"),
    ("SECURITY", "Security Admin"),
    ("BILLING", "Billing Admin"),
    ("SUPPORT", "Support Operator"),
    ("READONLY", "Read Only"),
]

ROLE_OWNER = "OWNER"
ROLE_SECURITY = "SECURITY"
ROLE_BILLING = "BILLING"
ROLE_SUPPORT = "SUPPORT"
ROLE_READONLY = "READONLY"

CAP_VIEW = "view"
CAP_MANAGE_SETTINGS = "manage_settings"
CAP_MANAGE_SECURITY = "manage_security"
CAP_MANAGE_FEATURES = "manage_features"
CAP_MANAGE_EMAIL = "manage_email"
CAP_MANAGE_PLANS = "manage_plans"
CAP_MANAGE_SUBSCRIPTIONS = "manage_subscriptions"
CAP_MANAGE_TENANTS = "manage_tenants"
CAP_MANAGE_DENOMINATIONS = "manage_denominations"
CAP_MANAGE_APPLICATIONS = "manage_applications"
CAP_MANAGE_OPERATORS = "manage_operators"
CAP_GRANT_BREAKGLASS = "grant_breakglass"
CAP_MANAGE_ANNOUNCEMENTS = "manage_announcements"
CAP_MANAGE_REGISTRATION = "manage_registration"
CAP_VIEW_AUDIT = "view_audit"
CAP_EXPORT_AUDIT = "export_audit"
CAP_VIEW_BILLING = "view_billing"
CAP_OPS = "manage_ops"
CAP_IMPERSONATE = "impersonate"

ALL_CAPABILITIES = frozenset({
    CAP_VIEW,
    CAP_MANAGE_SETTINGS,
    CAP_MANAGE_SECURITY,
    CAP_MANAGE_FEATURES,
    CAP_MANAGE_EMAIL,
    CAP_MANAGE_PLANS,
    CAP_MANAGE_SUBSCRIPTIONS,
    CAP_MANAGE_TENANTS,
    CAP_MANAGE_DENOMINATIONS,
    CAP_MANAGE_APPLICATIONS,
    CAP_MANAGE_OPERATORS,
    CAP_GRANT_BREAKGLASS,
    CAP_MANAGE_ANNOUNCEMENTS,
    CAP_MANAGE_REGISTRATION,
    CAP_VIEW_AUDIT,
    CAP_EXPORT_AUDIT,
    CAP_VIEW_BILLING,
    CAP_OPS,
    CAP_IMPERSONATE,
})

ROLE_CAPABILITIES = {
    ROLE_OWNER: ALL_CAPABILITIES,
    ROLE_SECURITY: frozenset({
        CAP_VIEW,
        CAP_MANAGE_SECURITY,
        CAP_MANAGE_OPERATORS,
        CAP_GRANT_BREAKGLASS,
        CAP_VIEW_AUDIT,
        CAP_EXPORT_AUDIT,
        CAP_MANAGE_ANNOUNCEMENTS,
        CAP_MANAGE_REGISTRATION,
        CAP_OPS,
    }),
    ROLE_BILLING: frozenset({
        CAP_VIEW,
        CAP_MANAGE_PLANS,
        CAP_MANAGE_SUBSCRIPTIONS,
        CAP_VIEW_BILLING,
        CAP_MANAGE_TENANTS,
        CAP_VIEW_AUDIT,
    }),
    ROLE_SUPPORT: frozenset({
        CAP_VIEW,
        CAP_MANAGE_TENANTS,
        CAP_MANAGE_APPLICATIONS,
        CAP_MANAGE_ANNOUNCEMENTS,
        CAP_VIEW_AUDIT,
        CAP_IMPERSONATE,
    }),
    ROLE_READONLY: frozenset({
        CAP_VIEW,
        CAP_VIEW_AUDIT,
        CAP_VIEW_BILLING,
    }),
}

# Navigation item → required capability (view is enough when omitted)
NAV_ITEM_CAPABILITIES = {
    "sitecontrol:dashboard": CAP_VIEW,
    "sitecontrol:setup": CAP_VIEW,
    "sitecontrol:health": CAP_VIEW,
    "sitecontrol:audit_log": CAP_VIEW_AUDIT,
    "sitecontrol:ops_health": CAP_OPS,
    "sitecontrol:denomination_list": CAP_MANAGE_DENOMINATIONS,
    "sitecontrol:denomination_billing_rollups": CAP_VIEW_BILLING,
    "sitecontrol:application_list": CAP_MANAGE_APPLICATIONS,
    # Tenant browse is available to all operators with CAP_VIEW; mutations stay gated.
    "sitecontrol:tenant_list": CAP_VIEW,
    "sitecontrol:subscription_list": CAP_MANAGE_SUBSCRIPTIONS,
    "sitecontrol:subscription_record_payment": CAP_MANAGE_SUBSCRIPTIONS,
    "sitecontrol:plan_list": CAP_MANAGE_PLANS,
    "sitecontrol:payment_method_list": CAP_MANAGE_PLANS,
    "sitecontrol:billing_settings": CAP_MANAGE_PLANS,
    "sitecontrol:tenant_provision": CAP_MANAGE_TENANTS,
    "sitecontrol:tenant_resend_invitation": CAP_MANAGE_TENANTS,
    "sitecontrol:tenant_create_admin_invitation": CAP_MANAGE_TENANTS,
    "sitecontrol:tenant_set_user_role": CAP_MANAGE_TENANTS,
    "sitecontrol:hierarchy": CAP_VIEW,
    "sitecontrol:registration_settings": CAP_MANAGE_REGISTRATION,
    "sitecontrol:operator_list": CAP_MANAGE_OPERATORS,
    "sitecontrol:announcement_list": CAP_MANAGE_ANNOUNCEMENTS,
    "sitecontrol:settings": CAP_MANAGE_SETTINGS,
    "sitecontrol:branding": CAP_MANAGE_SETTINGS,
    "sitecontrol:email_settings": CAP_MANAGE_EMAIL,
    "sitecontrol:security_settings": CAP_MANAGE_SECURITY,
    "sitecontrol:features": CAP_MANAGE_FEATURES,
    "sitecontrol:member_lookup_list": CAP_MANAGE_SETTINGS,
}


def _is_breakglass_or_owner(user):
    if not user.is_authenticated or not getattr(user, "is_platform_user", False):
        return False
    if user.is_superuser:
        return True
    return getattr(user, "platform_role", "") == ROLE_OWNER


def operator_capabilities(user):
    """Return the frozenset of capabilities for a platform operator."""
    if not user.is_authenticated or not getattr(user, "is_platform_user", False):
        return frozenset()
    if _is_breakglass_or_owner(user):
        return ALL_CAPABILITIES
    role = getattr(user, "platform_role", "") or ""
    return ROLE_CAPABILITIES.get(role, frozenset({CAP_VIEW}))


def operator_has_capability(user, cap):
    if not cap:
        return False
    return cap in operator_capabilities(user)


def require_platform_capability(cap):
    """Decorator: platform user must hold the given capability."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not getattr(user, "is_platform_user", False):
                raise PermissionDenied("Platform access required.")
            if not operator_has_capability(user, cap):
                raise PermissionDenied("You do not have permission for this platform action.")
            return view_func(request, *args, **kwargs)

        return user_passes_test(
            lambda u: u.is_authenticated and getattr(u, "is_platform_user", False),
            login_url="/accounts/login/",
        )(_wrapped)

    return decorator
