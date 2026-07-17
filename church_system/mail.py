"""Django email backends that honour Platform SMTP settings."""

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class PlatformSMTPEmailBackend(BaseEmailBackend):
    """
    Route Django mail (password reset, etc.) through SiteSettings / EMAIL_* SMTP.
    Falls back to the console backend in DEBUG when SMTP is not configured.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        from church_system.email_service import (
            EmailNotConfiguredError,
            get_platform_connection,
            resolve_smtp_config,
        )

        cfg = resolve_smtp_config()
        if not cfg:
            if settings.DEBUG:
                from django.core.mail.backends.console import EmailBackend as ConsoleBackend

                return ConsoleBackend(fail_silently=self.fail_silently).send_messages(email_messages)
            if self.fail_silently:
                return 0
            raise EmailNotConfiguredError(
                "SMTP is not configured. Set Platform → Email or EMAIL_HOST / DEFAULT_FROM_EMAIL."
            )

        connection = get_platform_connection()
        if not connection:
            if self.fail_silently:
                return 0
            raise EmailNotConfiguredError("SMTP connection could not be created.")

        # Ensure From is set when callers omit it
        for message in email_messages:
            if not message.from_email:
                message.from_email = cfg.from_email

        try:
            return connection.send_messages(email_messages)
        except Exception:
            if not self.fail_silently:
                raise
            return 0
