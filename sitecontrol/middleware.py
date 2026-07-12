"""Platform middleware: session timeout, login rate limit, maintenance mode, user scope."""

from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse

from sitecontrol.checks import can_access_django_admin, can_manage_platform
from sitecontrol.services import get_site_settings, ip_allowed_for_platform

SHARED_EXEMPT_PREFIXES = (
    "/accounts/login",
    "/accounts/logout",
    "/accounts/password",
    "/apply/",
    "/static/",
    "/media/",
    "/health/",
    "/platform/impersonate/end/",
)

INSTITUTION_PREFIXES = (
    "/dashboard/",
    "/members/",
    "/organization/",
    "/transactions/",
    "/permissions/",
    "/announcements/",
    "/reports/",
    "/meetings/",
    "/budgets/",
    "/giving/",
    "/ledger/",
    "/remittance/",
    "/payroll/",
    "/assets/",
)

INSTITUTION_ACCOUNT_PATHS = (
    "/accounts/profile",
    "/accounts/invite/accept",
)


class UserScopeMiddleware:
    """Enforce platform vs institution access lanes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        if any(path.startswith(p) for p in SHARED_EXEMPT_PREFIXES):
            return self.get_response(request)

        user = request.user
        is_platform = getattr(user, "is_platform_user", False)

        if path.startswith("/admin/"):
            if not can_access_django_admin(user):
                return HttpResponseForbidden("Django admin is restricted to break-glass platform operators.")
            return self.get_response(request)

        if path.startswith("/platform/"):
            if not can_manage_platform(user):
                messages.error(request, "You do not have access to the platform control room.")
                return redirect("dashboard:home")
            settings_obj = get_site_settings()
            client_ip = request.META.get("REMOTE_ADDR", "")
            if not ip_allowed_for_platform(client_ip, settings_obj):
                return HttpResponseForbidden(
                    "Your IP address is not permitted to access the platform control room."
                )
            return self.get_response(request)

        if is_platform:
            # Platform operators may use profile (and invite-accept) under /accounts/.
            if any(path.startswith(p) for p in INSTITUTION_ACCOUNT_PATHS):
                return self.get_response(request)
            if any(path.startswith(p) for p in INSTITUTION_PREFIXES) or path.startswith("/accounts/"):
                return redirect("sitecontrol:dashboard")

        return self.get_response(request)


class PlatformSessionMiddleware:
    """Apply site-owner session timeout from SiteSettings."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request, "session"):
            settings_obj = get_site_settings()
            timeout = settings_obj.session_timeout_minutes * 60
            request.session.set_expiry(timeout)
        return self.get_response(request)


class MaintenanceModeMiddleware:
    """Block institution users when maintenance mode is on."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        settings_obj = get_site_settings()
        if not settings_obj.maintenance_mode:
            return self.get_response(request)

        exempt = (
            request.path.startswith("/admin/"),
            request.path.startswith("/platform/"),
            request.path.startswith("/static/"),
            request.path.startswith("/health/"),
            (
                request.path.startswith("/apply/")
                and not getattr(settings_obj, "maintenance_block_apply", True)
            ),
            request.path == reverse("login"),
        )
        if any(exempt):
            return self.get_response(request)

        if request.user.is_authenticated:
            if can_manage_platform(request.user):
                return self.get_response(request)
            logout(request)
            messages.warning(request, settings_obj.maintenance_message)

        if request.path.startswith("/accounts/login"):
            return self.get_response(request)

        return HttpResponseForbidden(settings_obj.maintenance_message)


class LoginRateLimitMiddleware:
    """Throttle repeated failed login attempts by IP and username."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path.rstrip("/") == "/accounts/login":
            settings_obj = get_site_settings()
            ip = request.META.get("REMOTE_ADDR", "unknown")
            username = (request.POST.get("username") or "").strip().lower()
            lock_key = f"login_lock:{ip}"
            user_lock_key = f"login_lock_user:{username}" if username else None

            if cache.get(lock_key) or (user_lock_key and cache.get(user_lock_key)):
                messages.error(
                    request,
                    f"Too many failed login attempts. Try again in "
                    f"{settings_obj.login_lockout_minutes} minutes.",
                )
                return redirect("login")

            response = self.get_response(request)

            if request.user.is_authenticated:
                cache.delete(f"login_fail:{ip}")
                if username:
                    cache.delete(f"login_fail_user:{username}")
                return response

            ttl = settings_obj.login_lockout_minutes * 60
            fail_key = f"login_fail:{ip}"
            fails = cache.get(fail_key, 0) + 1
            cache.set(fail_key, fails, ttl)
            if fails >= settings_obj.login_max_attempts:
                cache.set(lock_key, True, ttl)
                cache.delete(fail_key)

            if username:
                user_fail_key = f"login_fail_user:{username}"
                user_fails = cache.get(user_fail_key, 0) + 1
                cache.set(user_fail_key, user_fails, ttl)
                if user_fails >= settings_obj.login_max_attempts:
                    cache.set(user_lock_key, True, ttl)
                    cache.delete(user_fail_key)
            return response

        return self.get_response(request)
