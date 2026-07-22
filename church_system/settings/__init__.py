"""
Django settings package.

Select environment via DJANGO_ENV / CHURCHHUB_ENV:
  development (default) | staging | production

DJANGO_SETTINGS_MODULE may be:
  church_system.settings                 → auto-select via DJANGO_ENV
  church_system.settings.development
  church_system.settings.staging
  church_system.settings.production
"""

from church_system.env import resolve_django_env

_env = resolve_django_env()

if _env == "production":
    from church_system.settings.production import *  # noqa: F401,F403
elif _env == "staging":
    from church_system.settings.staging import *  # noqa: F401,F403
else:
    from church_system.settings.development import *  # noqa: F401,F403
