"""Production settings — strict validation and HTTPS-aware hardening."""

import os

from django.core.exceptions import ImproperlyConfigured

from church_system.env import env_flag, validate_production_environment
from church_system.settings.base import *  # noqa: F401,F403
from church_system.settings.base import (
    ALLOWED_HOSTS,
    CHURCHHUB_PUBLIC_URL,
    CSRF_TRUSTED_ORIGINS,
    DEBUG,
    HEALTH_CHECK_TOKEN,
    ON_PYTHONANYWHERE,
    REDIS_URL,
    SECRET_KEY,
    _INSECURE_SECRET,
    configure_databases,
)

DJANGO_ENV = "production"

# Prefer MFA for /platform/; empty Site Settings allowlist is OK.
# Set CHURCHHUB_REQUIRE_PLATFORM_IP_ALLOWLIST=true when you have a static/VPN IP list.
REQUIRE_PLATFORM_IP_ALLOWLIST = env_flag("CHURCHHUB_REQUIRE_PLATFORM_IP_ALLOWLIST", False)

if DEBUG:
    raise ImproperlyConfigured(
        "Production settings require DEBUG=False. Set DJANGO_DEBUG=False."
    )

if SECRET_KEY == _INSECURE_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value in production."
    )

# HTTPS enforcement is env-controlled so IP-only HTTP (pre-domain) can work.
# When a domain + TLS are live: leave SECURE_SSL_REDIRECT=true (default).
SECURE_SSL_REDIRECT = env_flag("SECURE_SSL_REDIRECT", True)
_https_mode = bool(SECURE_SSL_REDIRECT)

SESSION_COOKIE_SECURE = _https_mode
CSRF_COOKIE_SECURE = _https_mode
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Django default — JS rarely needs CSRF cookie
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# HSTS only when serving HTTPS; never send HSTS on plain HTTP IP access.
SECURE_HSTS_SECONDS = 31536000 if _https_mode else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _https_mode
SECURE_HSTS_PRELOAD = (
    _https_mode
    and os.environ.get("SECURE_HSTS_PRELOAD", "false").lower() in ("true", "1", "yes")
)

# Trust Nginx / TLS terminator for scheme and host.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Clickjacking / XSS-related headers (also set in base).
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Pure-Python MySQL driver for PythonAnywhere (mysqlclient often unavailable).
if ON_PYTHONANYWHERE:
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:
        pass

DATABASES = configure_databases(require_managed=not ON_PYTHONANYWHERE)

# PythonAnywhere free/hacker plans usually have no Redis; allow LocMem there.
# Ubuntu VPS / multi-worker Gunicorn MUST set REDIS_URL (session OTP + rate limits).
_require_redis = not ON_PYTHONANYWHERE
if env_flag("CHURCHHUB_REQUIRE_REDIS", None) is not None:
    _require_redis = bool(env_flag("CHURCHHUB_REQUIRE_REDIS", True))
REQUIRE_REDIS = _require_redis

_allow_sqlite = ON_PYTHONANYWHERE
if env_flag("CHURCHHUB_ALLOW_SQLITE", None) is not None:
    _allow_sqlite = bool(env_flag("CHURCHHUB_ALLOW_SQLITE", False)) and ON_PYTHONANYWHERE

# After auto-correct, ensure we never validate an empty/invalid PA marketing URL.
_public_url = (CHURCHHUB_PUBLIC_URL or "").strip()
if ON_PYTHONANYWHERE:
    from church_system.public_urls import (
        is_invalid_pythonanywhere_host,
        resolve_pythonanywhere_public_url,
    )
    from urllib.parse import urlparse

    _host = (urlparse(_public_url).hostname or "").lower()
    if not _public_url or is_invalid_pythonanywhere_host(_host):
        _public_url = resolve_pythonanywhere_public_url(_public_url) or (
            "https://churchhub.pythonanywhere.com"
        )
        CHURCHHUB_PUBLIC_URL = _public_url

validate_production_environment(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    database_engine=DATABASES["default"]["ENGINE"],
    redis_url=REDIS_URL,
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
    public_site_url=CHURCHHUB_PUBLIC_URL,
    require_redis=_require_redis,
    allow_mysql=True,
    allow_sqlite=_allow_sqlite,
    health_check_token=HEALTH_CHECK_TOKEN,
    # PA free tier often omits this; empty token keeps /health/ open (acceptable there).
    require_health_token=not ON_PYTHONANYWHERE,
)

# File logs on by default in production
from church_system.logging_config import build_logging_config  # noqa: E402
from church_system.settings.base import LOG_DIR  # noqa: E402

LOGGING = build_logging_config(debug=False, log_dir=LOG_DIR, enable_file_logs=True)
