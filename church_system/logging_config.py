"""Structured logging configuration for ChurchHub."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path


def scrub_sentry_event(event, hint):  # noqa: ARG001
    """
    Drop or redact sensitive keys before events leave the process.

    Used as Sentry ``before_send``.
    """
    sensitive = {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "csrf",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "django_secret_key",
        "database_url",
        "redis_url",
        "celery_broker_url",
    }

    def _scrub_mapping(obj):
        if not isinstance(obj, dict):
            return
        for key in list(obj.keys()):
            lowered = str(key).lower()
            if any(s in lowered for s in sensitive):
                obj[key] = "[Filtered]"
            else:
                val = obj[key]
                if isinstance(val, dict):
                    _scrub_mapping(val)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            _scrub_mapping(item)

    _scrub_mapping(event.get("request") or {})
    _scrub_mapping(event.get("extra") or {})
    _scrub_mapping(event.get("contexts") or {})
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for hk in list(headers.keys()):
                if str(hk).lower() in {
                    "authorization",
                    "cookie",
                    "x-csrftoken",
                    "x-health-token",
                }:
                    headers[hk] = "[Filtered]"
    return event


def configure_sentry() -> None:
    """Initialize Sentry when SENTRY_DSN is set. No-op when unset."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        init_kwargs = {
            "dsn": dsn,
            "integrations": [
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            "traces_sample_rate": float(
                os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")
            ),
            "send_default_pii": False,
            "environment": os.environ.get(
                "SENTRY_ENVIRONMENT",
                os.environ.get("DJANGO_ENV", "production"),
            ),
            "before_send": scrub_sentry_event,
        }
        release = os.environ.get("SENTRY_RELEASE", "").strip()
        if release:
            init_kwargs["release"] = release

        sentry_sdk.init(**init_kwargs)
    except ImportError:
        logging.getLogger("churchhub").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed."
        )


class SecretRedactFilter(logging.Filter):
    """Logging filter that masks common secret patterns in log messages."""

    _PREFIX_PATTERNS = (
        re.compile(r"(password\s*[=:]\s*)\S+", re.I),
        re.compile(r"(passwd\s*[=:]\s*)\S+", re.I),
        re.compile(r"(secret[_-]?key\s*[=:]\s*)\S+", re.I),
        re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.I),
        re.compile(r"(token\s*[=:]\s*)\S+", re.I),
        re.compile(r"(authorization\s*[=:]\s*)\S+", re.I),
    )
    _FULL_PATTERNS = (
        re.compile(r"postgres(?:ql)?://\S+", re.I),
        re.compile(r"redis://\S+", re.I),
    )

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for pattern in self._PREFIX_PATTERNS:
            redacted = pattern.sub(r"\1[Filtered]", redacted)
        for pattern in self._FULL_PATTERNS:
            redacted = pattern.sub("[Filtered]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def build_logging_config(
    *,
    debug: bool,
    log_dir: Path | str | None = None,
    enable_file_logs: bool | None = None,
) -> dict:
    """
    Return Django LOGGING dict.

    - Console: always on (platform-friendly for Docker/Render)
    - Optional rotating files under log_dir:
      application.log, security.log, audit.log
    - SecretRedactFilter on all handlers (disk-safe rotation defaults: 10MB × 10)
    """
    env_level = os.environ.get("DJANGO_LOG_LEVEL", "").upper()
    if env_level in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        app_level = env_level
    else:
        app_level = "DEBUG" if debug else "INFO"

    console_level = env_level if env_level else "INFO"
    formatter_name = "verbose" if debug else "structured"

    if enable_file_logs is None:
        enable_file_logs = os.environ.get("CHURCHHUB_FILE_LOGS", "").lower() in (
            "true",
            "1",
            "yes",
        ) or (not debug)

    redact_filters = ["secret_redact"]
    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": formatter_name,
            "level": console_level,
            "filters": redact_filters,
        },
    }
    app_handlers = ["console"]
    security_handlers = ["console"]
    audit_handlers = ["console"]

    if enable_file_logs:
        base = Path(log_dir or os.environ.get("CHURCHHUB_LOG_DIR") or "logs")
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            enable_file_logs = False

    if enable_file_logs:
        base = Path(log_dir or os.environ.get("CHURCHHUB_LOG_DIR") or "logs")
        common_file = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "structured",
            "maxBytes": int(os.environ.get("CHURCHHUB_LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            "backupCount": int(os.environ.get("CHURCHHUB_LOG_BACKUP_COUNT", "10")),
            "encoding": "utf-8",
            "filters": redact_filters,
        }
        handlers["app_file"] = {
            **common_file,
            "filename": str(base / "application.log"),
            "level": app_level,
        }
        handlers["security_file"] = {
            **common_file,
            "filename": str(base / "security.log"),
            "level": "INFO",
        }
        handlers["audit_file"] = {
            **common_file,
            "filename": str(base / "audit.log"),
            "level": "INFO",
        }
        app_handlers = ["console", "app_file"]
        security_handlers = ["console", "security_file"]
        audit_handlers = ["console", "audit_file"]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "secret_redact": {
                "()": "church_system.logging_config.SecretRedactFilter",
            },
        },
        "formatters": {
            "verbose": {
                "format": "{levelname} {asctime} {name} {message}",
                "style": "{",
            },
            "structured": {
                "format": (
                    'level={levelname} time="{asctime}" logger={name} '
                    'module={module} message="{message}"'
                ),
                "style": "{",
            },
        },
        "handlers": handlers,
        "root": {
            "handlers": app_handlers,
            "level": console_level,
        },
        "loggers": {
            "django": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "django.request": {
                "handlers": security_handlers,
                "level": "WARNING" if not debug else "INFO",
                "propagate": False,
            },
            "django.security": {
                "handlers": security_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "django.server": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "django.utils.autoreload": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.db.backends": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "churchhub": {
                "handlers": app_handlers,
                "level": app_level,
                "propagate": False,
            },
            "churchhub.security": {
                "handlers": security_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "churchhub.audit": {
                "handlers": audit_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "accounts": {
                "handlers": security_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "gunicorn.error": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "gunicorn.access": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
            "celery": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
        },
    }
