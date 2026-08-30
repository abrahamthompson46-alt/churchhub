"""Global template context processors."""

from church_system.church_scope import get_active_church, get_available_churches, get_user_church
from church_system.navigation import (
    annotate_nav_badges,
    get_account_navigation,
    get_main_navigation,
    get_module_tabs,
    get_page_eyebrow,
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
        from dashboard.selectors import unread_notification_count

        unread_notifications = unread_notification_count(request.user)

    report_key = ""
    if resolver and resolver.namespace == "reports" and resolver.url_name == "run":
        report_key = resolver.kwargs.get("report_key", "")

    active_church = get_active_church(request) if request.user.is_authenticated else None
    module_key, module_tabs = get_module_tabs(
        request.user, namespace, current_view, active_church=active_church
    )

    main_navigation = get_main_navigation(request.user, active_church=active_church)
    if request.user.is_authenticated:
        from dashboard.services import get_nav_badges

        main_navigation = annotate_nav_badges(main_navigation, get_nav_badges(request))

    return {
        "main_navigation": main_navigation,
        "account_navigation": get_account_navigation(request.user),
        "current_view": current_view,
        "current_namespace": namespace,
        "report_key": report_key,
        "unread_notification_count": unread_notifications,
        "module_key": module_key,
        "module_tabs": module_tabs,
        "page_eyebrow": get_page_eyebrow(module_key, module_tabs, current_view, report_key),
    }


def platform_context(request):
    from sitecontrol.registration_services import (
        institution_invites_allowed,
        institution_onboarding_allowed,
        public_demo_trial_days,
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
        "site_tagline": settings_obj.site_tagline,
        "site_logo": settings_obj.logo,
        "site_favicon": settings_obj.favicon,
        "site_footer_text": settings_obj.footer_text or settings_obj.site_tagline,
        "login_highlights": [
            line.strip()
            for line in (settings_obj.login_highlights or "").splitlines()
            if line.strip()
        ],
        "can_manage_platform": request.user.is_authenticated and getattr(
            request.user, "is_platform_user", False
        ),
        "platform_announcement": announcement,
        "public_registration_allowed": public_registration_allowed(),
        "public_demo_trial_days": public_demo_trial_days(),
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
    from church_system.currency import currency_symbol, normalize_currency_code
    from church_system.denomination_scope import get_active_denomination
    from sitecontrol.branding_services import branding_css_block, resolve_institution_branding
    from sitecontrol.denomination_services import get_terminology_context, hierarchy_chain_description
    from sitecontrol.services import get_site_settings

    denomination = get_active_denomination(request)
    terminology = get_terminology_context(denomination)
    settings_obj = get_site_settings()
    branding = resolve_institution_branding(denomination=denomination, settings_obj=settings_obj)
    display_name = settings_obj.site_name
    logo = settings_obj.logo
    tenant_display_name = ""
    if denomination:
        tenant_display_name = denomination.display_name or denomination.name
        display_name = tenant_display_name
        if denomination.logo:
            logo = denomination.logo

    currency_code = normalize_currency_code(
        getattr(settings_obj, "default_billing_currency", None) or "GHS"
    )

    ctx = {
        "active_denomination": denomination,
        "org_labels": terminology["labels"],
        "org_labels_plural": terminology["labels_plural"],
        "org_levels_enabled": terminology["levels_enabled"],
        "institution_display_name": display_name,
        "tenant_display_name": tenant_display_name,
        "institution_primary_color": branding["primary_color"],
        "institution_accent_color": branding["accent_color"],
        "institution_highlight_color": branding["highlight_color"],
        "institution_branding": branding,
        "institution_branding_css": branding_css_block(branding),
        "denomination_logo": logo,
        "tenant_logo": logo,
        "hierarchy_chain": hierarchy_chain_description(denomination),
        "currency_code": currency_code,
        "currency_symbol": currency_symbol(currency_code),
    }
    if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
        from sitecontrol.platform_access import get_operator_denominations

        ctx["platform_denominations"] = get_operator_denominations(request.user)
        ctx["platform_active_denomination"] = denomination
    return ctx


def permission_context(request):
    """Expose can_* flags and has_perm map for template button visibility."""
    from permissions.checks import permission_flags
    from permissions.services import get_effective_permissions

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "is_platform_user", False):
        return {"perms": {}, "permission_flags": {}}

    flags = permission_flags(user)
    return {
        "perms": get_effective_permissions(user),
        "permission_flags": flags,
        # Flatten common flags into top-level for existing templates that use can_manage etc.
        **{k: v for k, v in flags.items() if k.startswith("can_")},
    }


def working_day_context(request):
    """System clock, working day, and cash position for the workspace status bar."""
    from django.utils import timezone

    from accounts.permissions import can_manage_working_day, can_view_dashboard_finance
    from church_system.church_scope import get_active_church, get_user_church
    from permissions.checks import can_view_transactions
    from transactions.services import get_working_day_status

    if not request.user.is_authenticated or getattr(request.user, "is_platform_user", False):
        return {}

    church = get_active_church(request) or get_user_church(request.user)
    if not church:
        return {
            "system_date": timezone.localdate(),
            "show_working_day_status": False,
            "show_cash_position": False,
            "cash_position": None,
        }

    status = get_working_day_status(church)
    show_finance = can_view_dashboard_finance(request.user) or can_view_transactions(request.user)
    cash_position = None
    if show_finance:
        from transactions.treasury import get_cash_position

        cash_position = get_cash_position(church)

    workspace_finance_mtd = None
    if show_finance:
        from dashboard.services import get_workspace_finance_mtd

        workspace_finance_mtd = get_workspace_finance_mtd(request)

    return {
        "system_date": status["system_date"],
        "working_day_status": status,
        "active_working_day": status["active_working_day"],
        "working_date": status["working_date"],
        "working_day_is_open": status["is_open"],
        "show_working_day_status": can_view_dashboard_finance(request.user),
        "can_manage_working_day": can_manage_working_day(request.user),
        "show_cash_position": show_finance,
        "cash_position": cash_position,
        "workspace_finance_mtd": workspace_finance_mtd,
    }
