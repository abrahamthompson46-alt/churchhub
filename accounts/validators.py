"""Password validators driven by platform SiteSettings."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def _platform_password_rules():
    from sitecontrol.services import get_site_settings

    site = get_site_settings()
    return site.password_min_length, site.password_require_uppercase


class PlatformMinimumLengthValidator:
    def validate(self, password, user=None):
        min_length, _require_upper = _platform_password_rules()
        if len(password) < min_length:
            raise ValidationError(
                _("Password must be at least %(min_length)d characters."),
                code="password_too_short",
                params={"min_length": min_length},
            )

    def get_help_text(self):
        min_length, _require_upper = _platform_password_rules()
        return _(f"Your password must contain at least {min_length} characters.")


class PlatformUppercaseValidator:
    def validate(self, password, user=None):
        _, require_upper = _platform_password_rules()
        if require_upper and not re.search(r"[A-Z]", password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter."),
                code="password_no_upper",
            )

    def get_help_text(self):
        return _("Your password must contain at least one uppercase letter.")
