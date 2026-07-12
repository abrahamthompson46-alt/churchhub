"""Backup PostgreSQL database to a local file."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a PostgreSQL dump (pg_dump) for disaster recovery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="backups",
            help="Directory for backup files (default: backups/)",
        )
        parser.add_argument(
            "--retention",
            type=int,
            default=30,
            help="Delete backups older than N days (0 = keep all).",
        )

    def handle(self *args, **options):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in engine:
            raise CommandError("backup_database requires PostgreSQL. Current engine: " + engine)

        db = settings.DATABASES["default"]
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = output_dir / f"churchhub_{stamp}.sql.gz"

        env = os.environ.copy()
        if db.get("PASSWORD"):
            env["PGPASSWORD"] = db["PASSWORD"]

        cmd = [
            "pg_dump",
            "-h", db.get("HOST", "localhost"),
            "-p", str(db.get("PORT", "5432")),
            "-U", db.get("USER", "churchhub"),
            "-d", db.get("NAME", "churchhub"),
            "--no-owner",
            "--no-acl",
        ]

        self.stdout.write(f"Writing backup to {outfile} ...")
        try:
            with open(outfile, "wb") as fh:
                dump = subprocess.run(cmd, env=env, check=True, stdout=subprocess.PIPE)
                import gzip

                with gzip.GzipFile(fileobj=fh, mode="wb") as gz:
                    gz.write(dump.stdout)
        except FileNotFoundError as exc:
            raise CommandError("pg_dump not found. Install PostgreSQL client tools.") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"pg_dump failed with exit code {exc.returncode}") from exc

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {outfile}"))

        retention = options["retention"]
        if retention > 0:
            cutoff = datetime.now().timestamp() - (retention * 86400)
            removed = 0
            for path in output_dir.glob("churchhub_*.sql.gz"):
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            if removed:
                self.stdout.write(f"Removed {removed} backup(s) older than {retention} days.")
