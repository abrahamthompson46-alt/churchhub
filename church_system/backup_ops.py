"""Shared helpers for database backup / restore management commands."""

from __future__ import annotations

import os
import subprocess
import tarfile
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


def post_hook_path() -> str:
    return (os.environ.get("CHURCHHUB_BACKUP_POST_HOOK") or "").strip()


def rclone_remote() -> str:
    return (
        (os.environ.get("CHURCHHUB_BACKUP_RCLONE_REMOTE") or "").strip()
        or (os.environ.get("RCLONE_REMOTE") or "").strip()
    )


def hook_uses_rclone(hook: str) -> bool:
    return "rclone" in Path(hook).name.lower()


def resolve_offsite_mode(
    *,
    production_like: bool = False,
    on_pythonanywhere: bool = False,
) -> str:
    """Return local | app | managed.

    *local* — write CHURCHHUB_BACKUP_DIR only (development).
    *app* — post-hook (rclone) must copy artifacts off the app disk.
    *managed* — operator relies on the host DB/media provider's snapshots.
    """
    raw = (os.environ.get("CHURCHHUB_BACKUP_OFFSITE") or "").strip().lower()
    if raw in {"app", "managed", "local"}:
        if raw == "local" and production_like and not on_pythonanywhere:
            raise CommandError(
                "CHURCHHUB_BACKUP_OFFSITE=local is not allowed in production. "
                "Use app (CHURCHHUB_BACKUP_POST_HOOK + rclone remote) or "
                "managed (provider snapshots, e.g. Render PostgreSQL backups)."
            )
        return raw
    if env_flag_true("CHURCHHUB_BACKUP_REQUIRE_OFFSITE", False):
        return "app"
    if not production_like:
        return "local"
    if on_pythonanywhere:
        return "managed"
    return "app"


def enforce_backup_policy(
    *,
    production_like: bool,
    on_pythonanywhere: bool,
    encrypt: bool,
) -> str:
    """Fail closed when production would keep the only copy on the app disk."""
    mode = resolve_offsite_mode(
        production_like=production_like,
        on_pythonanywhere=on_pythonanywhere,
    )
    if mode == "app":
        hook = post_hook_path()
        if not hook:
            raise CommandError(
                "Offsite backups are required (CHURCHHUB_BACKUP_OFFSITE=app). "
                "Set CHURCHHUB_BACKUP_POST_HOOK to deploy/backup/rclone-sync.sh "
                "and CHURCHHUB_BACKUP_RCLONE_REMOTE, or set "
                "CHURCHHUB_BACKUP_OFFSITE=managed if the database provider "
                "already snapshots off-host."
            )
        if hook_uses_rclone(hook) and not rclone_remote():
            raise CommandError(
                "rclone post-hook is set but CHURCHHUB_BACKUP_RCLONE_REMOTE is empty."
            )
        if production_like and not encrypt and not env_flag_true(
            "CHURCHHUB_BACKUP_ALLOW_PLAINTEXT", False
        ):
            raise CommandError(
                "Production app-offsite backups must be age-encrypted. "
                "Set CHURCHHUB_BACKUP_ENCRYPT=true and "
                "CHURCHHUB_BACKUP_AGE_RECIPIENT, or set "
                "CHURCHHUB_BACKUP_ALLOW_PLAINTEXT=true only as a temporary exception."
            )
    return mode


def run_post_hook(*backup_files: Path) -> None:
    hook = post_hook_path()
    paths = [p.resolve() for p in backup_files if p is not None]
    require = env_flag_true("CHURCHHUB_BACKUP_REQUIRE_OFFSITE", False)
    if not hook:
        if require:
            raise CommandError(
                "CHURCHHUB_BACKUP_REQUIRE_OFFSITE=true but CHURCHHUB_BACKUP_POST_HOOK is unset."
            )
        return
    if not paths:
        return
    for backup_file in paths:
        env = os.environ.copy()
        env["CHURCHHUB_BACKUP_FILE"] = str(backup_file)
        try:
            subprocess.run(
                [hook, str(backup_file)],
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


def archive_media_root(media_root: Path, dest: Path) -> int:
    """Write a gzip tar of MEDIA_ROOT. Returns the number of files archived."""
    count = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        if media_root.is_dir():
            for path in sorted(media_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    path.resolve().relative_to(media_root.resolve())
                except ValueError:
                    continue
                rel = path.relative_to(media_root)
                tar.add(path, arcname=str(Path("media") / rel), recursive=False)
                count += 1
        if count == 0:
            info = tarfile.TarInfo(name="media/.churchhub-empty")
            tar.addfile(info)
    return count


def encrypt_path_with_age(src: Path, dest: Path, recipient: str) -> None:
    try:
        completed = subprocess.run(
            ["age", "-r", recipient, "-o", str(dest), str(src)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CommandError("age not found. Install age to encrypt backups.") from exc
    if completed.returncode != 0:
        raise CommandError(
            "age encryption failed: "
            + (completed.stderr or completed.stdout or "")[:500]
        )


def database_identity(db: dict) -> tuple[str, str, str]:
    return (
        (db.get("HOST") or "localhost").strip().lower(),
        str(db.get("PORT") or "5432").strip(),
        (db.get("NAME") or "").strip().lower(),
    )


def parse_database_url(url: str) -> dict:
    import dj_database_url

    parsed = dj_database_url.parse(url.strip(), conn_max_age=0)
    if "postgresql" not in (parsed.get("ENGINE") or ""):
        raise CommandError("Drill database URL must be PostgreSQL.")
    return parsed


def count_tar_files(archive: Path) -> int:
    count = 0
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            if member.isfile() and not member.name.endswith(".churchhub-empty"):
                count += 1
    return count


def psql_restore_gzip(sql_gz: Path, db: dict) -> None:
    env = pg_env_from_settings(db)
    psql = psql_command(db)
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
        import gzip

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


def psql_scalar(db: dict, sql: str) -> str:
    env = pg_env_from_settings(db)
    cmd = psql_command(db) + ["-t", "-A", "-c", sql]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise CommandError("psql not found. Install PostgreSQL client tools.") from exc
    if completed.returncode != 0:
        raise CommandError(
            "psql query failed: " + (completed.stderr or completed.stdout or "")[:500]
        )
    return (completed.stdout or "").strip()


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
