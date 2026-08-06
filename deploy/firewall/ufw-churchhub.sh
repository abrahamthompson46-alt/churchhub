#!/usr/bin/env bash
# ChurchHub UFW helper — safe plan/apply (does not reset existing rules by default).
#
# Usage:
#   sudo bash deploy/firewall/ufw-churchhub.sh --status
#   sudo bash deploy/firewall/ufw-churchhub.sh --plan
#   sudo bash deploy/firewall/ufw-churchhub.sh --apply
#   sudo bash deploy/firewall/ufw-churchhub.sh --check-exposure
#
# --apply:
#   - Ensures OpenSSH (or TCP 22), 80, 443 are allowed BEFORE enabling UFW
#   - Does NOT flush or delete existing allow rules
#   - Does NOT run "ufw reset"
#   - Sets default deny incoming / allow outgoing only if not already set that way
#
# Rollback: see docs/DEVELOPMENT/DEPLOYMENT_NOTES.md (UFW section) —
# restore from a pre-change `ufw status numbered` snapshot; delete only rules you added.

set -euo pipefail

usage() {
  cat <<'EOF'
ChurchHub UFW helper

  --status          Show ufw status verbose (no changes)
  --plan            Print intended production policy (no changes)
  --apply           Ensure SSH/80/443 allows; enable UFW if inactive (no reset)
  --check-exposure  Local listen check for 8000/5432/6379 public binds
  --help            This message

Environment:
  CHURCHHUB_UFW_SSH_PROFILE  OpenSSH profile name (default: OpenSSH)
EOF
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "ERROR: run as root (sudo)." >&2
    exit 1
  fi
}

cmd_status() {
  require_root
  if ! command -v ufw >/dev/null 2>&1; then
    echo "ufw is not installed"
    exit 1
  fi
  ufw status verbose
  echo
  ufw status numbered || true
}

cmd_plan() {
  cat <<'EOF'
=== ChurchHub UFW planned policy (production-safe) ===

Defaults:
  default deny incoming
  default allow outgoing

Ensure ALLOW (add if missing; never delete others):
  - OpenSSH  (or 22/tcp)   — preserve SSH access
  - 80/tcp                 — HTTP / ACME
  - 443/tcp                — HTTPS

Explicitly NOT done by this script:
  - ufw reset / wipe existing rules
  - Cloudflare-only origin allowlist (optional later)
  - Changing SSH port

Exposure expectation (application bind, not UFW alone):
  - Gunicorn 127.0.0.1:8000
  - PostgreSQL localhost only
  - Redis localhost only

Use --apply to enforce allows + enable. Use --check-exposure for listen sockets.
EOF
}

rule_mentions() {
  # Return 0 if ufw status mentions the pattern
  local pattern="$1"
  ufw status 2>/dev/null | grep -qiE "$pattern"
}

ensure_allow() {
  local spec="$1"
  local human="$2"
  if rule_mentions "$spec"; then
    echo "OK: already allows $human ($spec)"
  else
    echo "ADD: ufw allow $spec  # $human"
    ufw allow "$spec"
  fi
}

cmd_apply() {
  require_root
  if ! command -v ufw >/dev/null 2>&1; then
    echo "ERROR: ufw not installed. apt install ufw" >&2
    exit 1
  fi

  echo "=== Snapshot (save this for rollback) ==="
  ufw status numbered || ufw status verbose || true
  echo

  local ssh_profile="${CHURCHHUB_UFW_SSH_PROFILE:-OpenSSH}"

  # Defaults — only set if we can query; ufw default is safe to re-run
  echo "=== Defaults (deny in / allow out) ==="
  ufw default deny incoming
  ufw default allow outgoing

  echo "=== Ensure critical allows (additive) ==="
  # Prefer named profile so custom SSH ports still work when using OpenSSH profile
  if ufw app list 2>/dev/null | grep -qx "$ssh_profile"; then
    ensure_allow "$ssh_profile" "SSH ($ssh_profile)"
  else
    ensure_allow "22/tcp" "SSH (22/tcp fallback)"
  fi
  ensure_allow "80/tcp" "HTTP"
  ensure_allow "443/tcp" "HTTPS"

  echo
  if ufw status | grep -qi "Status: active"; then
    echo "UFW already active — not resetting rules."
  else
    echo "UFW inactive — enabling (SSH/80/443 already ensured above)."
    # --force avoids interactive prompt; rules already include SSH
    ufw --force enable
  fi

  echo
  echo "=== Result ==="
  ufw status verbose
  echo
  echo "Rollback tip: keep the snapshot above; delete only numbered rules you added:"
  echo "  sudo ufw status numbered"
  echo "  sudo ufw delete N"
}

cmd_check_exposure() {
  echo "=== Listen sockets (8000 / 5432 / 6379 / 80 / 443 / 22) ==="
  if command -v ss >/dev/null 2>&1; then
    ss -lntp 2>/dev/null | grep -E ':22 |:80 |:443 |:8000 |:5432 |:6379 ' || echo "(no matches — check manually)"
  else
    netstat -lntp 2>/dev/null | grep -E ':22 |:80 |:443 |:8000 |:5432 |:6379 ' || true
  fi

  echo
  echo "=== Public bind check (FAIL if 0.0.0.0 or *:port for app DB redis) ==="
  local fail=0
  check_public() {
    local port="$1" name="$2"
    local line
    line="$(ss -lntp 2>/dev/null | grep -E ":${port} " || true)"
    if [[ -z "$line" ]]; then
      echo "OK: $name :$port not listening (or not visible)"
      return
    fi
    if echo "$line" | grep -qE '0\.0\.0\.0:'"${port}"'|:::'"${port}"'|\*:'"${port}"; then
      # Distinguish nginx (80/443 ok) from app ports
      if [[ "$port" == "80" || "$port" == "443" || "$port" == "22" ]]; then
        echo "OK: $name publicly listening on :$port (expected for edge)"
      else
        echo "FAIL: $name appears publicly bound on :$port"
        echo "$line"
        fail=1
      fi
    else
      echo "OK: $name :$port local/loopback only"
      echo "$line" | sed 's/^/  /'
    fi
  }

  check_public 8000 "Gunicorn"
  check_public 5432 "PostgreSQL"
  check_public 6379 "Redis"
  check_public 80 "HTTP"
  check_public 443 "HTTPS"
  check_public 22 "SSH"

  echo
  if [[ "$fail" -ne 0 ]]; then
    echo "RESULT: exposure check FAILED — bind Gunicorn/Postgres/Redis to 127.0.0.1 and restart."
    exit 1
  fi
  echo "RESULT: exposure check PASSED for 8000/5432/6379 (not publicly bound)."
}

main() {
  local arg="${1:-}"
  case "$arg" in
    --status) cmd_status ;;
    --plan) cmd_plan ;;
    --apply) cmd_apply ;;
    --check-exposure) cmd_check_exposure ;;
    --help|-h|"") usage; [[ -n "$arg" ]] || exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage; exit 1 ;;
  esac
}

main "${1:-}"
