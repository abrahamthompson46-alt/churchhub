# settings.py

from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

# ============================================
# PLATFORM DETECTION
# ============================================

ON_RENDER = bool(os.environ.get("RENDER"))
ON_PYTHONANYWHERE = bool(os.environ.get("PYTHONANYWHERE_SITE"))

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs from .env without requiring python-dotenv."""
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip().strip("'").strip('"')
            os.environ[key] = value
    except OSError:
        pass


_load_dotenv(BASE_DIR / ".env")

# ==============================
# SECURITY
# ==============================

_INSECURE_SECRET = "django-insecure-change-this-in-production"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _INSECURE_SECRET)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

if not DEBUG and SECRET_KEY == _INSECURE_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG is False."
    )

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1,testserver,churchhub.pythonanywhere.com,www.churchhub.pythonanywhere.com",
).split(",")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Render.com auto-configuration
_RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _RENDER_HOST:
    if _RENDER_HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_RENDER_HOST)
    _render_origin = f"https://{_RENDER_HOST}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

# ==============================
# APPLICATIONS
# ==============================

INSTALLED_APPS = [
    "admin_custom",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Project core (template tags, shared utilities)
    "church_system.apps.ChurchSystemConfig",
    # Local Apps
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

# ==============================
# MIDDLEWARE
# ==============================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "permissions.middleware.PermissionCacheMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "permissions.middleware.RoleEnforcementMiddleware",
    "sitecontrol.denomination_middleware.DenominationContextMiddleware",
    "sitecontrol.middleware.UserScopeMiddleware",
    "sitecontrol.middleware.PlatformSessionMiddleware",
    "sitecontrol.middleware.MaintenanceModeMiddleware",
    "sitecontrol.middleware.LoginRateLimitMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ==============================
# URLS & WSGI
# ==============================

ROOT_URLCONF = "church_system.urls"
WSGI_APPLICATION = "church_system.wsgi.application"

# ==============================
# TEMPLATES
# ==============================

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

# ==============================
# DATABASE
# ==============================

def _configure_databases():
    """
    Database priority:

    1. DATABASE_URL
    2. Explicit PostgreSQL settings (DB_ENGINE=postgresql)
    3. SQLite (Local & PythonAnywhere)

    Render always requires PostgreSQL.
    """

    database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url:
        import dj_database_url

        db = dj_database_url.parse(
            database_url,
            conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
            conn_health_checks=True,
        )

        if ON_RENDER:
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
                "CONN_MAX_AGE": 600,
            }
        }

    if ON_RENDER:
        raise ImproperlyConfigured(
            "DATABASE_URL must be configured on Render."
        )

    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


DATABASES = _configure_databases()

# ==============================
# PASSWORD VALIDATION
# ==============================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "accounts.validators.PlatformMinimumLengthValidator"},
    {"NAME": "accounts.validators.PlatformUppercaseValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==============================
# INTERNATIONALIZATION
# ==============================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

# ==============================
# STATIC FILES
# ==============================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# ==============================
# MEDIA FILES
# ==============================

MEDIA_URL = "/media/"
_media_root = os.environ.get("MEDIA_ROOT", "").strip()
MEDIA_ROOT = Path(_media_root) if _media_root else BASE_DIR / "media"

# ==============================
# AUTH
# ==============================

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ==============================
# SESSION
# ==============================

SESSION_COOKIE_AGE = 60 * 60 * 4
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ==============================
# SECURITY OPTIONS
# ==============================

X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in (
        "true",
        "1",
        "yes",
    )
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ==============================
# CACHE (Redis in production)
# ==============================

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "churchhub-default",
        }
    }

# ==============================
# LOGGING & MONITORING
# ==============================

from church_system.logging_config import build_logging_config  # noqa: E402

LOGGING = build_logging_config(debug=DEBUG)

# Public URL for emails when request object unavailable (e.g. management commands)
CHURCHHUB_PUBLIC_URL = os.environ.get(
    "CHURCHHUB_PUBLIC_URL",
    f"https://{_RENDER_HOST}" if _RENDER_HOST else "http://localhost:8000",
)

# ==============================
# EMAIL (Platform SMTP preferred; env is fallback)
# ==============================
# Primary config: Platform Control → Email (SiteSettings).
# Optional env fallback used when SiteSettings SMTP fields are empty.
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
# Invitation emails send synchronously by default so the UI reports real delivery.
# Set CHURCHHUB_ASYNC_EMAIL=1 only when a Celery worker is running.
CHURCHHUB_ASYNC_EMAIL = os.environ.get("CHURCHHUB_ASYNC_EMAIL", "").lower() in (
    "true",
    "1",
    "yes",
)

# ==============================
# CELERY
# ==============================

import sys

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

# ==============================
# DEFAULT PRIMARY KEY
# ==============================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
