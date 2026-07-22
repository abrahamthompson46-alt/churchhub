#!/usr/bin/env bash
# Self-host deploy helper (VPS). Run from repo root after venv + .env are ready.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export DJANGO_ENV="${DJANGO_ENV:-production}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-church_system.settings}"

echo "==> migrate"
python manage.py migrate --noinput
echo "==> seed_permissions"
python manage.py seed_permissions
echo "==> collectstatic"
python manage.py collectstatic --noinput
mkdir -p logs var media backups
echo "==> done — restart systemd units: churchhub-web churchhub-celery churchhub-celerybeat"
