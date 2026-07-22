#!/usr/bin/env bash
# Local / ops wrapper around manage.py backup_database
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-backups}"
RETENTION="${2:-30}"
python manage.py backup_database --output-dir "$OUT" --retention "$RETENTION"
