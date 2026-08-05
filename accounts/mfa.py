"""TOTP MFA helpers for ChurchHub accounts.

Enforcement is optional and configured by platform owners in Site Settings
(Security Policy): master toggle + which institution/platform roles (and
optionally Django superusers) must enroll and verify.

Also supports:
- Email OTP as an alternate challenge channel
- Trusted devices that skip MFA for a limited period (default 30 days)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from permissions.roles import UserRole

User = get_user_model()

SESSION_MFA_VERIFIED = "mfa_verified"
SESSION_MFA_PENDING_USER = "mfa_pending_user_id"
SESSION_MFA_PENDING_BACKEND = "mfa_pending_backend"
SESSION_MFA_ENROLL_SECRET = "mfa_enroll_secret"

# Recommended defaults when owners enable MFA without customizing audiences.
MFA_DEFAULT_PLATFORM_ROLES = frozenset({"OWNER", "SECURITY"})
MFA_DEFAULT_INSTITUTION_ROLES = frozenset({UserRole.SUPER_ADMIN, UserRole.TREASURY})
# Backward-compatible aliases
MFA_PRIVILEGED_PLATFORM_ROLES = MFA_DEFAULT_PLATFORM_ROLES
MFA_PRIVILEGED_INSTITUTION_ROLES = MFA_DEFAULT_INSTITUTION_ROLES
RECOVERY_CODE_COUNT = 10

TRUSTED_DEVICE_COOKIE = "ch_trusted_device"
TRUSTED_DEVICE_DAYS = 30
TRUSTED_DEVICE_MAX_PER_USER = 5

EMAIL_OTP_TTL_SECONDS = 600
EMAIL_OTP_LENGTH = 6
EMAIL_OTP_SEND_LIMIT = 3
EMAIL_OTP_SEND_WINDOW_SECONDS = 900


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_totp_secret(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().replace(" ", "").upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_totp_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def totp_provisioning_uri(user, secret: str) -> str:
    import pyotp

    issuer = "ChurchHub"
    try:
        from sitecontrol.services import get_site_settings

        issuer = get_site_settings().site_name or issuer
    except Exception:
        pass
    return pyotp.TOTP(secret).provisioning_uri(name=user.get_username(), issuer_name=issuer)


def totp_qr_data_uri(user, secret: str) -> str:
    """PNG data URI for authenticator app QR scan during enrollment."""
    import qrcode

    uri = totp_provisioning_uri(user, secret)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp(secret: str, token: str, *, window: int = 2) -> bool:
    """
    Verify a 6-digit TOTP code.

    valid_window=2 tolerates ±60s clock skew (common on VPS without NTP sync).
    """
    import pyotp

    cleaned = (token or "").strip().replace(" ", "")
    if not cleaned.isdigit():
        return False
    return bool(pyotp.TOTP(secret).verify(cleaned, valid_window=window))


def get_user_totp_secret(user) -> str | None:
    if not user.mfa_secret:
        return None
    try:
        return decrypt_totp_secret(user.mfa_secret)
    except Exception:
        # SECRET_KEY rotation or corrupt ciphertext — treat as unenrolled for verify
        return None


def enable_mfa_for_user(user, secret: str, recovery_codes: list[str]) -> None:
    from accounts import repositories as repo

    user.mfa_secret = encrypt_totp_secret(secret)
    user.mfa_recovery_hashes = store_recovery_code_hashes(recovery_codes)
    user.mfa_enabled = True
    repo.save_user(user, update_fields=["mfa_secret", "mfa_recovery_hashes", "mfa_enabled"])


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def store_recovery_code_hashes(codes: Iterable[str]) -> list[str]:
    return [hash_recovery_code(code) for code in codes]


def consume_recovery_code(user, code: str) -> bool:
    """Validate and consume one recovery code. Returns True on success."""
    if not user.mfa_recovery_hashes:
        return False
    target = hash_recovery_code(code)
    remaining = []
    matched = False
    for stored in user.mfa_recovery_hashes:
        if not matched and hmac.compare_digest(stored, target):
            matched = True
            continue
        remaining.append(stored)
    if not matched:
        return False
    user.mfa_recovery_hashes = remaining
    from accounts import repositories as repo

    repo.save_user(user, update_fields=["mfa_recovery_hashes"])
    return True


def _mfa_role_set(raw, fallback: frozenset[str]) -> frozenset[str]:
    """Normalize stored JSON role lists; empty means use recommended defaults."""
    if not raw:
        return fallback
    return frozenset(str(r).strip() for r in raw if str(r).strip())


def get_mfa_audience_policy() -> dict:
    """Return current MFA audience policy from SiteSettings (with defaults)."""
    try:
        from sitecontrol.services import get_site_settings

        cfg = get_site_settings()
        return {
            "enabled": bool(cfg.mfa_required_for_privileged),
            "institution_roles": _mfa_role_set(
                getattr(cfg, "mfa_institution_roles", None),
                MFA_DEFAULT_INSTITUTION_ROLES,
            ),
            "platform_roles": _mfa_role_set(
                getattr(cfg, "mfa_platform_roles", None),
                MFA_DEFAULT_PLATFORM_ROLES,
            ),
            "include_superusers": bool(
                getattr(cfg, "mfa_include_django_superusers", True)
            ),
        }
    except Exception:
        return {
            "enabled": False,
            "institution_roles": MFA_DEFAULT_INSTITUTION_ROLES,
            "platform_roles": MFA_DEFAULT_PLATFORM_ROLES,
            "include_superusers": True,
        }


def mfa_enforcement_enabled() -> bool:
    """Master switch — MFA is optional until platform owners enable it."""
    return bool(get_mfa_audience_policy()["enabled"])


def user_requires_mfa(user) -> bool:
    """Whether this account must complete MFA before using the app."""
    if not user or not getattr(user, "pk", None):
        return False
    policy = get_mfa_audience_policy()
    if not policy["enabled"]:
        return False
    if getattr(user, "is_superuser", False):
        return bool(policy["include_superusers"])
    if getattr(user, "is_platform_user", False):
        role = (getattr(user, "platform_role", "") or "").strip()
        return role in policy["platform_roles"]
    return getattr(user, "role", None) in policy["institution_roles"]


def session_mfa_verified(request) -> bool:
    return bool(request.session.get(SESSION_MFA_VERIFIED))


def mark_mfa_verified(request) -> None:
    request.session[SESSION_MFA_VERIFIED] = True
    request.session.pop(SESSION_MFA_PENDING_USER, None)
    request.session.pop(SESSION_MFA_PENDING_BACKEND, None)
    request.session.pop(SESSION_MFA_ENROLL_SECRET, None)
    request.session.modified = True


def clear_mfa_session(request) -> None:
    for key in (
        SESSION_MFA_VERIFIED,
        SESSION_MFA_PENDING_USER,
        SESSION_MFA_PENDING_BACKEND,
        SESSION_MFA_ENROLL_SECRET,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def verify_user_mfa(user, token: str) -> tuple[bool, str]:
    """
    Verify TOTP, email OTP, or recovery code.
    Returns (ok, method) where method is 'totp' | 'email' | 'recovery' | ''.
    """
    secret = get_user_totp_secret(user)
    if secret and verify_totp(secret, token):
        return True, "totp"
    if verify_email_otp(user, token):
        return True, "email"
    if consume_recovery_code(user, token):
        return True, "recovery"
    return False, ""


# --- Email OTP -----------------------------------------------------------------


def _email_otp_cache_key(user) -> str:
    return f"mfa_email_otp:{user.pk}"


def _email_otp_send_key(user) -> str:
    return f"mfa_email_otp_send:{user.pk}"


def user_can_receive_email_otp(user) -> bool:
    return bool((getattr(user, "email", "") or "").strip())


def email_otp_send_allowed(user) -> tuple[bool, str]:
    if not user_can_receive_email_otp(user):
        return False, "No email address is on file for this account."
    sends = cache.get(_email_otp_send_key(user), 0)
    if sends >= EMAIL_OTP_SEND_LIMIT:
        return False, "Too many email codes sent. Wait a few minutes and try again."
    return True, ""


def issue_email_otp(user) -> str:
    """Create and cache a one-time email code. Returns plaintext code."""
    code = f"{secrets.randbelow(10**EMAIL_OTP_LENGTH):0{EMAIL_OTP_LENGTH}d}"
    cache.set(_email_otp_cache_key(user), hash_recovery_code(code), EMAIL_OTP_TTL_SECONDS)
    send_key = _email_otp_send_key(user)
    sends = cache.get(send_key, 0) + 1
    cache.set(send_key, sends, EMAIL_OTP_SEND_WINDOW_SECONDS)
    return code


def verify_email_otp(user, token: str) -> bool:
    cleaned = (token or "").strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != EMAIL_OTP_LENGTH:
        return False
    stored = cache.get(_email_otp_cache_key(user))
    if not stored:
        return False
    if not hmac.compare_digest(stored, hash_recovery_code(cleaned)):
        return False
    cache.delete(_email_otp_cache_key(user))
    return True


def send_mfa_email_otp(user, *, fail_silently: bool = True) -> tuple[bool, str]:
    """Issue and email an OTP. Returns (ok, message)."""
    allowed, reason = email_otp_send_allowed(user)
    if not allowed:
        return False, reason
    code = issue_email_otp(user)
    try:
        from church_system.email_service import get_email_branding_context, send_platform_email
        from django.template.loader import render_to_string
        from sitecontrol.services import get_site_settings

        site = get_site_settings()
        context = {
            **get_email_branding_context(
                None,
                preheader="Your sign-in verification code",
            ),
            "user": user,
            "code": code,
            "ttl_minutes": EMAIL_OTP_TTL_SECONDS // 60,
        }
        subject = f"[{context['site_name']}] Your sign-in code"
        text_body = render_to_string("emails/mfa_email_otp.txt", context)
        html_body = render_to_string("emails/mfa_email_otp.html", context)
        sent = send_platform_email(
            subject=subject,
            to=user.email,
            text_body=text_body,
            html_body=html_body,
            fail_silently=fail_silently,
        )
        if not sent:
            return False, "Email could not be sent. Check SMTP settings or use your authenticator app."
        return True, f"A code was sent to {user.email}."
    except Exception:
        if fail_silently:
            return False, "Email could not be sent. Use your authenticator app or a recovery code."
        raise


# --- Trusted devices -----------------------------------------------------------


def _device_label(request) -> str:
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:200]
    if not ua:
        return "Browser"
    lower = ua.lower()
    if "edg/" in lower:
        browser = "Edge"
    elif "chrome/" in lower and "chromium" not in lower:
        browser = "Chrome"
    elif "firefox/" in lower:
        browser = "Firefox"
    elif "safari/" in lower:
        browser = "Safari"
    else:
        browser = "Browser"
    if "windows" in lower:
        os_name = "Windows"
    elif "mac os" in lower or "macintosh" in lower:
        os_name = "macOS"
    elif "android" in lower:
        os_name = "Android"
    elif "iphone" in lower or "ipad" in lower:
        os_name = "iOS"
    elif "linux" in lower:
        os_name = "Linux"
    else:
        os_name = "device"
    return f"{browser} on {os_name}"


def create_trusted_device(user, request) -> str:
    """Persist a trusted device and return the raw cookie token."""
    from accounts.models import TrustedDevice
    from accounts.services import get_client_ip

    token = secrets.token_urlsafe(32)
    now = timezone.now()
    TrustedDevice.objects.create(
        user=user,
        token_hash=hash_device_token(token),
        label=_device_label(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
        ip_address=get_client_ip(request),
        expires_at=now + timedelta(days=TRUSTED_DEVICE_DAYS),
        last_used_at=now,
    )
    # Cap devices per user — drop oldest expired/extra
    qs = TrustedDevice.objects.filter(user=user).order_by("-last_used_at")
    keep_ids = list(qs.values_list("pk", flat=True)[:TRUSTED_DEVICE_MAX_PER_USER])
    TrustedDevice.objects.filter(user=user).exclude(pk__in=keep_ids).delete()
    TrustedDevice.objects.filter(user=user, expires_at__lt=now).delete()
    return token


def revoke_all_trusted_devices(user) -> int:
    """Remove every trusted device for the user (password change / security reset)."""
    from accounts.models import TrustedDevice

    deleted, _ = TrustedDevice.objects.filter(user=user).delete()
    return deleted


def find_valid_trusted_device(user, token: str):
    from accounts.models import TrustedDevice

    if not user or not token:
        return None
    return (
        TrustedDevice.objects.filter(
            user=user,
            token_hash=hash_device_token(token),
            expires_at__gt=timezone.now(),
        )
        .order_by("-last_used_at")
        .first()
    )


def request_has_trusted_device(request, user) -> bool:
    token = request.COOKIES.get(TRUSTED_DEVICE_COOKIE, "")
    device = find_valid_trusted_device(user, token)
    if not device:
        return False
    device.last_used_at = timezone.now()
    device.save(update_fields=["last_used_at"])
    return True


def attach_trusted_device_cookie(response, token: str):
    """Set HttpOnly trusted-device cookie on the response."""
    # Align with production SESSION_COOKIE_SECURE (False on transitional HTTP IP access).
    secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", not settings.DEBUG))
    max_age = TRUSTED_DEVICE_DAYS * 24 * 60 * 60
    response.set_cookie(
        TRUSTED_DEVICE_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
    )
    return response
