"""Custom authentication views."""

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy

from accounts.mfa import (
    SESSION_MFA_PENDING_BACKEND,
    SESSION_MFA_PENDING_USER,
    mark_mfa_verified,
    request_has_trusted_device,
    stamp_mfa_pending,
    user_requires_mfa,
)
from accounts.services import get_client_ip, log_activity
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


class MfaAwareLoginMixin:
    """Challenge or enroll MFA for privileged roles after password success."""

    def form_valid(self, form):
        user = form.get_user()
        if user_requires_mfa(user):
            if user.mfa_enabled:
                # Trusted device: complete login without TOTP/email challenge
                if request_has_trusted_device(self.request, user):
                    login(self.request, user)
                    mark_mfa_verified(self.request)
                    log_activity(
                        user,
                        "MFA_TRUSTED_DEVICE",
                        ip_address=get_client_ip(self.request),
                    )
                    return redirect(self.get_success_url())
                self.request.session[SESSION_MFA_PENDING_USER] = str(user.pk)
                self.request.session[SESSION_MFA_PENDING_BACKEND] = getattr(
                    user, "backend", "django.contrib.auth.backends.ModelBackend"
                )
                stamp_mfa_pending(self.request)
                return redirect("accounts:mfa_verify")
            login(self.request, user)
            self.request.session["mfa_verified"] = False
            self.request.session.modified = True
            return redirect("accounts:mfa_enroll")
        login(self.request, user)
        mark_mfa_verified(self.request)
        return redirect(self.get_success_url())


class ChurchHubLoginView(MfaAwareLoginMixin, LoginView):
    template_name = "login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_branding_context())
        return context

    def get_success_url(self):
        return post_login_url(self.request.user)


class MemberPortalLoginView(MfaAwareLoginMixin, LoginView):
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
