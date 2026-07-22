"""Production settings — strict validation and HTTPS hardening."""

import os

from django.core.exceptions import ImproperlyConfigured

from church_system.env import validate_production_environment
from church_system.settings.base import *  # noqa: F401,F403
from church_system.settings.base import (
    ALLOWED_HOSTS,
    CSRF_TRUSTED_ORIGINS,
    DEBUG,
    REDIS_URL,
    SECRET_KEY,
    _INSECURE_SECRET,
    configure_databases,
)

DJANGO_ENV = "production"

if DEBUG:
    raise ImproperlyConfigured(
        "Production settings require DEBUG=False. Set DJANGO_DEBUG=False."
    )

if SECRET_KEY == _INSECURE_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value in production."
    )

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in (
    "true",
    "1",
    "yes",
)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = os.environ.get("SECURE_HSTS_PRELOAD", "false").lower() in (
    "true",
    "1",
    "yes",
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATABASES = configure_databases(require_postgres=True)

validate_production_environment(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    database_engine=DATABASES["default"]["ENGINE"],
    redis_url=REDIS_URL,
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
    require_redis=True,
)

# File logs on by default in production
from church_system.logging_config import build_logging_config  # noqa: E402
from church_system.settings.base import LOG_DIR  # noqa: E402

LOGGING = build_logging_config(debug=False, log_dir=LOG_DIR, enable_file_logs=True)
