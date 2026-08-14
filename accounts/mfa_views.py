"""MFA enrollment and challenge views."""

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts import selectors
from accounts.mfa import (
    SESSION_MFA_ENROLL_SECRET,
    SESSION_MFA_PENDING_BACKEND,
    SESSION_MFA_PENDING_USER,
    TRUSTED_DEVICE_DAYS,
    attach_trusted_device_cookie,
    clear_mfa_failures,
    clear_mfa_session,
    create_trusted_device,
    enable_mfa_for_user,
    generate_recovery_codes,
    generate_totp_secret,
    mark_mfa_verified,
    mfa_pending_expired,
    mfa_verify_allowed,
    record_mfa_failure,
    request_has_trusted_device,
    send_mfa_email_otp,
    totp_provisioning_uri,
    totp_qr_data_uri,
    user_can_receive_email_otp,
    user_requires_mfa,
    verify_totp,
    verify_user_mfa,
)
from accounts.services import get_client_ip, log_activity
from church_system.auth import post_login_url
from church_system.flash import flash_error, flash_success


def _pending_user(request):
    user_id = request.session.get(SESSION_MFA_PENDING_USER)
    if not user_id:
        return None
    user = selectors.get_user_or_none(user_id)
    if user is None:
        request.session.pop(SESSION_MFA_PENDING_USER, None)
    return user


def _challenge_user(request):
    if request.user.is_authenticated:
        return request.user
    return _pending_user(request)


def _complete_mfa_login(request, user, *, method: str, remember_device: bool):
    if not request.user.is_authenticated:
        backend = request.session.get(SESSION_MFA_PENDING_BACKEND) or (
            "django.contrib.auth.backends.ModelBackend"
        )
        login(request, user, backend=backend)
    mark_mfa_verified(request)
    action = {
        "totp": "MFA_VERIFY",
        "email": "MFA_EMAIL",
        "recovery": "MFA_RECOVERY",
        "trusted": "MFA_TRUSTED_DEVICE",
    }.get(method, "MFA_VERIFY")
    log_activity(user, action, ip_address=get_client_ip(request))
    response = redirect(post_login_url(user))
    if remember_device:
        token = create_trusted_device(user, request)
        attach_trusted_device_cookie(response, token)
    return response


@login_required
@require_http_methods(["GET", "POST"])
def mfa_enroll(request):
    user = request.user
    if not user_requires_mfa(user):
        return redirect(post_login_url(user))
    if user.mfa_enabled:
        return redirect("accounts:mfa_verify")

    # Keep the same secret across reloads so the scanned QR still matches.
    # Only mint a new secret when missing, or when the user asks to regenerate.
    regenerate = (
        request.method == "POST" and request.POST.get("action") == "regenerate"
    )
    if regenerate or not request.session.get(SESSION_MFA_ENROLL_SECRET):
        secret = generate_totp_secret()
        request.session[SESSION_MFA_ENROLL_SECRET] = secret
        request.session.modified = True
    else:
        secret = request.session[SESSION_MFA_ENROLL_SECRET]

    error = ""
    if request.method == "POST" and not regenerate:
        ip = get_client_ip(request)
        allowed, lock_msg = mfa_verify_allowed(user, ip)
        if not allowed:
            error = lock_msg
            return render(
                request,
                "accounts/mfa_enroll.html",
                {
                    "secret": secret,
                    "provisioning_uri": totp_provisioning_uri(user, secret),
                    "qr_data_uri": totp_qr_data_uri(user, secret),
                    "error": error,
                    "trusted_device_days": TRUSTED_DEVICE_DAYS,
                },
                status=429,
            )
        token = request.POST.get("token", "")
        if verify_totp(secret, token):
            codes = generate_recovery_codes()
            enable_mfa_for_user(user, secret, codes)
            mark_mfa_verified(request)
            request.session.pop(SESSION_MFA_ENROLL_SECRET, None)
            clear_mfa_failures(user, ip)
            log_activity(user, "MFA_ENROLL", ip_address=get_client_ip(request))
            flash_success(request, "Multi-factor authentication is now enabled.")
            response = render(
                request,
                "accounts/mfa_recovery_codes.html",
                {
                    "recovery_codes": codes,
                    "continue_url": post_login_url(user),
                    "trusted_device_days": TRUSTED_DEVICE_DAYS,
                },
            )
            if request.POST.get("remember_device"):
                device_token = create_trusted_device(user, request)
                attach_trusted_device_cookie(response, device_token)
            return response
        record_mfa_failure(user, ip)
        still_ok, lock_msg = mfa_verify_allowed(user, ip)
        if not still_ok:
            error = lock_msg
            return render(
                request,
                "accounts/mfa_enroll.html",
                {
                    "secret": secret,
                    "provisioning_uri": totp_provisioning_uri(user, secret),
                    "qr_data_uri": totp_qr_data_uri(user, secret),
                    "error": error,
                    "trusted_device_days": TRUSTED_DEVICE_DAYS,
                },
                status=429,
            )
        error = (
            "Invalid authenticator code. Use the code for the QR currently on this "
            "page (do not use an older entry). Check the server clock if it keeps failing."
        )

    return render(
        request,
        "accounts/mfa_enroll.html",
        {
            "secret": secret,
            "provisioning_uri": totp_provisioning_uri(user, secret),
            "qr_data_uri": totp_qr_data_uri(user, secret),
            "error": error,
            "trusted_device_days": TRUSTED_DEVICE_DAYS,
        },
    )


@require_http_methods(["GET", "POST"])
def mfa_verify(request):
    if mfa_pending_expired(request):
        clear_mfa_session(request)
        return redirect("login")
    user = _challenge_user(request)
    if user is None:
        return redirect("login")
    if not user_requires_mfa(user):
        if request.user.is_authenticated:
            mark_mfa_verified(request)
            return redirect(post_login_url(user))
        return redirect("login")
    if not user.mfa_enabled:
        if request.user.is_authenticated:
            return redirect("accounts:mfa_enroll")
        return redirect("login")

    # Trusted device may skip the challenge entirely
    if request_has_trusted_device(request, user):
        flash_success(request, "Signed in on a trusted device.")
        return _complete_mfa_login(request, user, method="trusted", remember_device=False)

    error = ""
    info = ""
    status = 200
    if request.method == "POST":
        ip = get_client_ip(request)
        allowed, lock_msg = mfa_verify_allowed(user, ip)
        if not allowed:
            error = lock_msg
            status = 429
        else:
            action = request.POST.get("action") or "verify"
            if action == "send_email":
                ok, message = send_mfa_email_otp(user, fail_silently=True)
                if ok:
                    info = message
                else:
                    error = message
            else:
                token = request.POST.get("token", "")
                ok, method = verify_user_mfa(user, token)
                if ok:
                    remember = bool(request.POST.get("remember_device"))
                    clear_mfa_failures(user, ip)
                    flash_success(request, "Signed in with multi-factor authentication.")
                    return _complete_mfa_login(
                        request, user, method=method, remember_device=remember
                    )
                record_mfa_failure(user, ip)
                still_ok, _ = mfa_verify_allowed(user, ip)
                if not still_ok:
                    error = "Too many attempts. Try again later."
                    status = 429
                else:
                    error = "Invalid code. Use your authenticator app, email code, or a recovery code."

    return render(
        request,
        "accounts/mfa_verify.html",
        {
            "error": error,
            "info": info,
            "username": user.get_username(),
            "email_masked": _mask_email(user.email) if user_can_receive_email_otp(user) else "",
            "can_email_otp": user_can_receive_email_otp(user),
            "trusted_device_days": TRUSTED_DEVICE_DAYS,
        },
        status=status,
    )


@require_POST
def mfa_send_email(request):
    """Dedicated POST for sending email OTP (same as verify action=send_email)."""
    user = _challenge_user(request)
    if user is None:
        return redirect("login")
    ip = get_client_ip(request)
    allowed, lock_msg = mfa_verify_allowed(user, ip)
    if not allowed:
        flash_error(request, lock_msg)
        return redirect("accounts:mfa_verify")
    ok, message = send_mfa_email_otp(user, fail_silently=True)
    if ok:
        flash_success(request, message)
    else:
        flash_error(request, message)
    return redirect("accounts:mfa_verify")


def _mask_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "*" * min(4, len(local) - 2)
    return f"{masked_local}@{domain}"
