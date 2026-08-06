#!/usr/bin/env bash
# ChurchHub Wave 1 — infrastructure security verification (read-only by default)
# Usage: bash deploy/scripts/wave1_infra_verify.sh
set -euo pipefail

echo "=== ChurchHub Wave 1 infra verify ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
echo "Host: $(hostname -f 2>/dev/null || hostname)"
echo

echo "--- Fail2Ban ---"
if command -v fail2ban-client >/dev/null 2>&1; then
  sudo fail2ban-client status || true
  sudo fail2ban-client status sshd 2>/dev/null || echo "sshd jail: not loaded"
  sudo fail2ban-client status churchhub-nginx-auth 2>/dev/null || echo "churchhub-nginx-auth: not loaded (OK if disabled)"
else
  echo "fail2ban-client not installed"
fi

echo
echo "--- UFW ---"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw status verbose || true
else
  echo "ufw not installed"
fi

echo
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -x "$ROOT/deploy/firewall/ufw-churchhub.sh" ]] || [[ -f "$ROOT/deploy/firewall/ufw-churchhub.sh" ]]; then
  bash "$ROOT/deploy/firewall/ufw-churchhub.sh" --check-exposure || true
else
  echo "ufw-churchhub.sh missing"
fi

echo
echo "=== done ==="
