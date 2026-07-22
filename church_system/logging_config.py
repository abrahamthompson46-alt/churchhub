"""Structured logging configuration for ChurchHub."""

from __future__ import annotations

import os
from pathlib import Path


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

    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": formatter_name,
            "level": console_level,
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
            "celery": {
                "handlers": app_handlers,
                "level": "INFO",
                "propagate": False,
            },
        },
    }


def configure_sentry() -> None:
    """Initialize Sentry when SENTRY_DSN is set."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            environment=os.environ.get(
                "SENTRY_ENVIRONMENT",
                os.environ.get("DJANGO_ENV", "production"),
            ),
        )
    except ImportError:
        import logging

        logging.getLogger("churchhub").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed."
        )
