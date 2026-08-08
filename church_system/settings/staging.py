"""Staging settings — production-like with slightly relaxed hardening."""

from django.core.exceptions import ImproperlyConfigured

from church_system.env import env_flag, validate_production_environment
from church_system.settings.base import *  # noqa: F401,F403
from church_system.settings.base import (
    ALLOWED_HOSTS,
    CHURCHHUB_PUBLIC_URL,
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
    # Match production: Secure cookies / HSTS follow SECURE_SSL_REDIRECT so HTTP
    # staging does not set Secure cookies that the browser will refuse to send.
    SECURE_SSL_REDIRECT = bool(env_flag("SECURE_SSL_REDIRECT", True))
    _https_mode = SECURE_SSL_REDIRECT
    SESSION_COOKIE_SECURE = _https_mode
    CSRF_COOKIE_SECURE = _https_mode
    SECURE_HSTS_SECONDS = 3600 if _https_mode else 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _https_mode
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    TRUST_X_FORWARDED_FOR = env_flag("CHURCHHUB_TRUST_X_FORWARDED_FOR", True)

if os.environ.get("CHURCHHUB_ALLOW_SQLITE", "").lower() not in ("true", "1", "yes"):
    DATABASES = configure_databases(require_managed=True)

validate_production_environment(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    database_engine=DATABASES["default"]["ENGINE"],
    redis_url=REDIS_URL,
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
    public_site_url=CHURCHHUB_PUBLIC_URL,
    require_redis=os.environ.get("CHURCHHUB_REQUIRE_REDIS", "true").lower()
    in ("true", "1", "yes"),
    allow_mysql=True,
)

REQUIRE_REDIS = os.environ.get("CHURCHHUB_REQUIRE_REDIS", "true").lower() in (
    "true",
    "1",
    "yes",
)
