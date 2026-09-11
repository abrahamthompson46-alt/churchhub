# ChurchHub — Offsite database + media backup (rclone)

**Status (Current):** Production VPS backups fail closed unless offsite is `app` (rclone) or `managed` (provider snapshots). Development stays local-only.

**Related:** `docs/WAVE1_BACKUP_RECOVERY_PLAN.md`, `manage.py backup_database`, `manage.py restore_drill`

## Local backups first

```bash
python manage.py backup_database --verify
# Optional skip of MEDIA_ROOT archive:
# python manage.py backup_database --verify --skip-media
```

Artifacts in `CHURCHHUB_BACKUP_DIR` (default `backups/`), mode `0600`:

- `churchhub_YYYYMMDD_HHMMSS.sql.gz` (or `.sql.gz.age`)
- `churchhub_YYYYMMDD_HHMMSS_media.tar.gz` (or `.tar.gz.age`)
- sibling `.sha256` when `--verify` is set

## Production offsite modes

| `CHURCHHUB_BACKUP_OFFSITE` | Meaning |
|----------------------------|---------|
| unset on VPS production | Treated as **app** — post-hook required |
| `app` | rclone (or another hook) must copy files off the app disk |
| `managed` | Operator relies on Render/host Postgres + media volume snapshots |
| `local` | Development only — rejected in production |

PythonAnywhere defaults to **managed** (no rclone assumed).

App-offsite production also requires age encryption unless `CHURCHHUB_BACKUP_ALLOW_PLAINTEXT=true`.

```ini
CHURCHHUB_BACKUP_OFFSITE=app
CHURCHHUB_BACKUP_ENCRYPT=true
CHURCHHUB_BACKUP_AGE_RECIPIENT=age1...
CHURCHHUB_BACKUP_POST_HOOK=/home/churchhub/apps/churchhub/deploy/backup/rclone-sync.sh
CHURCHHUB_BACKUP_RCLONE_REMOTE=gdrive:churchhub-backups/
CHURCHHUB_BACKUP_REQUIRE_OFFSITE=true
```

1. Install rclone and `age` on the VPS.  
2. `rclone config` — Google Drive service account, S3, MinIO, or R2.  
3. Dry-run: `bash deploy/backup/rclone-sync.sh --dry-run`

Keep the age **private** key off the app host (`CHURCHHUB_BACKUP_AGE_IDENTITY` on the restore/drill machine only).

## Restore drill (Current)

Create an empty throwaway database. Never use live `DATABASE_URL`.

```bash
python manage.py restore_drill \
  --input backups/churchhub_YYYYMMDD_HHMMSS.sql.gz \
  --media-input backups/churchhub_YYYYMMDD_HHMMSS_media.tar.gz \
  --operator "your-name" \
  --database-url "$CHURCHHUB_BACKUP_DRILL_DATABASE_URL"
```

`--dry-run` checks gzip and refuses if the URL matches the live database. A passed drill writes `backups/restore_drills/drill_*.json` (gitignored).

Encrypted dumps: decrypt to `.sql.gz` on the restore host, then drill.

## Rollback

- Development: unset `CHURCHHUB_BACKUP_POST_HOOK` / `CHURCHHUB_BACKUP_RCLONE_REMOTE`.  
- Production with provider snapshots only: `CHURCHHUB_BACKUP_OFFSITE=managed`.  
- Disable timer: `sudo systemctl disable --now churchhub-backup.timer`
