#!/usr/bin/env bash
# Self-host deploy helper (Ubuntu VPS). Run from repo root after venv + .env are ready.
# Order: migrate → permissions → collectstatic → restart services → readiness hint.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export DJANGO_ENV="${DJANGO_ENV:-production}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-church_system.settings}"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="python"
  fi
fi

echo "==> migrate"
"$PYTHON" manage.py migrate --noinput
echo "==> seed_permissions"
"$PYTHON" manage.py seed_permissions
echo "==> collectstatic"
"$PYTHON" manage.py collectstatic --noinput
mkdir -p logs var media backups staticfiles

if command -v systemctl >/dev/null 2>&1 && [[ "${CHURCHHUB_RESTART_SYSTEMD:-1}" == "1" ]]; then
  echo "==> restart systemd units (if installed)"
  for unit in churchhub-web churchhub-celery churchhub-celerybeat; do
    if systemctl list-unit-files "${unit}.service" >/dev/null 2>&1; then
      sudo systemctl restart "$unit" || true
    fi
  done
else
  echo "==> skip systemd restart — run manually:"
  echo "    sudo systemctl restart churchhub-web churchhub-celery churchhub-celerybeat"
fi

echo "==> done"
echo "    Readiness (token required in production):"
echo "    curl -fsS -H \"X-Health-Token: \$CHURCHHUB_HEALTH_TOKEN\" http://127.0.0.1/health/ready/"
