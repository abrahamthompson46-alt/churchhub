"""Platform middleware: session timeout, login rate limit, maintenance mode, user scope."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse

from church_system.client_ip import get_client_ip

from sitecontrol.checks import can_access_django_admin, can_manage_platform
from sitecontrol.services import (
    get_site_settings,
    ip_allowed_for_platform,
    platform_ip_allowlist_configured,
)

SHARED_EXEMPT_PREFIXES = (
    "/accounts/login",
    "/accounts/logout",
    "/accounts/password",
    "/dashboard/logout",
    "/apply/",
    "/static/",
    # Keep all /media/ scope-exempt so platform support can open auth-gated files;
    # anonymity is enforced in church_system.media_views, not here.
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
    "/contributions/",
    "/ledger/",
    "/remittance/",
    "/payroll/",
    "/assets/",
    "/portal/",
)

INSTITUTION_ACCOUNT_PATHS = (
    "/accounts/profile",
    "/accounts/invite/accept",
    "/accounts/mfa/",
    "/accounts/subscription-",
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
            if getattr(settings, "REQUIRE_PLATFORM_IP_ALLOWLIST", False):
                if not platform_ip_allowlist_configured(settings_obj):
                    return HttpResponseForbidden(
                        "Platform control room requires an IP allowlist. "
                        "Configure platform_ip_allowlist in Site Settings."
                    )
            client_ip = get_client_ip(request) or ""
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


class SubscriptionAccessMiddleware:
    """
    Hard cutoff for church subscriptions that are not operational.

    Date on TenantSubscription.expires_at is the source of truth. Nightly
    expire_due_subscriptions is hygiene only — this runs on every request.
    """

    EXEMPT_PREFIXES = (
        "/accounts/login",
        "/accounts/logout",
        "/accounts/subscription-",
        "/static/",
        "/health/",
        "/metrics/",
        "/apply/",
        "/contact/",
        "/admin/login",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)
        if getattr(user, "is_platform_user", False):
            return self.get_response(request)

        path = request.path
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        church = getattr(user, "church", None)
        if not church:
            return self.get_response(request)

        from sitecontrol.services import get_church_subscription

        sub = get_church_subscription(church)
        if sub is None or sub.is_operational:
            from sitecontrol.activation_services import maybe_notify_expiry_warning

            maybe_notify_expiry_warning(request, user, church, sub)
            return self.get_response(request)
        return redirect("subscription_expired")


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
            request.path.startswith("/metrics/"),
            (
                request.path.startswith("/apply/")
                and not getattr(settings_obj, "maintenance_block_apply", True)
            ),
            request.path == reverse("login"),
            request.path == reverse("public_home"),
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
    """Throttle failed auth POSTs: staff login, portal login, password reset, and /apply/."""

    LOGIN_PATHS = frozenset({"/accounts/login", "/portal/login"})
    # MFA verify is throttled in accounts.mfa (per-user + per-IP), not here:
    # this limiter keys on posted username, which /accounts/mfa does not receive.
    RESET_REQUEST_PATHS = frozenset({"/accounts/password_reset", "/portal/password/reset"})
    APPLY_PATH = "/apply"
    PORTAL_LOGIN_MAX_ATTEMPTS = 3
    APPLY_MAX_ATTEMPTS = 5

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _norm_path(path: str) -> str:
        return path.rstrip("/") or "/"

    @classmethod
    def _is_login_path(cls, path: str) -> bool:
        return path in cls.LOGIN_PATHS

    @classmethod
    def _is_reset_path(cls, path: str) -> bool:
        if path in cls.RESET_REQUEST_PATHS:
            return True
        # Django confirm: /accounts/reset/<uidb64>/<token>
        # Portal confirm: /portal/password/reset/<uidb64>/<token>
        parts = path.strip("/").split("/")
        if (
            len(parts) == 4
            and parts[0] == "accounts"
            and parts[1] == "reset"
            and parts[3] != "done"
        ):
            return True
        return (
            len(parts) == 5
            and parts[0] == "portal"
            and parts[1] == "password"
            and parts[2] == "reset"
            and parts[4] != "complete"
            and parts[3] != "done"
        )

    @classmethod
    def _is_apply_path(cls, path: str) -> bool:
        return path == cls.APPLY_PATH

    @staticmethod
    def _login_succeeded(request) -> bool:
        if request.user.is_authenticated:
            return True
        # Privileged MFA: password OK, challenge pending (not yet authenticated).
        if request.session.get("mfa_pending_user_id"):
            return True
        # Portal: credentials OK, waiting for email device confirmation.
        if request.session.get("portal_pending_email"):
            return True
        return False

    def __call__(self, request):
        if request.method != "POST":
            return self.get_response(request)

        path = self._norm_path(request.path)
        is_login = self._is_login_path(path)
        is_reset = self._is_reset_path(path)
        is_apply = self._is_apply_path(path)
        if not is_login and not is_reset and not is_apply:
            return self.get_response(request)

        settings_obj = get_site_settings()
        ip = get_client_ip(request) or "unknown"
        ttl = settings_obj.login_lockout_minutes * 60
        max_attempts = settings_obj.login_max_attempts

        if is_apply:
            lock_key = f"apply_lock:{ip}"
            if cache.get(lock_key):
                messages.error(
                    request,
                    f"Too many registration attempts. Try again in "
                    f"{settings_obj.login_lockout_minutes} minutes.",
                )
                return redirect("church_apply")

            response = self.get_response(request)
            if response.status_code in (301, 302, 303, 307, 308):
                cache.delete(f"apply_fail:{ip}")
                return response

            fail_key = f"apply_fail:{ip}"
            fails = cache.get(fail_key, 0) + 1
            cache.set(fail_key, fails, ttl)
            if fails >= self.APPLY_MAX_ATTEMPTS:
                cache.set(lock_key, True, ttl)
                cache.delete(fail_key)
            return response

        if is_login:
            username = (request.POST.get("username") or "").strip().lower()
            lock_key = f"login_lock:{ip}"
            user_lock_key = f"login_lock_user:{username}" if username else None
            redirect_name = "portal:login" if path == "/portal/login" else "login"
            portal_attempt_cap = min(self.PORTAL_LOGIN_MAX_ATTEMPTS, max_attempts)
            attempt_cap = portal_attempt_cap if path == "/portal/login" else max_attempts

            if cache.get(lock_key) or (user_lock_key and cache.get(user_lock_key)):
                messages.error(
                    request,
                    f"Too many failed login attempts. Try again in "
                    f"{settings_obj.login_lockout_minutes} minutes.",
                )
                return redirect(redirect_name)

            response = self.get_response(request)

            if self._login_succeeded(request):
                cache.delete(f"login_fail:{ip}")
                if username:
                    cache.delete(f"login_fail_user:{username}")
                return response

            fail_key = f"login_fail:{ip}"
            fails = cache.get(fail_key, 0) + 1
            cache.set(fail_key, fails, ttl)
            if fails >= attempt_cap:
                cache.set(lock_key, True, ttl)
                cache.delete(fail_key)

            if username:
                user_fail_key = f"login_fail_user:{username}"
                user_fails = cache.get(user_fail_key, 0) + 1
                cache.set(user_fail_key, user_fails, ttl)
                if user_fails >= attempt_cap:
                    cache.set(user_lock_key, True, ttl)
                    cache.delete(user_fail_key)
            return response

        # Password reset request / confirm — throttle by IP (+ email when present).
        email = (request.POST.get("email") or "").strip().lower()
        lock_key = f"reset_lock:{ip}"
        email_lock_key = f"reset_lock_email:{email}" if email else None

        if cache.get(lock_key) or (email_lock_key and cache.get(email_lock_key)):
            messages.error(
                request,
                f"Too many password reset attempts. Try again in "
                f"{settings_obj.login_lockout_minutes} minutes.",
            )
            if path.startswith("/portal/"):
                return redirect("portal:password_reset")
            return redirect("password_reset")

        response = self.get_response(request)

        fail_key = f"reset_fail:{ip}"
        fails = cache.get(fail_key, 0) + 1
        cache.set(fail_key, fails, ttl)
        if fails >= max_attempts:
            cache.set(lock_key, True, ttl)
            cache.delete(fail_key)

        if email:
            email_fail_key = f"reset_fail_email:{email}"
            email_fails = cache.get(email_fail_key, 0) + 1
            cache.set(email_fail_key, email_fails, ttl)
            if email_fails >= max_attempts:
                cache.set(email_lock_key, True, ttl)
                cache.delete(email_fail_key)
        return response
