#!/usr/bin/env bash
# ChurchHub Wave 0 — read-only host verification
# Safe: does not modify configs, flush caches, or restart services.
# Usage: bash deploy/scripts/wave0_verify.sh
set -euo pipefail

echo "=== ChurchHub Wave 0 verify ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
echo "Host: $(hostname -f 2>/dev/null || hostname)"
echo "User: $(whoami)"
echo

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# zreta.com VPS layout prefers /home/churchhub/... ; /opt/churchhub is the repo template path
for candidate in \
  "$HOME/apps/churchhub" \
  /home/churchhub/apps/churchhub \
  /opt/churchhub \
  "$ROOT"
do
  if [[ -d "$candidate" && -f "$candidate/manage.py" ]]; then
    ROOT="$candidate"
    break
  fi
done
echo "App root: $ROOT"
cd "$ROOT"

echo
echo "--- systemd ---"
for u in churchhub-web churchhub-celery churchhub-celerybeat nginx redis-server postgresql; do
  if systemctl list-unit-files "${u}.service" &>/dev/null; then
    echo "$u: $(systemctl is-active "$u" 2>/dev/null || echo n/a)"
  fi
done

echo
echo "--- listeners (8000/443/80/6379/5432) ---"
ss -lntp 2>/dev/null | grep -E ':8000|:443|:80|:6379|:5432' || netstat -lntp 2>/dev/null | grep -E ':8000|:443|:80|:6379|:5432' || true

echo
echo "--- UFW ---"
if command -v ufw >/dev/null; then
  sudo ufw status verbose || true
else
  echo "ufw not installed"
fi

echo
echo "--- Fail2Ban ---"
if command -v fail2ban-client >/dev/null; then
  sudo fail2ban-client status || true
else
  echo "fail2ban not installed"
fi

echo
echo "--- Redis ping ---"
if command -v redis-cli >/dev/null; then
  redis-cli ping 2>/dev/null || echo "redis-cli ping failed (auth or down)"
else
  echo "redis-cli not installed"
fi

echo
echo "--- Backups ---"
for d in \
  backups \
  "$ROOT/backups" \
  /home/churchhub/backups \
  /opt/churchhub/backups
do
  if [[ -d "$d" ]]; then
    echo "dir $d:"
    ls -lah "$d" | tail -n 20 || true
  fi
done
if [[ -x /home/churchhub/scripts/churchhub_backup.sh ]]; then
  echo "backup script: /home/churchhub/scripts/churchhub_backup.sh (present)"
fi
if [[ -x /home/churchhub/monitoring/churchhub_health_check.sh ]]; then
  echo "health script: /home/churchhub/monitoring/churchhub_health_check.sh (present)"
fi
if command -v rclone >/dev/null; then
  echo "rclone: $(rclone version | head -n 1)"
  rclone listremotes || true
else
  echo "rclone not installed"
fi

echo
echo "--- Django settings flags (no secrets) ---"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  set -a
  [[ -f "$ROOT/.env" ]] && . "$ROOT/.env"
  set +a
  "$ROOT/.venv/bin/python" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
import django
django.setup()
from django.conf import settings
print("DJANGO_ENV_env=", os.environ.get("DJANGO_ENV"))
print("DJANGO_ENV_attr=", getattr(settings, "DJANGO_ENV", None))
print("DEBUG=", settings.DEBUG)
print("SECURE_SSL_REDIRECT=", getattr(settings, "SECURE_SSL_REDIRECT", None))
print("SESSION_COOKIE_SECURE=", settings.SESSION_COOKIE_SECURE)
print("CSRF_COOKIE_SECURE=", settings.CSRF_COOKIE_SECURE)
print("SECURE_HSTS_SECONDS=", getattr(settings, "SECURE_HSTS_SECONDS", None))
print("REQUIRE_REDIS=", getattr(settings, "REQUIRE_REDIS", None))
print("REDIS_URL_set=", bool(getattr(settings, "REDIS_URL", "")))
print("ALLOWED_HOSTS=", list(settings.ALLOWED_HOSTS))
print("PUBLIC_URL=", getattr(settings, "CHURCHHUB_PUBLIC_URL", ""))
PY
else
  echo "venv python not found at $ROOT/.venv/bin/python"
fi

echo
echo "=== Wave 0 verify complete (read-only) ==="
