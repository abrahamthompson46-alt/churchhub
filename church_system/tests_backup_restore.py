"""Backup / restore configuration and safety tests."""

from __future__ import annotations

import gzip
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from church_system.backup_ops import (
    CONFIRM_DESTROY,
    encryption_requested,
    resolve_backup_dir,
    resolve_retention,
)


class BackupEnvResolutionTests(SimpleTestCase):
    def test_backup_dir_cli_wins(self):
        previous = os.environ.get("CHURCHHUB_BACKUP_DIR")
        os.environ["CHURCHHUB_BACKUP_DIR"] = "/from/env"
        try:
            self.assertEqual(resolve_backup_dir("/from/cli"), Path("/from/cli"))
        finally:
            if previous is None:
                os.environ.pop("CHURCHHUB_BACKUP_DIR", None)
            else:
                os.environ["CHURCHHUB_BACKUP_DIR"] = previous

    def test_backup_dir_from_env(self):
        previous = os.environ.pop("CHURCHHUB_BACKUP_DIR", None)
        os.environ["CHURCHHUB_BACKUP_DIR"] = "/var/backups/churchhub"
        try:
            self.assertEqual(resolve_backup_dir(None), Path("/var/backups/churchhub"))
        finally:
            os.environ.pop("CHURCHHUB_BACKUP_DIR", None)
            if previous is not None:
                os.environ["CHURCHHUB_BACKUP_DIR"] = previous

    def test_backup_dir_default(self):
        previous = os.environ.pop("CHURCHHUB_BACKUP_DIR", None)
        try:
            self.assertEqual(resolve_backup_dir(None), Path("backups"))
        finally:
            if previous is not None:
                os.environ["CHURCHHUB_BACKUP_DIR"] = previous

    def test_retention_env_and_default(self):
        previous = os.environ.pop("CHURCHHUB_BACKUP_RETENTION_DAYS", None)
        try:
            self.assertEqual(resolve_retention(None), 30)
            os.environ["CHURCHHUB_BACKUP_RETENTION_DAYS"] = "14"
            self.assertEqual(resolve_retention(None), 14)
            self.assertEqual(resolve_retention(7), 7)
        finally:
            os.environ.pop("CHURCHHUB_BACKUP_RETENTION_DAYS", None)
            if previous is not None:
                os.environ["CHURCHHUB_BACKUP_RETENTION_DAYS"] = previous

    def test_encryption_flag(self):
        previous = os.environ.pop("CHURCHHUB_BACKUP_ENCRYPT", None)
        try:
            self.assertFalse(encryption_requested(cli_encrypt=False))
            self.assertTrue(encryption_requested(cli_encrypt=True))
            os.environ["CHURCHHUB_BACKUP_ENCRYPT"] = "true"
            self.assertTrue(encryption_requested(cli_encrypt=False))
        finally:
            os.environ.pop("CHURCHHUB_BACKUP_ENCRYPT", None)
            if previous is not None:
                os.environ["CHURCHHUB_BACKUP_ENCRYPT"] = previous


@override_settings(
    DEBUG=True,
    DJANGO_ENV="development",
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "churchhub",
            "USER": "churchhub",
            "PASSWORD": "x",
            "HOST": "127.0.0.1",
            "PORT": "5432",
        }
    },
)
class BackupCommandTests(SimpleTestCase):
    def test_backup_streams_and_writes_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            proc = mock.Mock()
            proc.stdout.read.side_effect = [b"CREATE TABLE t();\n", b""]
            proc.stderr.read.return_value = b""
            proc.wait.return_value = 0
            proc.poll.return_value = 0

            with mock.patch("subprocess.Popen", return_value=proc) as popen:
                call_command(
                    "backup_database",
                    "--output-dir",
                    str(out_dir),
                    "--retention",
                    "0",
                    "--verify",
                )
                self.assertTrue(popen.called)
                self.assertEqual(popen.call_args[0][0][0], "pg_dump")

            files = list(out_dir.glob("churchhub_*.sql.gz"))
            self.assertEqual(len(files), 1)
            self.assertGreater(files[0].stat().st_size, 0)
            with gzip.open(files[0], "rb") as gz:
                self.assertIn(b"CREATE TABLE", gz.read())
            self.assertEqual(len(list(out_dir.glob("*.sha256"))), 1)

    def test_encrypt_without_recipient_fails(self):
        previous_r = os.environ.pop("CHURCHHUB_BACKUP_AGE_RECIPIENT", None)
        previous_e = os.environ.pop("CHURCHHUB_BACKUP_ENCRYPT", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(CommandError) as ctx:
                    call_command(
                        "backup_database",
                        "--output-dir",
                        tmp,
                        "--retention",
                        "0",
                        "--encrypt",
                    )
                self.assertIn("AGE_RECIPIENT", str(ctx.exception))
        finally:
            if previous_r is not None:
                os.environ["CHURCHHUB_BACKUP_AGE_RECIPIENT"] = previous_r
            if previous_e is not None:
                os.environ["CHURCHHUB_BACKUP_ENCRYPT"] = previous_e


@override_settings(
    DEBUG=True,
    DJANGO_ENV="development",
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "churchhub",
            "USER": "u",
            "PASSWORD": "p",
            "HOST": "127.0.0.1",
            "PORT": "5432",
        }
    },
)
class RestoreSafetyTests(SimpleTestCase):
    def test_restore_requires_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "churchhub_test.sql.gz"
            with gzip.open(path, "wb") as gz:
                gz.write(b"SELECT 1;\n")
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "restore_database",
                    f"--input={path}",
                    "--confirm=nope",
                    "--no-input",
                    "--allow-any-path",
                )
            self.assertIn(CONFIRM_DESTROY, str(ctx.exception))

    @override_settings(DEBUG=False, DJANGO_ENV="production")
    def test_restore_production_requires_extra_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "churchhub_test.sql.gz"
            with gzip.open(path, "wb") as gz:
                gz.write(b"SELECT 1;\n")
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "restore_database",
                    f"--input={path}",
                    f"--confirm={CONFIRM_DESTROY}",
                    "--no-input",
                    "--allow-any-path",
                )
            self.assertIn("i-understand-production", str(ctx.exception))

    def test_restore_rejects_path_outside_backup_dir(self):
        with tempfile.TemporaryDirectory() as backup_root:
            with tempfile.TemporaryDirectory() as other:
                path = Path(other) / "churchhub_test.sql.gz"
                with gzip.open(path, "wb") as gz:
                    gz.write(b"SELECT 1;\n")
                previous = os.environ.get("CHURCHHUB_BACKUP_DIR")
                os.environ["CHURCHHUB_BACKUP_DIR"] = backup_root
                try:
                    with self.assertRaises(CommandError) as ctx:
                        call_command(
                            "restore_database",
                            f"--input={path}",
                            f"--confirm={CONFIRM_DESTROY}",
                            "--no-input",
                        )
                    self.assertIn("outside backup dir", str(ctx.exception))
                finally:
                    if previous is None:
                        os.environ.pop("CHURCHHUB_BACKUP_DIR", None)
                    else:
                        os.environ["CHURCHHUB_BACKUP_DIR"] = previous
