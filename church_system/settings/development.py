"""Local development settings."""

import os

from django.core.exceptions import ImproperlyConfigured

from church_system.settings.base import *  # noqa: F401,F403
from church_system.settings.base import DEBUG, SECRET_KEY, _INSECURE_SECRET

DJANGO_ENV = "development"

# Allow insecure secret locally; still refuse insecure when DEBUG forced False.
if not DEBUG and SECRET_KEY == _INSECURE_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG is False."
    )

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

# Eager Celery in development unless Redis worker is intended
if not os.environ.get("CELERY_TASK_ALWAYS_EAGER") and not os.environ.get("REDIS_URL"):
    CELERY_TASK_ALWAYS_EAGER = True
