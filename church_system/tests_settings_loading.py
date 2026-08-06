"""Settings package selection: dotenv-before-resolve and production HTTPS flags."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from django.test import SimpleTestCase

from church_system.env import (
    ensure_dotenv_loaded,
    load_dotenv,
    project_root,
    resolve_django_env,
)


class DotenvBeforeResolveTests(SimpleTestCase):
    def test_project_root_points_at_repo(self):
        root = project_root()
        self.assertTrue((root / "manage.py").is_file())
        self.assertTrue((root / "church_system").is_dir())

    def test_dotenv_supplies_django_env_when_unset(self):
        """Regression: .env DJANGO_ENV must be visible before resolve_django_env()."""
        previous = os.environ.pop("DJANGO_ENV", None)
        previous_ch = os.environ.pop("CHURCHHUB_ENV", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_path = Path(tmp) / ".env"
                env_path.write_text("DJANGO_ENV=production\n", encoding="utf-8")
                load_dotenv(env_path)
                self.assertEqual(resolve_django_env(), "production")
        finally:
            os.environ.pop("DJANGO_ENV", None)
            if previous is not None:
                os.environ["DJANGO_ENV"] = previous
            if previous_ch is not None:
                os.environ["CHURCHHUB_ENV"] = previous_ch

    def test_process_env_wins_over_dotenv(self):
        previous = os.environ.get("DJANGO_ENV")
        os.environ["DJANGO_ENV"] = "development"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_path = Path(tmp) / ".env"
                env_path.write_text("DJANGO_ENV=production\n", encoding="utf-8")
                load_dotenv(env_path)
                self.assertEqual(resolve_django_env(), "development")
        finally:
            if previous is None:
                os.environ.pop("DJANGO_ENV", None)
            else:
                os.environ["DJANGO_ENV"] = previous

    def test_ensure_dotenv_loaded_is_idempotent(self):
        path = ensure_dotenv_loaded()
        again = ensure_dotenv_loaded()
        self.assertEqual(path, again)

    def test_default_without_env_is_development(self):
        previous = os.environ.pop("DJANGO_ENV", None)
        previous_ch = os.environ.pop("CHURCHHUB_ENV", None)
        # Clear PaaS heuristics that force production
        cleared = {}
        for key in ("RENDER", "DYNO", "PYTHONANYWHERE_SITE"):
            if key in os.environ:
                cleared[key] = os.environ.pop(key)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_path = Path(tmp) / ".env"
                env_path.write_text("# empty of DJANGO_ENV\n", encoding="utf-8")
                load_dotenv(env_path)
                self.assertEqual(resolve_django_env(), "development")
        finally:
            if previous is not None:
                os.environ["DJANGO_ENV"] = previous
            if previous_ch is not None:
                os.environ["CHURCHHUB_ENV"] = previous_ch
            os.environ.update(cleared)


class ProductionSettingsModuleTests(SimpleTestCase):
    """Import production settings in a subprocess so the test runner is unaffected."""

    def _run_settings_probe(self, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
        root = project_root()
        script = textwrap.dedent(
            """
            import os
            # Force package auto-select path used by manage.py / gunicorn / celery
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
            import django
            django.setup()
            from django.conf import settings
            print("DJANGO_ENV=" + str(settings.DJANGO_ENV))
            print("DEBUG=" + str(settings.DEBUG))
            print("SECURE_SSL_REDIRECT=" + str(bool(settings.SECURE_SSL_REDIRECT)))
            print("SESSION_COOKIE_SECURE=" + str(bool(settings.SESSION_COOKIE_SECURE)))
            print("CSRF_COOKIE_SECURE=" + str(bool(settings.CSRF_COOKIE_SECURE)))
            print("HSTS=" + str(int(settings.SECURE_HSTS_SECONDS)))
            """
        )
        env = os.environ.copy()
        # Isolate from the developer's local .env by setting explicit vars
        # (load_dotenv never overwrites process env).
        env.update(extra_env)
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_production_env_loads_secure_cookies(self):
        result = self._run_settings_probe(
            {
                "DJANGO_ENV": "production",
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "wave1-settings-prod-test-secret-key-32chars",
                "DJANGO_ALLOWED_HOSTS": "example.com",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.com",
                "CHURCHHUB_PUBLIC_URL": "https://example.com",
                "REDIS_URL": "redis://127.0.0.1:6379/0",
                "DATABASE_URL": "postgres://churchhub:churchhub@127.0.0.1:5432/churchhub",
                "CHURCHHUB_HEALTH_TOKEN": "health-token-for-settings-test",
                "SECURE_SSL_REDIRECT": "true",
                "CHURCHHUB_REQUIRE_REDIS": "false",
            }
        )
        if result.returncode != 0:
            self.fail(
                "production settings import failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        out = result.stdout
        self.assertIn("DJANGO_ENV=production", out)
        self.assertIn("DEBUG=False", out)
        self.assertIn("SECURE_SSL_REDIRECT=True", out)
        self.assertIn("SESSION_COOKIE_SECURE=True", out)
        self.assertIn("CSRF_COOKIE_SECURE=True", out)
        self.assertIn("HSTS=31536000", out)

    def test_development_env_still_loads_locally(self):
        result = self._run_settings_probe(
            {
                "DJANGO_ENV": "development",
                "DJANGO_DEBUG": "True",
                "DJANGO_SECRET_KEY": "dev-only-insecure-ok-for-subprocess-test",
                # Avoid inheriting production-like flags from the parent process
                "RENDER": "",
                "DYNO": "",
                "PYTHONANYWHERE_SITE": "",
            }
        )
        if result.returncode != 0:
            self.fail(
                "development settings import failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        out = result.stdout
        self.assertIn("DJANGO_ENV=development", out)
        self.assertIn("DEBUG=True", out)
        # Development does not force Secure cookies
        self.assertIn("SESSION_COOKIE_SECURE=False", out)

    def test_dotenv_file_selects_production_without_exported_django_env(self):
        """Simulate manage.py shell: DJANGO_ENV only in .env, not pre-exported."""
        root = project_root()
        with tempfile.TemporaryDirectory() as tmp:
            # Use a side .env and point ensure via copying into a subprocess that
            # only has CHURCHHUB-style vars after early load — we inject via
            # writing to a temp file and monkeypatching is hard in subprocess;
            # instead unset DJANGO_ENV and put production into a file that
            # ensure_dotenv_loaded reads: the real project .env may exist, so
            # we pass DJANGO_ENV only through a pre-load script that calls
            # load_dotenv on our temp file then django.setup().
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DJANGO_ENV=production",
                        "DJANGO_DEBUG=False",
                        "DJANGO_SECRET_KEY=wave1-dotenv-only-prod-secret-key-xx",
                        "DJANGO_ALLOWED_HOSTS=example.com",
                        "DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com",
                        "CHURCHHUB_PUBLIC_URL=https://example.com",
                        "REDIS_URL=redis://127.0.0.1:6379/0",
                        "DATABASE_URL=postgres://churchhub:churchhub@127.0.0.1:5432/churchhub",
                        "CHURCHHUB_HEALTH_TOKEN=health-token-dotenv-only",
                        "SECURE_SSL_REDIRECT=true",
                        "CHURCHHUB_REQUIRE_REDIS=false",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            script = textwrap.dedent(
                f"""
                import os
                # Strip selection vars so only the temp .env can supply them
                for k in (
                    "DJANGO_ENV", "CHURCHHUB_ENV", "RENDER", "DYNO",
                    "PYTHONANYWHERE_SITE",
                ):
                    os.environ.pop(k, None)
                from pathlib import Path
                from church_system.env import load_dotenv, resolve_django_env
                load_dotenv(Path(r"{env_path}"))
                assert resolve_django_env() == "production", resolve_django_env()
                os.environ["DJANGO_SETTINGS_MODULE"] = "church_system.settings"
                import django
                django.setup()
                from django.conf import settings
                print("DJANGO_ENV=" + settings.DJANGO_ENV)
                print("SESSION_COOKIE_SECURE=" + str(bool(settings.SESSION_COOKIE_SECURE)))
                """
            )
            env = os.environ.copy()
            for k in ("DJANGO_ENV", "CHURCHHUB_ENV", "RENDER", "DYNO", "PYTHONANYWHERE_SITE"):
                env.pop(k, None)
            env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
            # Prevent real project .env from winning if process already had nothing —
            # load_dotenv in script runs first with our file; ensure_dotenv_loaded
            # in settings/__init__ may then load project .env but will not override
            # DJANGO_ENV already set from our temp file.
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                self.fail(
                    "dotenv-only production selection failed:\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                )
            self.assertIn("DJANGO_ENV=production", result.stdout)
            self.assertIn("SESSION_COOKIE_SECURE=True", result.stdout)
