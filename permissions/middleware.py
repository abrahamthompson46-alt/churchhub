"""Role enforcement and permission caching middleware."""

from django.shortcuts import redirect
from django.urls import reverse

from church_system.flash import flash_warning
from permissions.checks import can_view_all_churches
from permissions.services import bind_request_permission_cache, clear_request_permission_cache

EXEMPT_PREFIXES = (
    "/accounts/login",
    "/accounts/logout",
    "/accounts/password",
    "/accounts/invite/accept",
    "/accounts/profile",
    "/admin/",
    "/platform/",
    "/apply/",
    "/static/",
    "/media/",
    "/health/",
    "/permissions/",
)


class PermissionCacheMiddleware:
    """Cache permission lookups on the request to avoid repeated DB hits."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        bind_request_permission_cache(request)
        try:
            return self.get_response(request)
        finally:
            clear_request_permission_cache()


class RoleEnforcementMiddleware:
    """Ensure local-role users have a church assigned before accessing the app."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path
            if not any(path.startswith(p) for p in EXEMPT_PREFIXES):
                user = request.user
                if (
                    not can_view_all_churches(user)
                    and user.requires_church
                    and not user.church_id
                    and not getattr(user, "is_platform_user", False)
                ):
                    profile_url = reverse("accounts:profile")
                    if path != profile_url:
                        flash_warning(
                            request,
                            "Contact an administrator to assign your account to a church.",
                            title="Church assignment required",
                        )
                        return redirect("accounts:profile")
        return self.get_response(request)
