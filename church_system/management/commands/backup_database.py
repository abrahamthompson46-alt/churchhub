"""Backup PostgreSQL database to a local file (streaming; optional age encryption)."""

from __future__ import annotations

import gzip
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from church_system.backup_ops import (
    age_recipient,
    encryption_requested,
    ensure_secure_dir,
    pg_dump_command,
    pg_env_from_settings,
    resolve_backup_dir,
    resolve_retention,
    run_post_hook,
    secure_file,
    verify_gzip_file,
    write_sha256,
)


class Command(BaseCommand):
    help = (
        "Create a PostgreSQL dump (pg_dump) for disaster recovery. "
        "Streams pg_dump → gzip (never loads the full dump into memory). "
        "Optional age encryption via --encrypt / CHURCHHUB_BACKUP_ENCRYPT."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=None,
            help=(
                "Directory for backup files. "
                "Default: CHURCHHUB_BACKUP_DIR or backups/"
            ),
        )
        parser.add_argument(
            "--retention",
            type=int,
            default=None,
            help=(
                "Delete backups older than N days (0 = keep all). "
                "Default: CHURCHHUB_BACKUP_RETENTION_DAYS or 30."
            ),
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify gzip integrity and write a sibling .sha256 checksum.",
        )
        parser.add_argument(
            "--encrypt",
            action="store_true",
            help="Encrypt with age (requires CHURCHHUB_BACKUP_AGE_RECIPIENT).",
        )

    def handle(self, *args, **options):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in engine:
            raise CommandError(
                "backup_database requires PostgreSQL. Current engine: " + engine
            )

        db = settings.DATABASES["default"]
        output_dir = resolve_backup_dir(options.get("output_dir"))
        ensure_secure_dir(output_dir)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        encrypt = encryption_requested(cli_encrypt=bool(options.get("encrypt")))
        recipient = age_recipient()
        if encrypt and not recipient:
            raise CommandError(
                "Encryption requested but CHURCHHUB_BACKUP_AGE_RECIPIENT is unset."
            )

        plain_name = f"churchhub_{stamp}.sql.gz"
        if encrypt:
            outfile = output_dir / f"{plain_name}.age"
        else:
            outfile = output_dir / plain_name

        env = pg_env_from_settings(db)
        dump_cmd = pg_dump_command(db)

        self.stdout.write(f"Writing backup to {outfile} ...")
        try:
            if encrypt:
                self._stream_dump_gzip_age(dump_cmd, env, outfile, recipient)
            else:
                self._stream_dump_gzip(dump_cmd, env, outfile)
        except FileNotFoundError as exc:
            missing = getattr(exc, "filename", None) or "pg_dump/age"
            raise CommandError(
                f"Required tool not found ({missing}). "
                "Install PostgreSQL client tools"
                + (" and age" if encrypt else "")
                + "."
            ) from exc
        except subprocess.CalledProcessError as exc:
            if outfile.exists():
                outfile.unlink(missing_ok=True)
            raise CommandError(f"Backup pipeline failed with exit code {exc.returncode}") from exc
        except CommandError:
            if outfile.exists():
                outfile.unlink(missing_ok=True)
            raise

        secure_file(outfile)
        if not outfile.is_file() or outfile.stat().st_size <= 0:
            raise CommandError(f"Backup file missing or empty: {outfile}")

        if options.get("verify"):
            if encrypt:
                # Ciphertext: checksum only (cannot gzip -t without private key).
                digest = write_sha256(outfile)
                self.stdout.write(f"Checksum written: {digest}")
            else:
                verify_gzip_file(outfile)
                digest = write_sha256(outfile)
                self.stdout.write(f"Verified gzip; checksum: {digest}")

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {outfile}"))

        run_post_hook(outfile)

        retention = resolve_retention(options.get("retention"))
        if retention > 0:
            removed = self._prune(output_dir, retention)
            if removed:
                self.stdout.write(
                    f"Removed {removed} backup(s) older than {retention} days."
                )

    def _stream_dump_gzip(self, dump_cmd: list[str], env: dict, outfile: Path) -> None:
        """Stream pg_dump stdout through gzip to outfile (no full in-memory dump)."""
        dump = subprocess.Popen(
            dump_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert dump.stdout is not None
        try:
            with outfile.open("wb") as fh:
                with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
                    while True:
                        chunk = dump.stdout.read(1024 * 1024)
                        if not chunk:
                            break
                        gz.write(chunk)
            stderr = dump.stderr.read().decode("utf-8", errors="replace") if dump.stderr else ""
            rc = dump.wait()
            if rc != 0:
                raise CommandError(
                    f"pg_dump failed with exit code {rc}: {stderr[:500]}"
                )
        finally:
            if dump.poll() is None:
                dump.kill()

    def _stream_dump_gzip_age(
        self, dump_cmd: list[str], env: dict, outfile: Path, recipient: str
    ) -> None:
        """
        Stream pg_dump → Python gzip → temp .sql.gz → age encrypt to outfile.

        Final on-disk artifact is ciphertext only; plaintext temp is deleted.
        Dump bytes are never fully buffered in RAM.
        """
        with tempfile.NamedTemporaryFile(
            prefix="churchhub_bak_", suffix=".sql.gz", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self._stream_dump_gzip(dump_cmd, env, tmp_path)
            secure_file(tmp_path)
            age_cmd = ["age", "-r", recipient, "-o", str(outfile), str(tmp_path)]
            completed = subprocess.run(
                age_cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise CommandError(
                    "age encryption failed: "
                    + (completed.stderr or completed.stdout or "")[:500]
                )
        finally:
            tmp_path.unlink(missing_ok=True)

    @staticmethod
    def _prune(output_dir: Path, retention_days: int) -> int:
        cutoff = datetime.now().timestamp() - (retention_days * 86400)
        removed = 0
        patterns = (
            "churchhub_*.sql.gz",
            "churchhub_*.sql.gz.age",
            "churchhub_*.sql.gz.sha256",
            "churchhub_*.sql.gz.age.sha256",
        )
        seen: set[Path] = set()
        for pattern in patterns:
            for path in output_dir.glob(pattern):
                if path in seen:
                    continue
                seen.add(path)
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        return removed
