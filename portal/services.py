"""Member portal authentication — email + date-of-birth credentials."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.mfa import (
    attach_trusted_device_cookie,
    create_trusted_device,
    request_has_trusted_device,
)
from accounts.services import get_client_ip, log_activity
from church_system.email_service import send_platform_email
from members.models import Member
from permissions.roles import UserRole

logger = logging.getLogger(__name__)

User = get_user_model()

PORTAL_CONFIRM_SALT = "churchhub.portal.device-confirm"
PORTAL_CONFIRM_MAX_AGE = 60 * 60 * 24  # 24 hours
PORTAL_DOB_PASSWORD_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
    "%d%m%Y",
)


class PortalAuthError(Exception):
    """Raised when portal credentials cannot be verified."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def parse_dob_password(raw: str) -> Optional[date]:
    """Parse a password string as a date of birth when it looks like one."""
    value = (raw or "").strip()
    if not value:
        return None
    for fmt in PORTAL_DOB_PASSWORD_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        for fmt in ("%Y%m%d", "%d%m%Y"):
            try:
                return datetime.strptime(digits, fmt).date()
            except ValueError:
                continue
    return None


def canonical_dob_password(dob: date) -> str:
    """Canonical first-login password derived from date of birth (ISO)."""
    return dob.isoformat()


def member_matches_dob(member: Member, password: str) -> bool:
    if not member.date_of_birth:
        return False
    parsed = parse_dob_password(password)
    if parsed and parsed == member.date_of_birth:
        return True
    return password.strip() == canonical_dob_password(member.date_of_birth)


def find_member_by_email(email: str) -> Optional[Member]:
    email = normalize_email(email)
    if not email:
        return None
    matches = list(
        Member.objects.filter(email__iexact=email, is_active=True)
        .select_related("church")
        .order_by("created_at")[:3]
    )
    if not matches:
        return None
    if len(matches) > 1:
        raise PortalAuthError(
            "More than one member record uses this email. Contact your church office."
        )
    return matches[0]


def find_portal_user_for_email(email: str):
    email = normalize_email(email)
    if not email:
        return None
    return (
        User.objects.filter(is_active=True, is_platform_user=False, role=UserRole.MEMBER)
        .filter(Q(username__iexact=email) | Q(email__iexact=email))
        .select_related("member", "church")
        .first()
    )


def _linked_user(member: Member):
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return member.user_account
    except ObjectDoesNotExist:
        return None


@transaction.atomic
def provision_portal_user(member: Member) -> User:
    """Create or repair a MEMBER user linked to this member record."""
    email = normalize_email(member.email)
    if not email:
        raise PortalAuthError("Your member record has no email address.")
    if not member.date_of_birth:
        raise PortalAuthError(
            "Your member record has no date of birth. Contact your church office."
        )

    existing = _linked_user(member)
    if existing is not None:
        user = existing
        updates = []
        if user.username.lower() != email:
            if not User.objects.filter(username__iexact=email).exclude(pk=user.pk).exists():
                user.username = email
                updates.append("username")
        if (user.email or "").lower() != email:
            user.email = email
            updates.append("email")
        if user.role != UserRole.MEMBER:
            user.role = UserRole.MEMBER
            updates.append("role")
        if user.church_id != member.church_id:
            user.church_id = member.church_id
            updates.append("church_id")
        if updates:
            user.save(update_fields=updates)
        return user

    user = find_portal_user_for_email(email)
    if user:
        if user.member_id and user.member_id != member.pk:
            raise PortalAuthError(
                "This email is already linked to another portal account. "
                "Contact your church office."
            )
        user.member = member
        user.church = member.church
        user.email = email
        if user.username.lower() != email and not User.objects.filter(
            username__iexact=email
        ).exclude(pk=user.pk).exists():
            user.username = email
        user.save()
        return user

    if User.objects.filter(username__iexact=email).exists():
        raise PortalAuthError(
            "This email is already used by another account. Contact your church office."
        )

    password = canonical_dob_password(member.date_of_birth)
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        role=UserRole.MEMBER,
        church=member.church,
        member=member,
        first_name=member.first_name or "",
        last_name=member.last_name or "",
        must_change_password=True,
    )
    log_activity(user, "PORTAL_ACCOUNT_PROVISIONED")
    return user


def authenticate_portal_credentials(email: str, password: str) -> User:
    """
    Verify portal credentials.

    Accepts an existing MEMBER password, or date of birth matching the Member
    record (first-time / default password). Email must match the directory.
    """
    email = normalize_email(email)
    password = (password or "").strip()
    if not email or not password:
        raise PortalAuthError("Enter your email and password.")

    member = find_member_by_email(email)
    if member is None:
        raise PortalAuthError("No active member was found for that email.")

    user = _linked_user(member) or find_portal_user_for_email(email)

    if user is not None and user.check_password(password):
        if user.member_id and user.member_id != member.pk:
            raise PortalAuthError("Account link mismatch. Contact your church office.")
        if not user.member_id:
            user.member = member
            user.church = member.church
            user.save(update_fields=["member", "church"])
        return user

    if not member_matches_dob(member, password):
        raise PortalAuthError(
            "Email and date of birth do not match our records. "
            "For first sign-in use your member email and date of birth as YYYY-MM-DD."
        )

    user = provision_portal_user(member)
    if user.check_password(password) or user.check_password(
        canonical_dob_password(member.date_of_birth)
    ):
        return user

    if not user.must_change_password and user.last_login is not None:
        raise PortalAuthError(
            "Use the password you set for the portal, or reset it from the sign-in page."
        )

    user.set_password(canonical_dob_password(member.date_of_birth))
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    return user


def portal_needs_device_confirmation(request, user) -> bool:
    """First login or unrecognized browser requires email confirmation."""
    if user.last_login is None:
        return True
    return not request_has_trusted_device(request, user)


def build_confirm_token(user) -> str:
    signer = signing.TimestampSigner(salt=PORTAL_CONFIRM_SALT)
    return signer.sign(str(user.pk))


def resolve_confirm_token(token: str):
    signer = signing.TimestampSigner(salt=PORTAL_CONFIRM_SALT)
    try:
        user_id = signer.unsign(token, max_age=PORTAL_CONFIRM_MAX_AGE)
    except signing.BadSignature as exc:
        raise PortalAuthError("This confirmation link is invalid or has expired.") from exc
    user = User.objects.filter(pk=user_id, is_active=True, role=UserRole.MEMBER).first()
    if not user:
        raise PortalAuthError("This confirmation link is invalid or has expired.")
    return user


def public_absolute_url(request, path: str) -> str:
    from church_system.public_urls import build_public_absolute_uri

    return build_public_absolute_uri(request, path)


def send_portal_device_confirmation(request, user) -> bool:
    """Email a one-time confirmation link for first login / new device."""
    email = normalize_email(user.email or getattr(user.member, "email", ""))
    if not email:
        raise PortalAuthError("No email address is available to send a confirmation link.")

    token = build_confirm_token(user)
    from urllib.parse import quote

    confirm_path = reverse("portal:confirm_device") + "?token=" + quote(token, safe="")
    confirm_url = public_absolute_url(request, confirm_path)
    from church_system.email_service import get_email_branding_context

    context = {
        **get_email_branding_context(
            request,
            preheader="Confirm your member portal sign-in",
        ),
        "user": user,
        "member": getattr(user, "member", None),
        "confirm_url": confirm_url,
        "expires_hours": PORTAL_CONFIRM_MAX_AGE // 3600,
        "device_hint": (request.META.get("HTTP_USER_AGENT") or "")[:120],
        "ip_address": get_client_ip(request),
    }
    site_name = context["site_name"]
    text_body = render_to_string("emails/portal_device_confirm.txt", context)
    html_body = render_to_string("emails/portal_device_confirm.html", context)
    sent = send_platform_email(
        subject=f"[{site_name}] Confirm your member portal sign-in",
        to=email,
        text_body=text_body,
        html_body=html_body,
        fail_silently=True,
    )
    if not sent and getattr(settings, "DEBUG", False):
        logger.warning("Portal confirm email skipped (SMTP); link=%s", confirm_url)
        request.session["portal_dev_confirm_url"] = confirm_url
        request.session.modified = True
        return True
    if not sent:
        raise PortalAuthError(
            "We could not send a confirmation email. Contact your church office or try again later."
        )
    log_activity(
        user,
        "PORTAL_DEVICE_CONFIRM_SENT",
        ip_address=get_client_ip(request),
        details=f"to={email}",
    )
    return True


def complete_portal_login(request, user, *, trust_device: bool = True):
    """Create session + optional trusted device; return cookie token if any."""
    from django.contrib.auth import login

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    token = None
    if trust_device:
        token = create_trusted_device(user, request)
    log_activity(user, "PORTAL_LOGIN", ip_address=get_client_ip(request))
    return token


def apply_trusted_device_cookie(response, token: str | None):
    if token:
        attach_trusted_device_cookie(response, token)
    return response


def password_is_still_dob(user) -> bool:
    member = getattr(user, "member", None)
    if not member or not member.date_of_birth:
        return False
    return user.check_password(canonical_dob_password(member.date_of_birth))
