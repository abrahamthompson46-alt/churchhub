"""Shared Django settings for ChurchHub (all environments)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from church_system.debug_config import is_production_like_env, resolve_debug
from church_system.env import (
    env_flag,
    env_int,
    env_str,
    insecure_secret_default,
    load_dotenv,
)
from church_system.storage import apply_s3_settings, build_storages

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

DJANGO_ENV = env_str("DJANGO_ENV") or env_str("CHURCHHUB_ENV") or "development"

ON_RENDER = bool(os.environ.get("RENDER"))
ON_PYTHONANYWHERE = bool(os.environ.get("PYTHONANYWHERE_SITE"))
PRODUCTION_LIKE = is_production_like_env(
    on_render=ON_RENDER,
    on_pythonanywhere=ON_PYTHONANYWHERE,
)

_INSECURE_SECRET = insecure_secret_default()
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _INSECURE_SECRET)

DEBUG = resolve_debug(production_like=PRODUCTION_LIKE)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,testserver,churchhub.pythonanywhere.com,"
        "www.churchhub.pythonanywhere.com",
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

_RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _RENDER_HOST:
    if _RENDER_HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_RENDER_HOST)
    _render_origin = f"https://{_RENDER_HOST}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

INSTALLED_APPS = [
    "admin_custom",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "church_system.apps.ChurchSystemConfig",
    "accounts",
    "permissions",
    "organization",
    "members",
    "transactions",
    "dashboard",
    "announcements",
    "reports",
    "meetings",
    "budgets",
    "giving",
    "ledger",
    "remittance.apps.RemittanceConfig",
    "payroll.apps.PayrollConfig",
    "assets.apps.AssetsConfig",
    "portal.apps.PortalConfig",
    "sitecontrol.apps.SitecontrolConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "permissions.middleware.PermissionCacheMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.MfaEnforcementMiddleware",
    "permissions.middleware.RoleEnforcementMiddleware",
    "sitecontrol.denomination_middleware.DenominationContextMiddleware",
    "sitecontrol.middleware.UserScopeMiddleware",
    "sitecontrol.middleware.PlatformSessionMiddleware",
    "sitecontrol.middleware.MaintenanceModeMiddleware",
    "sitecontrol.middleware.LoginRateLimitMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "church_system.urls"
WSGI_APPLICATION = "church_system.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.static",
                "church_system.context_processors.church_context",
                "church_system.context_processors.navigation_context",
                "church_system.context_processors.permission_context",
                "church_system.context_processors.platform_context",
                "church_system.context_processors.denomination_context",
                "church_system.context_processors.working_day_context",
            ],
        },
    },
]


def configure_databases(*, require_postgres: bool = False) -> dict:
    """
    Database priority:
    1. DATABASE_URL
    2. Explicit PostgreSQL (DB_ENGINE=postgresql)
    3. SQLite (local only)
    """
    from django.core.exceptions import ImproperlyConfigured

    database_url = os.environ.get("DATABASE_URL", "").strip()
    conn_max_age = env_int("DB_CONN_MAX_AGE", 600)

    if database_url:
        import dj_database_url

        db = dj_database_url.parse(
            database_url,
            conn_max_age=conn_max_age,
            conn_health_checks=True,
        )
        if ON_RENDER or env_flag("DB_SSL_REQUIRE", False):
            db.setdefault("OPTIONS", {}).setdefault("sslmode", "require")
        return {"default": db}

    if os.environ.get("DB_ENGINE") == "postgresql":
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ.get("DB_NAME"),
                "USER": os.environ.get("DB_USER"),
                "PASSWORD": os.environ.get("DB_PASSWORD"),
                "HOST": os.environ.get("DB_HOST"),
                "PORT": os.environ.get("DB_PORT", "5432"),
                "CONN_MAX_AGE": conn_max_age,
                "CONN_HEALTH_CHECKS": True,
            }
        }

    if require_postgres or ON_RENDER:
        raise ImproperlyConfigured(
            "DATABASE_URL (PostgreSQL) must be configured for this environment."
        )

    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


DATABASES = configure_databases(require_postgres=False)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "accounts.validators.PlatformMinimumLengthValidator"},
    {"NAME": "accounts.validators.PlatformUppercaseValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []

MEDIA_URL = "/media/"
_media_root = os.environ.get("MEDIA_ROOT", "").strip()
MEDIA_ROOT = Path(_media_root) if _media_root else BASE_DIR / "media"

STORAGES = build_storages(compressed_static=True)
apply_s3_settings(globals())

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_AGE = 60 * 60 * 4
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
SESSION_REDIS = env_flag("CHURCHHUB_SESSION_REDIS", False)

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": env_str("CACHE_KEY_PREFIX", "churchhub"),
            "TIMEOUT": env_int("CACHE_DEFAULT_TIMEOUT", 300),
        }
    }
    # cached_db: Redis for speed, DB for durability across Redis flushes
    if SESSION_REDIS or env_flag("CHURCHHUB_SESSION_CACHE", True):
        SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
        SESSION_CACHE_ALIAS = "default"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "churchhub-default",
        }
    }

CHURCHHUB_PUBLIC_URL = os.environ.get(
    "CHURCHHUB_PUBLIC_URL",
    f"https://{_RENDER_HOST}" if _RENDER_HOST else "http://localhost:8000",
)

EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587") or 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").strip()
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    os.environ.get("EMAIL_FROM", ""),
).strip()
SERVER_EMAIL = DEFAULT_FROM_EMAIL or "root@localhost"
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "church_system.mail.PlatformSMTPEmailBackend",
)
CHURCHHUB_ASYNC_EMAIL = os.environ.get("CHURCHHUB_ASYNC_EMAIL", "").lower() in (
    "true",
    "1",
    "yes",
)

_CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", "").strip() or REDIS_URL
CELERY_BROKER_URL = _CELERY_BROKER or "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "").lower() in (
    "true",
    "1",
    "yes",
) or "test" in sys.argv
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_WORKER_PREFETCH_MULTIPLIER = env_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_DEFAULT_RETRY_DELAY = env_int("CELERY_TASK_DEFAULT_RETRY_DELAY", 60)
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 600)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 540)

# Beat schedules — ops may disable via CHURCHHUB_CELERY_BEAT=0
CELERY_BEAT_SCHEDULE = {}
if env_flag("CHURCHHUB_CELERY_BEAT", True):
    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        "purge-old-notifications-daily": {
            "task": "church_system.tasks.purge_old_notifications_task",
            "schedule": crontab(hour=2, minute=15),
            "options": {"expires": 3600},
        },
        "database-backup-daily": {
            "task": "church_system.tasks.backup_database_task",
            "schedule": crontab(hour=3, minute=0),
            "options": {"expires": 7200},
        },
        "health-probe-hourly": {
            "task": "church_system.tasks.health_probe_task",
            "schedule": crontab(minute=5),
            "options": {"expires": 600},
        },
    }

LOG_DIR = Path(env_str("CHURCHHUB_LOG_DIR") or str(BASE_DIR / "logs"))
from church_system.logging_config import build_logging_config  # noqa: E402

LOGGING = build_logging_config(
    debug=DEBUG,
    log_dir=LOG_DIR,
    enable_file_logs=env_flag("CHURCHHUB_FILE_LOGS", not DEBUG),
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEST_RUNNER = "church_system.test_runner.ChurchHubDiscoverRunner"

# Cache invalidation keys (document convention for services)
CACHE_VERSION = env_int("CACHE_VERSION", 1)
PERMISSION_CACHE_TIMEOUT = env_int("PERMISSION_CACHE_TIMEOUT", 300)
