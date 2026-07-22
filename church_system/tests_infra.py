"""Infrastructure settings, health, and env validation tests."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, Client
from django.urls import reverse

from church_system.env import (
    insecure_secret_default,
    resolve_django_env,
    validate_production_environment,
)
from church_system.health import basic_metrics, run_liveness_checks
from church_system.storage import build_storages


class EnvHelperTests(SimpleTestCase):
    def test_resolve_django_env_aliases(self):
        import os

        previous = os.environ.get("DJANGO_ENV")
        os.environ["DJANGO_ENV"] = "prod"
        try:
            self.assertEqual(resolve_django_env(), "production")
        finally:
            if previous is None:
                os.environ.pop("DJANGO_ENV", None)
            else:
                os.environ["DJANGO_ENV"] = previous

    def test_validate_production_rejects_sqlite_and_insecure(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_environment(
                secret_key=insecure_secret_default(),
                debug=True,
                allowed_hosts=[],
                database_engine="django.db.backends.sqlite3",
                redis_url="",
                csrf_trusted_origins=[],
                require_redis=True,
            )
        msg = str(ctx.exception)
        self.assertIn("DEBUG", msg)
        self.assertIn("DJANGO_SECRET_KEY", msg)
        self.assertIn("PostgreSQL", msg)
        self.assertIn("REDIS_URL", msg)

    def test_validate_production_passes_minimal(self):
        validate_production_environment(
            secret_key="unique-production-secret-key-value",
            debug=False,
            allowed_hosts=["app.example.com"],
            database_engine="django.db.backends.postgresql",
            redis_url="redis://localhost:6379/0",
            csrf_trusted_origins=["https://app.example.com"],
            require_redis=True,
        )


class StorageConfigTests(SimpleTestCase):
    def test_default_filesystem_and_whitenoise(self):
        storages = build_storages()
        self.assertIn("FileSystemStorage", storages["default"]["BACKEND"])
        self.assertIn("whitenoise", storages["staticfiles"]["BACKEND"])


class HealthEndpointTests(TestCase):
    def test_liveness_payload_shape(self):
        payload, status = run_liveness_checks()
        self.assertIn(status, (200, 503))
        self.assertEqual(payload.get("check_type"), "liveness")
        self.assertIn("database", payload.get("checks", {}))

    def test_metrics_shape(self):
        data = basic_metrics()
        self.assertEqual(data["service"], "churchhub")
        self.assertIn("database_engine", data)

    def test_health_urls_resolve(self):
        client = Client()
        for name in ("health_check", "health_live", "health_ready"):
            url = reverse(name)
            response = client.get(url)
            self.assertIn(response.status_code, (200, 503), msg=name)

    def test_metrics_requires_authentication(self):
        client = Client()
        response = client.get(reverse("metrics"))
        self.assertEqual(response.status_code, 401)
