# ChurchHub — Fail2Ban operator notes

**Audience:** VPS operators (zreta.com / Ubuntu 24.04)  
**Related:** `docs/WAVE1_INFRA_SECURITY_PLAN.md`, `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md`

## Goals

- Keep / tune **sshd** protection without weakening a working live jail.
- Optional **HTTP auth** jail for sustained POST abuse (off until Cloudflare real-IP works).
- Complement Django `LoginRateLimitMiddleware` — do not replace it.

## Install (safe order)

```bash
# 1) Snapshot live state
sudo fail2ban-client status
sudo fail2ban-client status sshd || true
sudo cp -a /etc/fail2ban/jail.d "/etc/fail2ban/jail.d.bak.$(date +%Y%m%d%H%M)" 2>/dev/null || true

# 2) Compare live thresholds to repo template (keep stricter live values if present)
sudo fail2ban-client get sshd maxretry
sudo fail2ban-client get sshd findtime
sudo fail2ban-client get sshd bantime

# 3) Copy templates (from app root)
sudo cp deploy/fail2ban/filter.d/churchhub-nginx-auth.conf /etc/fail2ban/filter.d/
sudo cp deploy/fail2ban/jail.d/churchhub-sshd.conf /etc/fail2ban/jail.d/
sudo cp deploy/fail2ban/jail.d/churchhub-nginx-auth.conf /etc/fail2ban/jail.d/

# 4) Reload — sshd stays enabled; nginx-auth stays disabled until real-IP gate
sudo fail2ban-client reload
sudo fail2ban-client status
```

## Cloudflare real-IP gate (before enabling HTTP jail)

```bash
sudo cp deploy/nginx/cloudflare-realip.conf /etc/nginx/snippets/cloudflare-realip.conf
# ensure TLS server includes: include /etc/nginx/snippets/cloudflare-realip.conf;
sudo nginx -t && sudo systemctl reload nginx
sudo tail -n 30 /var/log/nginx/access.log
# Visitor IP must appear — not Cloudflare anycast alone
```

Then set `enabled = true` in `/etc/fail2ban/jail.d/churchhub-nginx-auth.conf` and reload.

## Rollback

```bash
# Restore previous jail.d from backup directory created above
sudo rm -f /etc/fail2ban/jail.d/churchhub-sshd.conf \
           /etc/fail2ban/jail.d/churchhub-nginx-auth.conf
sudo rm -f /etc/fail2ban/filter.d/churchhub-nginx-auth.conf
# If you kept a bak tree:
# sudo cp -a /etc/fail2ban/jail.d.bak.YYYYMMDDHHMM/* /etc/fail2ban/jail.d/
sudo fail2ban-client reload
sudo fail2ban-client status sshd
```

Unban a mistaken IP:

```bash
sudo fail2ban-client set sshd unbanip A.B.C.D
sudo fail2ban-client set churchhub-nginx-auth unbanip A.B.C.D
```

## ignoreip

Edit both jail files (or `/etc/fail2ban/jail.local`) to append office/VPN CIDRs:

```ini
ignoreip = 127.0.0.1/8 ::1 203.0.113.0/24
```
