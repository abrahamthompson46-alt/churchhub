"""Custom authentication views."""

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy

from permissions.roles import UserRole


def post_login_url(user):
    """Route users to the right home after authentication."""
    if getattr(user, "is_platform_user", False):
        return reverse_lazy("sitecontrol:dashboard")
    if getattr(user, "role", None) == UserRole.MEMBER:
        return reverse_lazy("portal:home")
    return reverse_lazy("dashboard:home")


def _branding_context():
    """Restore platform branding — LoginView overwrites site_name with RequestSite."""
    from sitecontrol.services import get_site_settings

    settings_obj = get_site_settings()
    return {
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
        "platform_name": settings_obj.site_name,
    }


class ChurchHubLoginView(LoginView):
    template_name = "login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_branding_context())
        return context

    def get_success_url(self):
        return post_login_url(self.request.user)


class MemberPortalLoginView(LoginView):
    """Member-facing sign-in — separate landing from staff operations login."""

    template_name = "portal/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_branding_context())
        return context

    def get_success_url(self):
        user = self.request.user
        if getattr(user, "is_platform_user", False):
            return reverse_lazy("sitecontrol:dashboard")
        if getattr(user, "member_id", None) or getattr(user, "role", None) == UserRole.MEMBER:
            return reverse_lazy("portal:home")
        return reverse_lazy("dashboard:home")
