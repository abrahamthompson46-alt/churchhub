"""MFA enrollment and login challenge enforcement."""

from django.shortcuts import redirect

from accounts.mfa import (
    SESSION_MFA_PENDING_USER,
    request_has_trusted_device,
    session_mfa_verified,
    user_requires_mfa,
    mark_mfa_verified,
)
from church_system.flash import flash_warning
from accounts.services import get_client_ip, log_activity

MFA_EXEMPT_PREFIXES = (
    "/accounts/login",
    "/accounts/logout",
    "/accounts/password",
    "/accounts/invite/accept",
    "/accounts/mfa/",
    "/portal/login",
    "/portal/confirm",
    "/portal/password",
    "/admin/login",
    "/static/",
    # Public branding only — private /media/* requires MFA-verified sessions.
    "/media/platform/branding/",
    "/media/denominations/branding/",
    "/health/",
    "/metrics/",
)

# Session key set while a platform operator is impersonating an institution user.
IMPERSONATION_ACTIVE_SESSION_KEY = "impersonation_active"


class MfaEnforcementMiddleware:
    """
    Block privileged sessions until MFA is enrolled and verified.

    - Privileged user without enrollment → enroll only.
    - Privileged user with enrollment but session not verified → verify only
      (covers edge cases after password login before challenge completes).
    - Pending MFA user id in session (password OK, not logged in) → verify only.
    - Valid trusted-device cookie → mark session verified and continue.
    - Active platform impersonation → skip MFA enroll/verify so operators cannot
      bind TOTP to the impersonated account (session is audited separately).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(prefix) for prefix in MFA_EXEMPT_PREFIXES):
            return self.get_response(request)

        # Support impersonation must not trigger MFA enrollment on the target user.
        if request.session.get(IMPERSONATION_ACTIVE_SESSION_KEY) or request.session.get(
            "platform_impersonator_id"
        ):
            return self.get_response(request)

        pending_id = request.session.get(SESSION_MFA_PENDING_USER)
        if pending_id and not request.user.is_authenticated:
            return redirect("accounts:mfa_verify")

        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)

        if not user_requires_mfa(user):
            return self.get_response(request)

        if not user.mfa_enabled:
            if not path.startswith("/accounts/mfa/"):
                flash_warning(
                    request,
                    "Multi-factor authentication is required for your role. Please enroll now.",
                )
                return redirect("accounts:mfa_enroll")
            return self.get_response(request)

        if not session_mfa_verified(request):
            if request_has_trusted_device(request, user):
                mark_mfa_verified(request)
                log_activity(
                    user,
                    "MFA_TRUSTED_DEVICE",
                    ip_address=get_client_ip(request),
                )
                return self.get_response(request)
            if not path.startswith("/accounts/mfa/"):
                flash_warning(request, "Enter your authenticator code to continue.")
                return redirect("accounts:mfa_verify")
            return self.get_response(request)

        return self.get_response(request)
