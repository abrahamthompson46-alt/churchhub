"""Global template context processors."""

from church_system.church_scope import get_active_church, get_available_churches, get_user_church
from church_system.navigation import (
    get_account_navigation,
    get_main_navigation,
    get_module_tabs,
)


def church_context(request):
    if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
        return {
            "active_church": None,
            "user_church": None,
            "available_churches": [],
            "can_switch_church": False,
        }
    active_church = get_active_church(request) if request.user.is_authenticated else None
    churches = get_available_churches(request.user) if request.user.is_authenticated else []
    can_switch = request.user.is_authenticated and churches.count() > 1
    return {
        "active_church": active_church,
        "user_church": get_user_church(request.user),
        "available_churches": churches[:100],
        "can_switch_church": can_switch,
    }


def navigation_context(request):
    if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
        return {
            "main_navigation": [],
            "account_navigation": get_account_navigation(request.user),
            "current_view": "",
            "current_namespace": "",
            "report_key": "",
            "unread_notification_count": 0,
            "module_key": None,
            "module_tabs": [],
        }
    resolver = getattr(request, "resolver_match", None)
    current_view = ""
    namespace = ""
    if resolver:
        current_view = resolver.view_name or ""
        namespace = resolver.namespace or ""

    unread_notifications = 0
    if request.user.is_authenticated:
        from dashboard.models import Notification
        unread_notifications = Notification.objects.filter(
            user=request.user, read=False
        ).count()

    report_key = ""
    if resolver and resolver.namespace == "reports" and resolver.url_name == "run":
        report_key = resolver.kwargs.get("report_key", "")

    active_church = get_active_church(request) if request.user.is_authenticated else None
    module_key, module_tabs = get_module_tabs(
        request.user, namespace, current_view, active_church=active_church
    )

    return {
        "main_navigation": get_main_navigation(request.user, active_church=active_church),
        "account_navigation": get_account_navigation(request.user),
        "current_view": current_view,
        "current_namespace": namespace,
        "report_key": report_key,
        "unread_notification_count": unread_notifications,
        "module_key": module_key,
        "module_tabs": module_tabs,
    }


def platform_context(request):
    from sitecontrol.registration_services import (
        institution_invites_allowed,
        institution_onboarding_allowed,
        public_registration_allowed,
    )
    from sitecontrol.services import get_active_platform_announcement, get_site_settings

    settings_obj = get_site_settings()
    announcement = get_active_platform_announcement()
    impersonator_id = None
    if hasattr(request, "session"):
        impersonator_id = request.session.get("platform_impersonator_id")
    ctx = {
        "site_settings": settings_obj,
        "site_name": settings_obj.site_name,
        "site_logo": settings_obj.logo,
        "can_manage_platform": request.user.is_authenticated and getattr(
            request.user, "is_platform_user", False
        ),
        "platform_announcement": announcement,
        "public_registration_allowed": public_registration_allowed(),
        "institution_invites_allowed": institution_invites_allowed(),
        "institution_onboarding_allowed": institution_onboarding_allowed(),
        "is_impersonating": bool(impersonator_id),
        "impersonation_active": bool(impersonator_id),
    }
    if request.path.startswith("/platform/") and ctx["can_manage_platform"]:
        from sitecontrol.navigation import get_platform_navigation
        from sitecontrol.platform_access import get_operator_denominations, operator_has_global_access

        resolver = getattr(request, "resolver_match", None)
        ctx["platform_navigation"] = get_platform_navigation(request.user)
        ctx["platform_view"] = resolver.view_name if resolver else ""
        ctx["operator_has_global_access"] = operator_has_global_access(request.user)
        ctx["platform_denominations"] = get_operator_denominations(request.user)
        from church_system.denomination_scope import get_active_denomination

        ctx["platform_active_denomination"] = get_active_denomination(request)
    return ctx


def denomination_context(request):
    from church_system.denomination_scope import get_active_denomination
    from sitecontrol.denomination_services import get_terminology_context, hierarchy_chain_description
    from sitecontrol.services import get_site_settings

    denomination = get_active_denomination(request)
    terminology = get_terminology_context(denomination)
    settings_obj = get_site_settings()
    display_name = settings_obj.site_name
    primary_color = "#1d4ed8"
    accent_color = "#0e7490"
    logo = None
    tenant_display_name = ""
    if denomination:
        tenant_display_name = denomination.display_name or denomination.name
        display_name = tenant_display_name
        primary_color = denomination.primary_color or primary_color
        accent_color = denomination.accent_color or accent_color
        logo = denomination.logo

    ctx = {
        "active_denomination": denomination,
        "org_labels": terminology["labels"],
        "org_labels_plural": terminology["labels_plural"],
        "org_levels_enabled": terminology["levels_enabled"],
        "institution_display_name": display_name,
        "tenant_display_name": tenant_display_name,
        "institution_primary_color": primary_color,
        "institution_accent_color": accent_color,
        "denomination_logo": logo,
        "tenant_logo": logo,
        "hierarchy_chain": hierarchy_chain_description(denomination),
    }
    if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
        from sitecontrol.platform_access import get_operator_denominations

        ctx["platform_denominations"] = get_operator_denominations(request.user)
        ctx["platform_active_denomination"] = denomination
    return ctx


def working_day_context(request):
    """System clock and open/closed business day for navbar and dashboards."""
    from django.utils import timezone

    from accounts.permissions import can_approve_transactions, can_manage_finances
    from church_system.church_scope import get_active_church, get_user_church
    from transactions.services import get_working_day_status

    if not request.user.is_authenticated or getattr(request.user, "is_platform_user", False):
        return {}

    church = get_active_church(request) or get_user_church(request.user)
    if not church:
        return {
            "system_date": timezone.localdate(),
            "show_working_day_status": False,
        }

    status = get_working_day_status(church)
    return {
        "system_date": status["system_date"],
        "working_day_status": status,
        "active_working_day": status["active_working_day"],
        "working_date": status["working_date"],
        "working_day_is_open": status["is_open"],
        "show_working_day_status": can_manage_finances(request.user),
        "can_manage_working_day": can_approve_transactions(request.user),
    }
