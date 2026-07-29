"""Platform email delivery using SiteSettings SMTP (with env fallback)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.urls import reverse

from sitecontrol.services import get_site_settings

logger = logging.getLogger("churchhub.email")


class EmailNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    use_ssl: bool
    from_email: str
    source: str  # "site" | "env"


def _env(name: str, default: str = "") -> str:
    import os

    return (os.environ.get(name) or default).strip()


def resolve_smtp_config() -> SmtpConfig | None:
    """
    Resolve outbound SMTP settings.
    Prefer Platform → Email (SiteSettings), then Django/env EMAIL_* fallback.
    """
    from sitecontrol.crypto import resolve_smtp_password

    site = get_site_settings()
    host = (site.smtp_host or "").strip()
    from_email = (site.default_from_email or site.support_email or "").strip()
    if host and from_email:
        port = int(site.smtp_port or 587)
        use_tls = bool(site.smtp_use_tls)
        use_ssl = port == 465 and not use_tls
        if port == 465:
            # Implicit SSL on 465; STARTTLS is for 587.
            use_ssl = True
            use_tls = False
        return SmtpConfig(
            host=host,
            port=port,
            username=(site.smtp_username or "").strip(),
            password=resolve_smtp_password(site) or "",
            use_tls=use_tls,
            use_ssl=use_ssl,
            from_email=from_email,
            source="site",
        )

    host = _env("EMAIL_HOST") or (getattr(settings, "EMAIL_HOST", "") or "").strip()
    from_email = (
        _env("DEFAULT_FROM_EMAIL")
        or _env("EMAIL_FROM")
        or (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    )
    if not host or not from_email:
        return None

    port = int(_env("EMAIL_PORT") or getattr(settings, "EMAIL_PORT", 587) or 587)
    use_tls = _env("EMAIL_USE_TLS", "true" if port == 587 else "false").lower() in (
        "1",
        "true",
        "yes",
    )
    use_ssl = _env("EMAIL_USE_SSL", "true" if port == 465 else "false").lower() in (
        "1",
        "true",
        "yes",
    )
    if port == 465:
        use_ssl = True
        use_tls = False
    elif use_ssl and use_tls:
        use_tls = False

    return SmtpConfig(
        host=host,
        port=port,
        username=_env("EMAIL_HOST_USER") or (getattr(settings, "EMAIL_HOST_USER", "") or ""),
        password=_env("EMAIL_HOST_PASSWORD") or (getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""),
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_email=from_email,
        source="env",
    )


def smtp_configured() -> bool:
    return resolve_smtp_config() is not None


def smtp_status() -> dict:
    """UI-friendly SMTP readiness summary (no secrets)."""
    cfg = resolve_smtp_config()
    if not cfg:
        return {
            "configured": False,
            "source": None,
            "host": "",
            "port": None,
            "from_email": "",
            "username_set": False,
            "password_set": False,
            "use_tls": None,
            "use_ssl": None,
            "message": "SMTP is not configured. Set host and from-address in Platform → Email, or EMAIL_* env vars.",
        }
    return {
        "configured": True,
        "source": cfg.source,
        "host": cfg.host,
        "port": cfg.port,
        "from_email": cfg.from_email,
        "username_set": bool(cfg.username),
        "password_set": bool(cfg.password),
        "use_tls": cfg.use_tls,
        "use_ssl": cfg.use_ssl,
        "message": f"Ready via {cfg.source} ({cfg.host}:{cfg.port}).",
    }


def get_platform_connection():
    """Return a real SMTP connection from resolved settings, or None."""
    cfg = resolve_smtp_config()
    if not cfg:
        return None
    # Always use Django's SMTP backend — never EMAIL_BACKEND — to avoid recursion
    # when EMAIL_BACKEND is PlatformSMTPEmailBackend.
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=cfg.host,
        port=cfg.port,
        username=cfg.username or None,
        password=cfg.password or None,
        use_tls=cfg.use_tls,
        use_ssl=cfg.use_ssl,
        fail_silently=False,
    )


def send_platform_email(*, subject, to, text_body, html_body=None, fail_silently=False):
    """
    Send email via platform SMTP.
    Returns True if sent, False if SMTP not configured (when fail_silently).
    """
    cfg = resolve_smtp_config()
    connection = get_platform_connection()
    if not connection or not cfg:
        if fail_silently:
            logger.warning("SMTP not configured; skipped email to %s", to)
            return False
        raise EmailNotConfiguredError(
            "SMTP is not configured. Set host and default from-address in Platform → Email "
            "(or EMAIL_HOST / DEFAULT_FROM_EMAIL in the environment)."
        )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=cfg.from_email,
        to=[to] if isinstance(to, str) else list(to),
        connection=connection,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    try:
        message.send()
    except Exception:
        logger.exception("Failed to send email to %s subject=%s", to, subject)
        if fail_silently:
            return False
        raise
    logger.info("Email sent to %s subject=%s", to, subject)
    return True


def send_test_email(recipient: str) -> bool:
    """Send a short connectivity test using the resolved SMTP config."""
    from django.template.loader import render_to_string

    context = get_email_branding_context(
        None,
        preheader="ChurchHub SMTP test",
    )
    html_body = render_to_string("emails/test_email.html", context)
    return send_platform_email(
        subject=f"[{context['site_name']}] Email test",
        to=recipient,
        text_body=(
            f"{context['site_name']} email test succeeded.\n\n"
            "Invitations, portal sign-in, and password resets can use this SMTP connection."
        ),
        html_body=html_body,
        fail_silently=False,
    )


def build_absolute_uri(request, path):
    from church_system.public_urls import build_public_absolute_uri

    return build_public_absolute_uri(request, path)


def get_email_branding_context(request=None, *, preheader: str = "") -> dict:
    """Shared template context for HTML emails (platform SiteSettings + public URLs)."""
    from church_system.public_urls import resolve_public_site_base

    site = get_site_settings()
    base = resolve_public_site_base(request).rstrip("/")
    logo_url = ""
    if site.logo:
        logo_path = site.logo.url
        if logo_path.startswith(("http://", "https://")):
            logo_url = logo_path
        else:
            logo_url = f"{base}{logo_path if logo_path.startswith('/') else '/' + logo_path}"

    return {
        "site_name": site.site_name,
        "site_tagline": (site.site_tagline or "").strip(),
        "brand_color": site.admin_primary_color or "#1e3a5f",
        "action_color": site.accent_color or "#1d4ed8",
        "site_url": base,
        "logo_url": logo_url,
        "support_email": (site.support_email or "").strip(),
        "footer_text": (site.footer_text or "").strip(),
        "email_preheader": (preheader or "").strip(),
    }


def send_user_invitation_email(invitation, request=None, *, fail_silently=True):
    """Email invitation link to a new institution user."""
    accept_path = reverse("accounts:accept_invite", kwargs={"token": invitation.token})
    accept_url = build_absolute_uri(request, accept_path)
    site = get_site_settings()
    context = {
        **get_email_branding_context(
            request,
            preheader=f"Accept your invitation to {invitation.church.name}",
        ),
        "invitation": invitation,
        "accept_url": accept_url,
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
