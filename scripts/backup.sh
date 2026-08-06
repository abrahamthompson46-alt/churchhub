#!/usr/bin/env bash
# Local / ops wrapper around manage.py backup_database
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-${CHURCHHUB_BACKUP_DIR:-backups}}"
RETENTION="${2:-${CHURCHHUB_BACKUP_RETENTION_DAYS:-30}}"
python manage.py backup_database --output-dir "$OUT" --retention "$RETENTION" --verify
