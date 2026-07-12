"""Operational health checks for load balancers and monitoring."""

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


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


def run_health_checks():
    """
    Run all health probes.
    Returns (payload dict, http_status).
    """
    payload = {
        "status": "ok",
        "service": "churchhub",
        "checks": {
            "database": "unknown",
            "cache": "unknown",
            "migrations": "unknown",
        },
    }
    failures = []

    for name, checker in (
        ("database", check_database),
        ("cache", check_cache),
        ("migrations", check_migrations),
    ):
        try:
            payload["checks"][name] = checker()
        except Exception as exc:
            payload["checks"][name] = "error"
            payload["checks"][f"{name}_detail"] = str(exc)
            failures.append(name)

    if failures:
        payload["status"] = "degraded"
        return payload, 503
    return payload, 200
