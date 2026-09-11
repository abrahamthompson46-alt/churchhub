"""Restore a backup into a throwaway database and record the drill."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from church_system.backup_ops import (
    count_tar_files,
    database_identity,
    ensure_secure_dir,
    parse_database_url,
    path_is_under,
    psql_restore_gzip,
    psql_scalar,
    resolve_backup_dir,
    secure_file,
    verify_gzip_file,
)


class Command(BaseCommand):
    help = (
        "Restore a ChurchHub dump into a dedicated drill database (never the live "
        "DATABASE_URL), verify django_migrations, and write a drill log. "
        "Create an empty PostgreSQL database first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="Path to churchhub_*.sql.gz (not .age — decrypt first if needed).",
        )
        parser.add_argument(
            "--operator",
            required=True,
            help="Who ran the drill (name or username). Stored in the drill log.",
        )
        parser.add_argument(
            "--database-url",
            default="",
            help="Throwaway Postgres URL. Default: CHURCHHUB_BACKUP_DRILL_DATABASE_URL.",
        )
        parser.add_argument(
            "--media-input",
            default="",
            help="Optional churchhub_*_media.tar.gz to count files (not extracted to MEDIA_ROOT).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate paths and URL mismatch only; do not restore or write a log.",
        )
        parser.add_argument(
            "--allow-any-path",
            action="store_true",
            help="Allow input outside CHURCHHUB_BACKUP_DIR.",
        )
        parser.add_argument(
            "--reset-schema",
            action="store_true",
            default=True,
            help="DROP SCHEMA public CASCADE on the drill DB before restore (default).",
        )
        parser.add_argument(
            "--no-reset-schema",
            action="store_false",
            dest="reset_schema",
            help="Do not drop public schema on the drill database.",
        )

    def handle(self, *args, **options):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in engine:
            raise CommandError(
                "restore_drill requires PostgreSQL. Current engine: " + engine
            )

        src = Path(options["input"]).expanduser()
        if not src.is_file():
            raise CommandError(f"Backup file not found: {src}")
        if src.name.endswith(".age"):
            raise CommandError(
                "Decrypt the age backup to .sql.gz first (age -d -i identity), "
                "then pass the plaintext gzip. Keep the private key off the app host."
            )
        if not src.name.endswith(".sql.gz"):
            raise CommandError("Expected a churchhub_*.sql.gz dump.")

        if not options.get("allow_any_path"):
            backup_root = resolve_backup_dir(None)
            ensure_secure_dir(backup_root)
            if not path_is_under(src, backup_root):
                raise CommandError(
                    f"Input {src} is outside backup dir {backup_root.resolve()}. "
                    "Move the file there or pass --allow-any-path."
                )

        drill_url = (
            (options.get("database_url") or "").strip()
            or (os.environ.get("CHURCHHUB_BACKUP_DRILL_DATABASE_URL") or "").strip()
        )
        if not drill_url:
            raise CommandError(
                "Set CHURCHHUB_BACKUP_DRILL_DATABASE_URL or pass --database-url "
                "to an empty throwaway database (not production)."
            )

        live = database_identity(settings.DATABASES["default"])
        drill_db = parse_database_url(drill_url)
        drill = database_identity(drill_db)
        if not drill[2]:
            raise CommandError("Drill database URL has no database name.")
        if drill == live:
            raise CommandError(
                "Refusing restore drill: target is the live database "
                f"({live[2]} on {live[0]}:{live[1]}). Use a separate drill database."
            )

        media_path = None
        media_arg = (options.get("media_input") or "").strip()
        if media_arg:
            media_path = Path(media_arg).expanduser()
            if not media_path.is_file():
                raise CommandError(f"Media archive not found: {media_path}")
            if media_path.name.endswith(".age"):
                raise CommandError("Decrypt the media .age archive before the drill.")

        verify_gzip_file(src)
        media_count = None
        if media_path is not None:
            media_count = count_tar_files(media_path)

        self.stdout.write(
            f"Drill target {drill[2]} on {drill[0]}:{drill[1]} "
            f"(live is {live[2]} on {live[0]}:{live[1]})"
        )

        if options.get("dry_run"):
            self.stdout.write(self.style.SUCCESS("Dry-run OK — dump is readable gzip."))
            if media_count is not None:
                self.stdout.write(f"Media archive file count: {media_count}")
            return

        if options.get("reset_schema"):
            psql_scalar(
                drill_db,
                "DROP SCHEMA IF EXISTS public CASCADE; "
                "CREATE SCHEMA public; "
                "GRANT ALL ON SCHEMA public TO CURRENT_USER;",
            )

        psql_restore_gzip(src, drill_db)
        migrations = psql_scalar(drill_db, "SELECT COUNT(*) FROM django_migrations;")
        if not migrations.isdigit() or int(migrations) < 1:
            raise CommandError(
                f"Drill restore did not yield django_migrations rows (got {migrations!r})."
            )

        log_dir = resolve_backup_dir(None) / "restore_drills"
        ensure_secure_dir(log_dir)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"drill_{stamp}.json"
        payload = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "operator": options["operator"],
            "input": src.name,
            "media_input": media_path.name if media_path else "",
            "media_files": media_count,
            "target_database": drill[2],
            "target_host": drill[0],
            "live_database": live[2],
            "migrations_count": int(migrations),
            "result": "passed",
        }
        log_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        secure_file(log_path)
        self.stdout.write(self.style.SUCCESS(f"Restore drill passed: {log_path}"))
        self.stdout.write(
            "Smoke-check the drill DB separately if needed, then drop it. "
            "Do not point DATABASE_URL at the drill database."
        )
