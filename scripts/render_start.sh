#!/usr/bin/env bash
set -o errexit
set -o pipefail

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: Neither python3 nor python found in PATH" >&2
  exit 1
fi

echo "==> Checking DATABASE_URL"
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  echo "In Render: Web Service → Environment → Add DATABASE_URL from your Postgres instance" >&2
  echo "(or link the database under Environment → Add from Database)." >&2
  exit 1
fi

echo "==> Waiting for database"
$PY << 'PY'
import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
django.setup()

from django.conf import settings
from django.db import connection

engine = settings.DATABASES["default"]["ENGINE"]
print(f"Database engine: {engine}")
if "sqlite" in engine:
    print("ERROR: Refusing to start with SQLite on Render.", file=sys.stderr)
    sys.exit(1)

for attempt in range(30):
    try:
        connection.ensure_connection()
        print("Database ready.")
        break
    except Exception as exc:
        if attempt == 29:
            print(f"Database not ready: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
PY

echo "==> Applying migrations"
$PY manage.py migrate --noinput

echo "==> Syncing permission matrix"
$PY manage.py seed_permissions

if [ "${CHURCHHUB_BOOTSTRAP:-0}" = "1" ]; then
  echo "==> Running production bootstrap"
  $PY manage.py bootstrap_production --no-input
fi

PORT="${PORT:-8000}"
WORKERS="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-2}}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "==> Starting Gunicorn on port ${PORT}"
exec $PY -m gunicorn church_system.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile -
