# Wave 1 — Backup & Disaster Recovery Hardening Plan

**Status:** IMPLEMENTED  
**Date:** 6 August 2026  
**Detail:** Original plan below; §10 lists what shipped.

---

## 10. Implementation shipped

| Path | Role |
|------|------|
| `church_system/backup_ops.py` | Shared env/path/perm/hook helpers |
| `church_system/management/commands/backup_database.py` | Streaming dump; verify; optional age; post-hook |
| `church_system/management/commands/restore_database.py` | Safe restore with confirm gates |
| `church_system/tasks.py` | Beat task honors `CHURCHHUB_BACKUP_*` + `--verify` |
| `church_system/tests_backup_restore.py` | Env + safety tests |
| `deploy/systemd/churchhub-backup.service` / `.timer` | Daily oneshot |
| `deploy/backup/rclone-sync.sh` + `README.md` | Opt-in offsite |
| `scripts/backup.sh` | Env-aware + `--verify` |
| Docs | `SECURITY.md`, `DEPLOYMENT_GUIDE.md`, runbook, DEPLOYMENT_NOTES, `.env.example` |

**Encryption:** age (optional). **Upload:** never without `CHURCHHUB_BACKUP_RCLONE_REMOTE` / post-hook.

---

## 1. Goals

1. Keep existing `manage.py backup_database` compatible.
2. Safe `restore_database` with hard confirmation.
3. Configurable dir, `0600` files, optional age encryption.
4. Daily systemd timer + documented rclone readiness.
5. Tests + SECURITY / DEPLOYMENT docs.

(See prior sections in git history for full design narrative.)
