"""Structured logging configuration for ChurchHub."""

import os


def build_logging_config(*, debug: bool) -> dict:
    """Return Django LOGGING dict — quiet console in dev, structured in production."""
    env_level = os.environ.get("DJANGO_LOG_LEVEL", "").upper()
    if env_level in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        app_level = env_level
    else:
        app_level = "DEBUG" if debug else "INFO"

    console_level = env_level if env_level else "INFO"
    formatter_name = "verbose" if debug else "structured"

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
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
                "level": console_level,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": console_level,
        },
        "loggers": {
            "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING" if not debug else "INFO",
                "propagate": False,
            },
            "django.server": {
                "handlers": ["console"],
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
            "churchhub": {"handlers": ["console"], "level": app_level, "propagate": False},
        },
    }


def configure_sentry() -> None:
    """Initialize Sentry when SENTRY_DSN is set."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[DjangoIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )
    except ImportError:
        import logging

        logging.getLogger("churchhub").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed."
        )
