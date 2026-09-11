#!/usr/bin/env bash
# Optional offsite sync for ChurchHub DB backups (rclone).
# Does NOTHING unless CHURCHHUB_BACKUP_RCLONE_REMOTE (or RCLONE_REMOTE) is set.
#
# Usage:
#   bash deploy/backup/rclone-sync.sh
#   bash deploy/backup/rclone-sync.sh --dry-run
#   CHURCHHUB_BACKUP_FILE=/path/to/file.sql.gz bash deploy/backup/rclone-sync.sh
#
# Typical post-hook:
#   CHURCHHUB_BACKUP_POST_HOOK=/path/to/repo/deploy/backup/rclone-sync.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

REMOTE="${CHURCHHUB_BACKUP_RCLONE_REMOTE:-${RCLONE_REMOTE:-}}"
MODE="${CHURCHHUB_BACKUP_OFFSITE:-}"
REQUIRE="$(echo "${CHURCHHUB_BACKUP_REQUIRE_OFFSITE:-false}" | tr '[:upper:]' '[:lower:]')"
if [[ -z "$REMOTE" ]]; then
  if [[ "$MODE" == "app" || "$REQUIRE" == "true" || "$REQUIRE" == "1" || "$REQUIRE" == "yes" ]]; then
    echo "ERROR: offsite required but CHURCHHUB_BACKUP_RCLONE_REMOTE is unset." >&2
    exit 1
  fi
  echo "Offsite sync skipped: CHURCHHUB_BACKUP_RCLONE_REMOTE unset."
  exit 0
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "ERROR: rclone not installed" >&2
  exit 1
fi

LOCAL_DIR="${CHURCHHUB_BACKUP_DIR:-$ROOT/backups}"
FILE="${CHURCHHUB_BACKUP_FILE:-${1:-}}"

ARGS=(copy)
if [[ "$DRY_RUN" -eq 1 ]]; then
  ARGS+=(--dry-run)
fi
ARGS+=(--checksum -v)

if [[ -n "$FILE" && -f "$FILE" ]]; then
  echo "rclone ${ARGS[*]} $FILE $REMOTE"
  rclone "${ARGS[@]}" "$FILE" "$REMOTE"
  if [[ -f "${FILE}.sha256" ]]; then
    rclone "${ARGS[@]}" "${FILE}.sha256" "$REMOTE"
  fi
else
  echo "rclone ${ARGS[*]} $LOCAL_DIR $REMOTE"
  rclone "${ARGS[@]}" "$LOCAL_DIR" "$REMOTE"
fi

echo "Offsite sync finished."
