#!/usr/bin/env bash
# Fix malformed Markdown-style DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS in .env
# Safe: backs up .env first; only rewrites those two keys to plain CSV values.
#
# Usage (on the VPS as churchhub or with sudo -u churchhub):
#   bash deploy/scripts/fix_env_hosts_csrf.sh
#   APP_ROOT=/home/churchhub/apps/churchhub bash deploy/scripts/fix_env_hosts_csrf.sh
#
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/churchhub/apps/churchhub}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/.env}"
ALLOWED_VALUE="${DJANGO_ALLOWED_HOSTS_VALUE:-localhost,127.0.0.1,162.35.179.20,zreta.com,www.zreta.com,app.zreta.com}"
CSRF_VALUE="${DJANGO_CSRF_TRUSTED_ORIGINS_VALUE:-https://zreta.com,https://www.zreta.com,https://app.zreta.com}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
BACKUP="${ENV_FILE}.bak.csrfhost.${STAMP}"
cp -a "$ENV_FILE" "$BACKUP"
echo "Backup: $BACKUP"

# Show current (possibly malformed) lines
echo "=== Before ==="
grep -E '^(DJANGO_ALLOWED_HOSTS|DJANGO_CSRF_TRUSTED_ORIGINS)=' "$ENV_FILE" || echo "(keys missing)"

TMP="$(mktemp)"
# Drop existing keys then append clean values (preserve rest of file)
grep -vE '^(DJANGO_ALLOWED_HOSTS|DJANGO_CSRF_TRUSTED_ORIGINS)=' "$ENV_FILE" > "$TMP" || true
{
  echo "DJANGO_ALLOWED_HOSTS=${ALLOWED_VALUE}"
  echo "DJANGO_CSRF_TRUSTED_ORIGINS=${CSRF_VALUE}"
} >> "$TMP"
# Preserve ownership/mode
cp -a "$ENV_FILE" "${ENV_FILE}.mode_ref" 2>/dev/null || true
cat "$TMP" > "$ENV_FILE"
rm -f "$TMP" "${ENV_FILE}.mode_ref"

echo "=== After ==="
grep -E '^(DJANGO_ALLOWED_HOSTS|DJANGO_CSRF_TRUSTED_ORIGINS)=' "$ENV_FILE"

# Verify Django loads clean lists (no brackets / markdown)
cd "$APP_ROOT"
if [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
  PY="$APP_ROOT/.venv/bin/python"
else
  PY=python3
fi

echo "=== Django settings check ==="
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-church_system.settings}"
"$PY" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")
import django
django.setup()
from django.conf import settings
hosts = list(settings.ALLOWED_HOSTS)
origins = list(settings.CSRF_TRUSTED_ORIGINS)
print("ALLOWED_HOSTS=", hosts)
print("CSRF_TRUSTED_ORIGINS=", origins)
bad = [h for h in hosts if "[" in h or "]" in h or "(" in h or ")" in h or "http" in h]
bad += [o for o in origins if "[" in o or "]" in o or "(" in o]
if bad:
    raise SystemExit(f"FAIL: malformed entries still present: {bad}")
need_hosts = {"zreta.com", "www.zreta.com", "app.zreta.com"}
need_origins = {
    "https://zreta.com",
    "https://www.zreta.com",
    "https://app.zreta.com",
}
missing_h = need_hosts - set(hosts)
missing_o = need_origins - set(origins)
if missing_h or missing_o:
    raise SystemExit(f"FAIL: missing hosts={missing_h} origins={missing_o}")
print("VERIFY_OK")
PY

# Restart Gunicorn — try both unit names used on this project
echo "=== Restart web ==="
restarted=0
for unit in churchhub-web churchhub; do
  if systemctl list-unit-files "${unit}.service" 2>/dev/null | grep -q "${unit}.service"; then
    if systemctl is-active --quiet "${unit}.service" || systemctl cat "${unit}.service" >/dev/null 2>&1; then
      sudo systemctl restart "${unit}.service"
      sudo systemctl is-active "${unit}.service"
      echo "Restarted ${unit}.service"
      restarted=1
    fi
  fi
done
if [[ "$restarted" -eq 0 ]]; then
  echo "WARNING: neither churchhub-web nor churchhub systemd unit found; restart manually." >&2
fi

echo "Done. Rollback: cp -a $BACKUP $ENV_FILE && sudo systemctl restart churchhub-web"
