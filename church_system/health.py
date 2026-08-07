"""Operational health / readiness / liveness checks."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

logger = logging.getLogger("churchhub")


def _expose_health_details() -> bool:
    """Raw exception detail in JSON only when DEBUG (local diagnosis)."""
    return bool(getattr(settings, "DEBUG", False))


def _safe_detail(exc: BaseException) -> str:
    """Map failures to non-sensitive codes for production health JSON."""
    text = str(exc).lower()
    if "pending migration" in text:
        return "pending_migrations"
    if "debug=true" in text or "debug" in text and "production" in text:
        return "misconfigured"
    if "redis_url is required" in text or "redis" in text and "required" in text:
        return "misconfigured"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "password" in text or "authentication" in text or "auth failed" in text:
        return "unavailable"
    return "unavailable"


def check_database():
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return "ok"


def check_cache():
    probe_key = "health:probe"
    cache.set(probe_key, "1", 10)
    if cache.get(probe_key) != "1":
        raise RuntimeError("cache read/write failed")
    cache.delete(probe_key)
    return "ok"


def check_migrations():
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        raise RuntimeError(f"{len(plan)} pending migration(s)")
    return "ok"


def check_debug_safe():
    """Fail health when DEBUG is on in a production-like deployment."""
    from church_system.debug_config import is_production_like_env

    if settings.DEBUG and is_production_like_env():
        raise RuntimeError(
            "DEBUG=True on a production-like host (DATABASE_URL / RENDER / "
            "PYTHONANYWHERE_SITE / DYNO). Set DJANGO_DEBUG=False."
        )
    return "ok"


def check_redis_configured():
    """Require Redis in production except when startup allows LocMem (e.g. PythonAnywhere)."""
    redis_url = getattr(settings, "REDIS_URL", "") or ""
    env = getattr(settings, "DJANGO_ENV", "development")
    require_redis = bool(getattr(settings, "REQUIRE_REDIS", env == "production"))
    if redis_url:
        check_cache()
        return "ok"
    if env == "production" and require_redis:
        raise RuntimeError("REDIS_URL is required in production")
    return "skipped"


def check_celery_broker():
    """Optional probe — skip when eager or broker unreachable in non-prod."""
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return "eager"
    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    if not broker:
        return "skipped"
    try:
        from kombu import Connection

        with Connection(broker) as conn:
            conn.ensure_connection(max_retries=1, timeout=2)
        return "ok"
    except Exception as exc:
        env = getattr(settings, "DJANGO_ENV", "development")
        if env == "production":
            raise RuntimeError(f"celery broker unreachable: {exc}") from exc
        return f"degraded:{exc}"


def _run_named_checks(checks: tuple[tuple[str, Callable], ...]):
    payload = {"status": "ok", "service": "churchhub", "checks": {}}
    failures = []
    expose = _expose_health_details()
    for name, checker in checks:
        payload["checks"][name] = "unknown"
        try:
            payload["checks"][name] = checker()
        except Exception as exc:
            logger.error("Health check %s failed: %s", name, exc, exc_info=True)
            payload["checks"][name] = "error"
            payload["checks"][f"{name}_detail"] = (
                str(exc) if expose else _safe_detail(exc)
            )
            failures.append(name)
    if failures:
        payload["status"] = "degraded"
        return payload, 503
    return payload, 200


def run_liveness_checks():
    """Process is up — minimal probes (DB ping only)."""
    started = time.time()
    payload, status = _run_named_checks((("database", check_database),))
    payload["check_type"] = "liveness"
    payload["duration_ms"] = int((time.time() - started) * 1000)
    return payload, status


def run_readiness_checks():
    """Ready to serve traffic — DB, migrations, cache/redis, debug safety."""
    started = time.time()
    checks = [
        ("database", check_database),
        ("migrations", check_migrations),
        ("cache", check_cache),
        ("debug", check_debug_safe),
        ("redis", check_redis_configured),
    ]
    payload, status = _run_named_checks(tuple(checks))
    payload["check_type"] = "readiness"
    payload["duration_ms"] = int((time.time() - started) * 1000)
    payload["django_env"] = getattr(settings, "DJANGO_ENV", "unknown")
    return payload, status


def run_health_checks():
    """
    Full health probes (backward compatible with /health/).
    Returns (payload dict, http_status).
    """
    started = time.time()
    checks = [
        ("database", check_database),
        ("cache", check_cache),
        ("migrations", check_migrations),
        ("debug", check_debug_safe),
        ("redis", check_redis_configured),
    ]
    payload, status = _run_named_checks(tuple(checks))
    try:
        payload["checks"]["celery_broker"] = check_celery_broker()
    except Exception as exc:
        logger.error("Health check celery_broker failed: %s", exc, exc_info=True)
        payload["checks"]["celery_broker"] = "error"
        payload["checks"]["celery_broker_detail"] = (
            str(exc) if _expose_health_details() else _safe_detail(exc)
        )
        payload["status"] = "degraded"
        status = 503
    payload["check_type"] = "health"
    payload["duration_ms"] = int((time.time() - started) * 1000)
    payload["django_env"] = getattr(settings, "DJANGO_ENV", "unknown")
    return payload, status


def basic_metrics():
    """Lightweight process metrics for /metrics/ JSON (not Prometheus)."""
    import os

    try:
        import django

        django_version = django.get_version()
    except Exception:
        django_version = "unknown"

    db_engine = settings.DATABASES["default"]["ENGINE"].split(".")[-1]
    return {
        "service": "churchhub",
        "django_env": getattr(settings, "DJANGO_ENV", "unknown"),
        "django_version": django_version,
        "debug": bool(settings.DEBUG),
        "database_engine": db_engine,
        "redis_configured": bool(getattr(settings, "REDIS_URL", "")),
        "celery_eager": bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)),
        "pid": os.getpid(),
    }
