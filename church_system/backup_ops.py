"""Shared helpers for database backup / restore management commands."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from django.core.management.base import CommandError

CONFIRM_DESTROY = "DESTROY_LOCAL_DATA"
BACKUP_FILE_MODE = 0o600
BACKUP_DIR_MODE = 0o700


def resolve_backup_dir(cli_value: str | None = None) -> Path:
    """CLI --output-dir wins, then CHURCHHUB_BACKUP_DIR, else backups/."""
    if cli_value:
        return Path(cli_value)
    env = (os.environ.get("CHURCHHUB_BACKUP_DIR") or "").strip()
    if env:
        return Path(env)
    return Path("backups")


def resolve_retention(cli_value: int | None = None) -> int:
    """CLI --retention wins, then CHURCHHUB_BACKUP_RETENTION_DAYS, else 30."""
    if cli_value is not None:
        return int(cli_value)
    raw = (os.environ.get("CHURCHHUB_BACKUP_RETENTION_DAYS") or "").strip()
    if raw:
        return int(raw)
    return 30


def env_flag_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes")


def encryption_requested(*, cli_encrypt: bool = False) -> bool:
    return bool(cli_encrypt) or env_flag_true("CHURCHHUB_BACKUP_ENCRYPT", False)


def age_recipient() -> str:
    return (os.environ.get("CHURCHHUB_BACKUP_AGE_RECIPIENT") or "").strip()


def ensure_secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, BACKUP_DIR_MODE)
    except OSError:
        # Windows / restricted FS may not support Unix modes.
        pass


def secure_file(path: Path) -> None:
    try:
        os.chmod(path, BACKUP_FILE_MODE)
    except OSError:
        pass


def write_sha256(path: Path) -> Path:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    digest_path = Path(str(path) + ".sha256")
    digest_path.write_text(f"{h.hexdigest()}  {path.name}\n", encoding="utf-8")
    secure_file(digest_path)
    return digest_path


def verify_gzip_file(path: Path) -> None:
    """Raise CommandError if gzip stream is corrupt."""
    import gzip

    try:
        with gzip.open(path, "rb") as gz:
            while gz.read(1024 * 1024):
                pass
    except OSError as exc:
        raise CommandError(f"Backup gzip verification failed: {path}: {exc}") from exc


def run_post_hook(backup_file: Path) -> None:
    hook = (os.environ.get("CHURCHHUB_BACKUP_POST_HOOK") or "").strip()
    require = env_flag_true("CHURCHHUB_BACKUP_REQUIRE_OFFSITE", False)
    if not hook:
        if require:
            raise CommandError(
                "CHURCHHUB_BACKUP_REQUIRE_OFFSITE=true but CHURCHHUB_BACKUP_POST_HOOK is unset."
            )
        return
    env = os.environ.copy()
    env["CHURCHHUB_BACKUP_FILE"] = str(backup_file.resolve())
    try:
        subprocess.run(
            [hook, str(backup_file.resolve())],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Backup post-hook not found: {hook}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise CommandError(
            f"Backup post-hook failed (exit {exc.returncode}): {detail[:500]}"
        ) from exc


def path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def pg_env_from_settings(db: dict) -> dict:
    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = db["PASSWORD"]
    return env


def pg_dump_command(db: dict) -> list[str]:
    return [
        "pg_dump",
        "-h",
        db.get("HOST") or "localhost",
        "-p",
        str(db.get("PORT") or "5432"),
        "-U",
        db.get("USER") or "churchhub",
        "-d",
        db.get("NAME") or "churchhub",
        "--no-owner",
        "--no-acl",
    ]


def psql_command(db: dict) -> list[str]:
    return [
        "psql",
        "-h",
        db.get("HOST") or "localhost",
        "-p",
        str(db.get("PORT") or "5432"),
        "-U",
        db.get("USER") or "churchhub",
        "-d",
        db.get("NAME") or "churchhub",
        "-v",
        "ON_ERROR_STOP=1",
    ]
