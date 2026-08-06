"""
Django settings package.

Select environment via DJANGO_ENV / CHURCHHUB_ENV:
  development (default) | staging | production

DJANGO_SETTINGS_MODULE may be:
  church_system.settings                 → auto-select via DJANGO_ENV
  church_system.settings.development
  church_system.settings.staging
  church_system.settings.production

``.env`` is loaded here *before* env resolution so interactive manage.py,
Gunicorn, and Celery all see the same DJANGO_ENV when it is only set in `.env`.
Process environment variables always win over `.env` values.
"""

from church_system.env import ensure_dotenv_loaded, resolve_django_env

ensure_dotenv_loaded()

_env = resolve_django_env()

if _env == "production":
    from church_system.settings.production import *  # noqa: F401,F403
elif _env == "staging":
    from church_system.settings.staging import *  # noqa: F401,F403
else:
    from church_system.settings.development import *  # noqa: F401,F403
