"""Restore PostgreSQL from a ChurchHub .sql.gz (or .sql.gz.age) backup."""

from __future__ import annotations

import gzip
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from church_system.backup_ops import (
    CONFIRM_DESTROY,
    ensure_secure_dir,
    path_is_under,
    pg_env_from_settings,
    psql_command,
    resolve_backup_dir,
    secure_file,
)


class Command(BaseCommand):
    help = (
        "Restore PostgreSQL from churchhub_*.sql.gz or churchhub_*.sql.gz.age. "
        "DESTRUCTIVE — requires --confirm DESTROY_LOCAL_DATA."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="Path to .sql.gz or .sql.gz.age backup file.",
        )
        parser.add_argument(
            "--confirm",
            default="",
            help=f'Must be exactly "{CONFIRM_DESTROY}" to proceed.',
        )
        parser.add_argument(
            "--i-understand-production",
            action="store_true",
            help="Required when DJANGO_ENV=production or DEBUG is False.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip interactive yes/no (still requires --confirm).",
        )
        parser.add_argument(
            "--age-identity",
            default="",
            help="Path to age private key file (for .age backups). "
            "Or set CHURCHHUB_BACKUP_AGE_IDENTITY.",
        )
        parser.add_argument(
            "--allow-any-path",
            action="store_true",
            help="Allow input outside CHURCHHUB_BACKUP_DIR / backups/ (default: restricted).",
        )

    def handle(self, *args, **options):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in engine:
            raise CommandError(
                "restore_database requires PostgreSQL. Current engine: " + engine
            )

        if options.get("confirm") != CONFIRM_DESTROY:
            raise CommandError(
                f'Refuse to restore without --confirm {CONFIRM_DESTROY} '
                "(this overwrites the configured database)."
            )

        production_like = (not settings.DEBUG) or (
            getattr(settings, "DJANGO_ENV", "") == "production"
        )
        if production_like and not options.get("i_understand_production"):
            raise CommandError(
                "Production/non-DEBUG restore refused. "
                "Re-run with --i-understand-production after verifying DATABASE_URL "
                "points at the intended target (prefer staging)."
            )

        if not options.get("no_input"):
            self.stdout.write(
                self.style.WARNING(
                    "This will overwrite the database configured in Django settings."
                )
            )
            answer = input('Type "yes" to continue: ').strip().lower()
            if answer != "yes":
                raise CommandError("Restore aborted.")

        src = Path(options["input"]).expanduser()
        if not src.is_file():
            raise CommandError(f"Backup file not found: {src}")

        if not options.get("allow_any_path"):
            backup_root = resolve_backup_dir(None)
            ensure_secure_dir(backup_root)
            if not path_is_under(src, backup_root):
                raise CommandError(
                    f"Input {src} is outside backup dir {backup_root.resolve()}. "
                    "Move the file there or pass --allow-any-path."
                )

        name = src.name
        if not (name.endswith(".sql.gz") or name.endswith(".sql.gz.age")):
            raise CommandError(
                "Unsupported backup type. Expected *.sql.gz or *.sql.gz.age"
            )

        db = settings.DATABASES["default"]
        env = pg_env_from_settings(db)
        psql = psql_command(db)

        tmp_plain: Path | None = None
        try:
            if name.endswith(".sql.gz.age"):
                identity = (
                    (options.get("age_identity") or "").strip()
                    or (os.environ.get("CHURCHHUB_BACKUP_AGE_IDENTITY") or "").strip()
                )
                if not identity:
                    raise CommandError(
                        "Encrypted backup requires --age-identity or "
                        "CHURCHHUB_BACKUP_AGE_IDENTITY (path to age private key)."
                    )
                identity_path = Path(identity).expanduser()
                if not identity_path.is_file():
                    raise CommandError(f"age identity file not found: {identity_path}")
                tmp_plain = self._decrypt_age(src, identity_path)
                sql_gz = tmp_plain
            else:
                sql_gz = src

            self._verify_gzip(sql_gz)
            self.stdout.write(f"Restoring {sql_gz} into database {db.get('NAME')} ...")
            self._psql_restore(sql_gz, psql, env)
        finally:
            if tmp_plain is not None:
                tmp_plain.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS("Restore complete."))
        self.stdout.write(
            "Smoke-check: login, one church-scoped list, one transaction detail."
        )

    def _decrypt_age(self, src: Path, identity: Path) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix="churchhub_restore_", suffix=".sql.gz", delete=False
        ) as tmp:
            out = Path(tmp.name)
        try:
            completed = subprocess.run(
                ["age", "-d", "-i", str(identity), "-o", str(out), str(src)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                out.unlink(missing_ok=True)
                raise CommandError(
                    "age decrypt failed: "
                    + (completed.stderr or completed.stdout or "")[:500]
                )
            secure_file(out)
            return out
        except FileNotFoundError as exc:
            out.unlink(missing_ok=True)
            raise CommandError(
                "age not found. Install age to restore encrypted backups."
            ) from exc

    @staticmethod
    def _verify_gzip(path: Path) -> None:
        try:
            with gzip.open(path, "rb") as gz:
                gz.read(64)
        except OSError as exc:
            raise CommandError(f"Invalid gzip backup: {path}: {exc}") from exc

    def _psql_restore(self, sql_gz: Path, psql: list[str], env: dict) -> None:
        try:
            psql_proc = subprocess.Popen(
                psql,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CommandError("psql not found. Install PostgreSQL client tools.") from exc

        assert psql_proc.stdin is not None
        try:
            with gzip.open(sql_gz, "rb") as gz:
                while True:
                    chunk = gz.read(1024 * 1024)
                    if not chunk:
                        break
                    psql_proc.stdin.write(chunk)
            psql_proc.stdin.close()
            _stdout, stderr = psql_proc.communicate()
            if psql_proc.returncode != 0:
                err = (stderr or b"").decode("utf-8", errors="replace")
                raise CommandError(f"psql restore failed: {err[:800]}")
        finally:
            if psql_proc.poll() is None:
                psql_proc.kill()
