"""Platform email delivery using SiteSettings SMTP configuration."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.urls import reverse

from sitecontrol.services import get_site_settings

logger = logging.getLogger("churchhub.email")


class EmailNotConfiguredError(RuntimeError):
    pass


def smtp_configured() -> bool:
    site = get_site_settings()
    return bool(site.smtp_host and site.default_from_email)


def get_platform_connection():
    """Return a mail connection from platform SMTP settings, or None."""
    from sitecontrol.crypto import resolve_smtp_password

    site = get_site_settings()
    if not site.smtp_host:
        return None
    return get_connection(
        host=site.smtp_host,
        port=site.smtp_port,
        username=site.smtp_username or None,
        password=resolve_smtp_password(site) or None,
        use_tls=site.smtp_use_tls,
        fail_silently=False,
    )


def send_platform_email(*, subject, to, text_body, html_body=None, fail_silently=False):
    """
    Send email via platform SMTP.
    Returns True if sent, False if SMTP not configured (unless fail_silently).
    """
    site = get_site_settings()
    connection = get_platform_connection()
    if not connection:
        if fail_silently:
            logger.info("SMTP not configured; skipped email to %s", to)
            return False
        raise EmailNotConfiguredError(
            "SMTP is not configured. Set host and default from-address in Platform → Email settings."
        )

    from_email = site.default_from_email or site.support_email
    if not from_email:
        if fail_silently:
            return False
        raise EmailNotConfiguredError("default_from_email is not set in platform email settings.")

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[to] if isinstance(to, str) else list(to),
        connection=connection,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    message.send()
    logger.info("Email sent to %s subject=%s", to, subject)
    return True


def build_absolute_uri(request, path):
    if request:
        return request.build_absolute_uri(path)
    base = getattr(settings, "CHURCHHUB_PUBLIC_URL", "").rstrip("/")
    if base:
        return f"{base}{path}"
    return path


def send_user_invitation_email(invitation, request=None, *, fail_silently=True):
    """Email invitation link to a new institution user."""
    accept_path = reverse("accounts:accept_invite", kwargs={"token": invitation.token})
    accept_url = build_absolute_uri(request, accept_path)
    site = get_site_settings()
    context = {
        "invitation": invitation,
        "accept_url": accept_url,
        "site_name": site.site_name,
        "church_name": invitation.church.name,
        "invited_by": invitation.invited_by.get_full_name() or invitation.invited_by.username,
        "expires_at": invitation.expires_at,
    }
    subject = f"You're invited to {site.site_name} — {invitation.church.name}"
    text_body = render_to_string("emails/user_invitation.txt", context)
    html_body = render_to_string("emails/user_invitation.html", context)
    return send_platform_email(
        subject=subject,
        to=invitation.email,
        text_body=text_body,
        html_body=html_body,
        fail_silently=fail_silently,
    )
