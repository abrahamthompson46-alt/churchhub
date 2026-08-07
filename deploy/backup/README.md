# ChurchHub — Offsite database backup (rclone)

**Status:** Opt-in only. No upload runs unless a remote is configured.  
**Related:** `docs/WAVE1_BACKUP_RECOVERY_PLAN.md`, `manage.py backup_database`

## Local backups first

```bash
python manage.py backup_database --verify
# Optional encryption (age public recipient in .env):
# CHURCHHUB_BACKUP_ENCRYPT=true
# CHURCHHUB_BACKUP_AGE_RECIPIENT=age1...
```

Files land in `CHURCHHUB_BACKUP_DIR` (default `backups/`) mode `0600`.

## rclone remote (Google Drive / S3)

1. Install rclone on the VPS.  
2. `rclone config` — create a remote (Google Drive service account recommended for unattended; or S3/MinIO/R2).  
3. Set in `.env`:

```ini
CHURCHHUB_BACKUP_RCLONE_REMOTE=gdrive:churchhub-backups/
# or:  s3churchhub:bucket/churchhub-db/
CHURCHHUB_BACKUP_POST_HOOK=/home/churchhub/apps/churchhub/deploy/backup/rclone-sync.sh
# Optional: fail backup if hook fails
# CHURCHHUB_BACKUP_REQUIRE_OFFSITE=true
```

4. Dry-run:

```bash
bash deploy/backup/rclone-sync.sh --dry-run
```

## Encryption at rest

**Recommended:** age-encrypt locally (`CHURCHHUB_BACKUP_ENCRYPT=true`) then rclone plaintext or ciphertext files. Private age key stays offline / on restore hosts only (`CHURCHHUB_BACKUP_AGE_IDENTITY`).

**Alternative:** rclone `crypt` remote (encrypts in transit to remote). Prefer age-at-source so any remote is ciphertext without rclone crypt complexity.

## Rollback

- Unset `CHURCHHUB_BACKUP_POST_HOOK` / `CHURCHHUB_BACKUP_RCLONE_REMOTE` — backups stay local.  
- `CHURCHHUB_BACKUP_ENCRYPT=false` — resume plaintext `.sql.gz`.  
- Disable timer: `sudo systemctl disable --now churchhub-backup.timer`
