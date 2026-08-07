"""Observability: health redaction, Sentry optional config, log scrubbing."""

from __future__ import annotations

import logging
import os
from unittest import mock

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from church_system.health import (
    _safe_detail,
    run_health_checks,
    run_liveness_checks,
    run_readiness_checks,
)
from church_system.logging_config import (
    SecretRedactFilter,
    configure_sentry,
    scrub_sentry_event,
)


class HealthSafeDetailTests(SimpleTestCase):
    def test_safe_detail_codes(self):
        self.assertEqual(_safe_detail(RuntimeError("pending migration(s)")), "pending_migrations")
        self.assertEqual(_safe_detail(TimeoutError("connection timed out")), "timeout")
        self.assertEqual(
            _safe_detail(RuntimeError("password authentication failed")),
            "unavailable",
        )
        self.assertEqual(_safe_detail(RuntimeError("other")), "unavailable")


@override_settings(DEBUG=False, DJANGO_ENV="production", HEALTH_CHECK_TOKEN="")
class HealthRedactionTests(SimpleTestCase):
    def test_database_failure_redacts_detail_when_not_debug(self):
        with mock.patch(
            "church_system.health.check_database",
            side_effect=RuntimeError("password=secret host=db.internal"),
        ):
            payload, status = run_liveness_checks()
        self.assertEqual(status, 503)
        self.assertEqual(payload["checks"]["database"], "error")
        self.assertEqual(payload["checks"]["database_detail"], "unavailable")
        self.assertNotIn("password", payload["checks"]["database_detail"])
        self.assertNotIn("db.internal", str(payload))

    def test_redis_failure_on_readiness(self):
        with mock.patch(
            "church_system.health.check_redis_configured",
            side_effect=RuntimeError("Error 111 connecting to redis:6379"),
        ):
            payload, status = run_readiness_checks()
        self.assertEqual(status, 503)
        self.assertEqual(payload["checks"]["redis"], "error")
        self.assertEqual(payload["checks"]["redis_detail"], "unavailable")

    def test_full_health_includes_redis_key(self):
        with mock.patch("church_system.health.check_database", return_value="ok"), mock.patch(
            "church_system.health.check_cache", return_value="ok"
        ), mock.patch(
            "church_system.health.check_migrations", return_value="ok"
        ), mock.patch(
            "church_system.health.check_debug_safe", return_value="ok"
        ), mock.patch(
            "church_system.health.check_redis_configured", return_value="ok"
        ), mock.patch(
            "church_system.health.check_celery_broker", return_value="skipped"
        ):
            payload, status = run_health_checks()
        self.assertEqual(status, 200)
        self.assertIn("redis", payload["checks"])
        self.assertEqual(payload["checks"]["redis"], "ok")


@override_settings(DEBUG=True, DJANGO_ENV="development", HEALTH_CHECK_TOKEN="")
class HealthDebugDetailTests(SimpleTestCase):
    def test_debug_exposes_exception_text(self):
        with mock.patch(
            "church_system.health.check_database",
            side_effect=RuntimeError("local-only-detail"),
        ):
            payload, status = run_liveness_checks()
        self.assertEqual(status, 503)
        self.assertEqual(payload["checks"]["database_detail"], "local-only-detail")


@override_settings(HEALTH_CHECK_TOKEN="probe-secret")
class HealthTokenTests(TestCase):
    def test_health_requires_token_when_configured(self):
        client = Client()
        response = client.get(reverse("health_ready"))
        self.assertEqual(response.status_code, 401)

    def test_health_accepts_header_token(self):
        client = Client()
        response = client.get(
            reverse("health_live"),
            HTTP_X_HEALTH_TOKEN="probe-secret",
        )
        self.assertIn(response.status_code, (200, 503))


class SentryConfigTests(SimpleTestCase):
    def test_sentry_disabled_when_dsn_unset(self):
        previous = os.environ.pop("SENTRY_DSN", None)
        try:
            with mock.patch("sentry_sdk.init") as init:
                configure_sentry()
                init.assert_not_called()
        finally:
            if previous is not None:
                os.environ["SENTRY_DSN"] = previous

    def test_sentry_enabled_with_release_and_scrubber(self):
        previous = {
            k: os.environ.get(k)
            for k in (
                "SENTRY_DSN",
                "SENTRY_RELEASE",
                "SENTRY_ENVIRONMENT",
                "SENTRY_TRACES_SAMPLE_RATE",
            )
        }
        os.environ["SENTRY_DSN"] = "https://key@example.com/1"
        os.environ["SENTRY_RELEASE"] = "churchhub@test"
        os.environ["SENTRY_ENVIRONMENT"] = "staging"
        os.environ["SENTRY_TRACES_SAMPLE_RATE"] = "0.05"
        try:
            with mock.patch("sentry_sdk.init") as init:
                configure_sentry()
                init.assert_called_once()
                kwargs = init.call_args.kwargs
                self.assertFalse(kwargs["send_default_pii"])
                self.assertEqual(kwargs["release"], "churchhub@test")
                self.assertEqual(kwargs["environment"], "staging")
                self.assertEqual(kwargs["traces_sample_rate"], 0.05)
                self.assertIs(kwargs["before_send"], scrub_sentry_event)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_scrub_sentry_event_filters_secrets(self):
        event = {
            "request": {
                "cookies": {"sessionid": "abc"},
                "headers": {
                    "Authorization": "Bearer secret",
                    "X-Health-Token": "probe",
                    "Accept": "application/json",
                },
                "data": {"password": "hunter2", "username": "admin"},
            },
            "extra": {"database_url": "postgres://u:p@host/db", "ok": 1},
        }
        out = scrub_sentry_event(event, hint=None)
        self.assertNotIn("cookies", out["request"])
        self.assertEqual(out["request"]["headers"]["Authorization"], "[Filtered]")
        self.assertEqual(out["request"]["headers"]["X-Health-Token"], "[Filtered]")
        self.assertEqual(out["request"]["headers"]["Accept"], "application/json")
        self.assertEqual(out["request"]["data"]["password"], "[Filtered]")
        self.assertEqual(out["request"]["data"]["username"], "admin")
        self.assertEqual(out["extra"]["database_url"], "[Filtered]")
        self.assertEqual(out["extra"]["ok"], 1)


class LoggingRedactTests(SimpleTestCase):
    def test_secret_redact_filter(self):
        filt = SecretRedactFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="login password=supersecret token=abc123",
            args=(),
            exc_info=None,
        )
        self.assertTrue(filt.filter(record))
        self.assertIn("[Filtered]", record.getMessage())
        self.assertNotIn("supersecret", record.getMessage())

    def test_logging_config_has_rotation_and_filter(self):
        from church_system.logging_config import build_logging_config

        cfg = build_logging_config(debug=False, enable_file_logs=False)
        self.assertIn("secret_redact", cfg["filters"])
        self.assertIn("filters", cfg["handlers"]["console"])
        # Defaults documented for VPS disk safety
        cfg_files = build_logging_config(
            debug=False, log_dir=None, enable_file_logs=True
        )
        app = cfg_files["handlers"].get("app_file")
        if app:
            self.assertEqual(app["maxBytes"], 10 * 1024 * 1024)
            self.assertEqual(app["backupCount"], 10)
