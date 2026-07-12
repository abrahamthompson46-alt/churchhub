#!/usr/bin/env bash
set -o errexit

echo "==> Waiting for database"
python << 'PY'
import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
django.setup()

from django.db import connection

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
python manage.py migrate --noinput

echo "==> Syncing permission matrix"
python manage.py seed_permissions

if [ "${CHURCHHUB_BOOTSTRAP:-0}" = "1" ]; then
  echo "==> Running production bootstrap"
  python manage.py bootstrap_production --no-input
fi

PORT="${PORT:-8000}"
WORKERS="${GUNICORN_WORKERS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "==> Starting Gunicorn on port ${PORT}"
exec gunicorn church_system.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile -
