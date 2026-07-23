"""Environment helpers and production validation for ChurchHub."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


_INSECURE_SECRET = "django-insecure-change-this-in-production"


def load_dotenv(path: Path) -> None:
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


def env_flag(name: str, default: bool | None = None) -> bool | None:
    """Return True/False for a boolean env var, or default if unset."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes")


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


def resolve_django_env() -> str:
    """
    Return development | staging | production.

    Precedence:
    1. DJANGO_ENV / CHURCHHUB_ENV
    2. RENDER / DYNO / PYTHONANYWHERE_SITE → production
    3. default → development
    """
    explicit = (
        os.environ.get("DJANGO_ENV")
        or os.environ.get("CHURCHHUB_ENV")
        or ""
    ).strip().lower()
    if explicit in {"development", "dev", "local"}:
        return "development"
    if explicit in {"staging", "stage"}:
        return "staging"
    if explicit in {"production", "prod"}:
        return "production"
    if explicit:
        raise ImproperlyConfigured(
            f"Unknown DJANGO_ENV={explicit!r}. Use development, staging, or production."
        )
    if os.environ.get("RENDER") or os.environ.get("DYNO") or os.environ.get("PYTHONANYWHERE_SITE"):
        return "production"
    return "development"


def insecure_secret_default() -> str:
    return _INSECURE_SECRET


def validate_production_environment(
    *,
    secret_key: str,
    debug: bool,
    allowed_hosts: list[str],
    database_engine: str,
    redis_url: str,
    csrf_trusted_origins: list[str],
    require_redis: bool = True,
    allow_mysql: bool = False,
    allow_sqlite: bool = False,
) -> None:
    """Raise ImproperlyConfigured when production essentials are missing."""
    errors: list[str] = []

    if debug:
        errors.append("DEBUG must be False in production/staging.")
    if not secret_key or secret_key == _INSECURE_SECRET:
        errors.append("DJANGO_SECRET_KEY must be set to a unique non-default value.")
    if not allowed_hosts or allowed_hosts == ["*"]:
        errors.append("DJANGO_ALLOWED_HOSTS must list explicit hostnames.")

    engine = (database_engine or "").lower()
    if "sqlite" in engine and not allow_sqlite:
        errors.append(
            "A managed database is required (DATABASE_URL or DB_ENGINE=postgresql"
            + ("|mysql" if allow_mysql else "")
            + ")."
        )
    elif "mysql" in engine and not allow_mysql:
        errors.append("PostgreSQL is required (DATABASE_URL or DB_ENGINE=postgresql).")
    elif (
        "postgresql" not in engine
        and "mysql" not in engine
        and "sqlite" not in engine
    ):
        errors.append("Unrecognized database engine for production.")

    if require_redis and not redis_url:
        errors.append(
            "REDIS_URL is required for multi-worker cache, rate limits, and Celery."
        )
    if not csrf_trusted_origins:
        errors.append(
            "DJANGO_CSRF_TRUSTED_ORIGINS must include https://your-production-host"
        )

    if errors:
        raise ImproperlyConfigured(
            "Production environment validation failed:\n- " + "\n- ".join(errors)
        )
