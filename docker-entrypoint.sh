#!/bin/sh
set -e

echo "Waiting for database..."
python << 'PY'
import os, sys, time
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
django.setup()
from django.db import connection
for i in range(30):
    try:
        connection.ensure_connection()
        print("Database ready.")
        break
    except Exception:
        if i == 29:
            sys.exit(1)
        time.sleep(2)
PY

python manage.py migrate --noinput
python manage.py seed_permissions

if [ "${DJANGO_SETUP_DEMO:-0}" = "1" ]; then
  python manage.py setup_churchhub --no-input || true
fi

python manage.py collectstatic --noinput --clear 2>/dev/null || true

exec gunicorn church_system.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout 120
