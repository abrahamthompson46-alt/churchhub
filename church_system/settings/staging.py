"""Staging settings — production-like with slightly relaxed hardening."""

from django.core.exceptions import ImproperlyConfigured

from church_system.env import validate_production_environment
from church_system.settings.base import *  # noqa: F401,F403
from church_system.settings.base import (
    ALLOWED_HOSTS,
    CSRF_TRUSTED_ORIGINS,
    DATABASES,
    DEBUG,
    REDIS_URL,
    SECRET_KEY,
    _INSECURE_SECRET,
    configure_databases,
)
import os

DJANGO_ENV = "staging"

if not DEBUG and SECRET_KEY == _INSECURE_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG is False."
    )

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in (
        "true",
        "1",
        "yes",
    )
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if os.environ.get("CHURCHHUB_ALLOW_SQLITE", "").lower() not in ("true", "1", "yes"):
    DATABASES = configure_databases(require_postgres=True)

validate_production_environment(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    database_engine=DATABASES["default"]["ENGINE"],
    redis_url=REDIS_URL,
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
    require_redis=os.environ.get("CHURCHHUB_REQUIRE_REDIS", "true").lower()
    in ("true", "1", "yes"),
)
