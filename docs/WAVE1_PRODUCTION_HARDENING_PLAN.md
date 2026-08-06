# ChurchHub — Wave 0 Verification + Wave 1 Production Hardening Plan

**Status:** PLAN ONLY — awaiting owner approval before any file or VPS changes  
**Date:** 6 August 2026  
**Inputs:** `docs/SECURITY_AND_DEPLOYMENT_AUDIT.md`, live code, prior VPS/MFA work  
**Constraint:** Do **not** implement until this document is approved

| Label | Meaning |
|-------|---------|
| **Wave 0** | Read-only verification on the live VPS + checklist evidence (no product code required) |
| **Wave 1** | Production hardening changes (repo + VPS + docs) after approval |
| **Out of scope** | Soft-delete, absolute session timeout, password history, public `/api/v1/`, second GL |

---

## 1. Goals

After Wave 0 + Wave 1:

1. HTTPS is enforced end-to-end (Cloudflare Full Strict → origin → Django Secure cookies / HSTS).
2. Host has Fail2Ban + documented UFW policy; Redis is not world-reachable without auth.
3. DB backups are local **and** verified offsite (Google Drive), with a documented restore drill.
4. Sensitive member media is no longer anonymously downloadable via raw `/media/` URLs.
5. MFA verify is rate-limited; MFA secrets use a dedicated encryption key; report/finance exports respect export permissions.

---

## 2. Wave 0 — Verification checklist (no code changes)

Execute on the production VPS / Cloudflare dashboard. Record answers in an ops log (date, operator, pass/fail). **Do not change application code in Wave 0.**

### 2.1 Django / process

| # | Check | Pass criteria |
|---|--------|----------------|
| W0-1 | `DJANGO_ENV` | `production` |
| W0-2 | `DJANGO_DEBUG` | `False` |
| W0-3 | `DJANGO_SECRET_KEY` | Unique, not the insecure default |
| W0-4 | `SECURE_SSL_REDIRECT` | `true` once Cloudflare Full Strict + origin TLS are live |
| W0-5 | Redis | `REDIS_URL` set; `redis-cli ping` → `PONG`; Gunicorn workers > 1 still share rate limits |
| W0-6 | Postgres | `DATABASE_URL` Postgres; `/health/ready/` OK with health token |
| W0-7 | Units | `churchhub-web`, `churchhub-celery`, `churchhub-celerybeat` active |
| W0-8 | Gunicorn bind | Listening on `127.0.0.1:8000` only (not `0.0.0.0`) |
| W0-9 | MFA | OWNER / SECURITY / SUPER_ADMIN / TREASURY enrolled where policy requires |

**Commands (ops only):**

```bash
cd /opt/churchhub   # or ~/apps/churchhub
sudo systemctl status churchhub-web churchhub-celery churchhub-celerybeat
ss -lntp | grep 8000
sudo -u churchhub bash -c 'set -a; source .env; set +a; redis-cli -u "$REDIS_URL" ping'
curl -sH "X-Health-Token: $CHURCHHUB_HEALTH_TOKEN" http://127.0.0.1:8000/health/ready/
```

### 2.2 Cloudflare Full (Strict)

| # | Check | Pass criteria |
|---|--------|----------------|
| W0-10 | SSL/TLS mode | **Full (Strict)** |
| W0-11 | Proxied DNS | Orange cloud on apex/www |
| W0-12 | Origin cert | Valid Let’s Encrypt **or** Cloudflare Origin Certificate on Nginx 443 |
| W0-13 | Always Use HTTPS | On (Cloudflare) |
| W0-14 | Browser test | `https://` loads; HTTP redirects; Set-Cookie includes `Secure` for session |
| W0-15 | Django scheme | With `X-Forwarded-Proto: https` from Nginx, Django does not redirect-loop |

**Known code fact (no change in Wave 0):** `production.py` already ties `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS to `SECURE_SSL_REDIRECT`. If Wave 0 finds cookies still non-Secure, root cause is almost always `SECURE_SSL_REDIRECT=false` still in `.env`, or Nginx not sending `X-Forwarded-Proto https`.

### 2.3 Firewall / Fail2Ban / Redis (baseline observation)

| # | Check | Record |
|---|--------|--------|
| W0-16 | `ufw status verbose` | Allowed ports today |
| W0-17 | `fail2ban-client status` | Installed? Active jails? |
| W0-18 | Redis bind | `127.0.0.1` only? `requirepass` set? |
| W0-19 | Postgres listen | Local only / SSL? |

### 2.4 Backups / Google Drive

| # | Check | Pass criteria |
|---|--------|----------------|
| W0-20 | Local dump exists | Recent `churchhub_*.sql.gz` under backups dir |
| W0-21 | Beat backup | Journal shows `backup_database_task` success |
| W0-22 | Google Drive | Confirm whether **rclone** (or other) already syncs dumps off-box. **Repo today has no GDrive integration** — Wave 0 only verifies what exists on the VPS |
| W0-23 | Media backup | Media tree included in offsite sync or separate snapshot |

If Google Drive sync is **missing**, Wave 1 adds `rclone` scripts (see §5.3). Do not invent a Drive API app unless ops prefers that over rclone.

### 2.5 Media exposure spot-check

| # | Check | Pass criteria |
|---|--------|----------------|
| W0-24 | Unauthenticated fetch | Logged-out browser/`curl` of a known `/media/members/...` URL returns **200 today** (expected gap) or 403/401 if already locked |
| W0-25 | Public branding | Site logo still loads on login when logged out (must remain public after Wave 1) |

---

## 3. Change taxonomy (Wave 1)

Every planned change is tagged:

| Tag | Meaning |
|-----|---------|
| **APP** | Application Python / templates / tests |
| **SETTINGS** | Django settings / `.env.example` |
| **VPS** | Live server commands / packages (not always committed) |
| **SEC-CFG** | Fail2Ban, UFW, Nginx, Redis, Cloudflare, rclone configs in `deploy/` |
| **DOCS** | Markdown runbooks / checklists / this plan’s follow-ups |

---

## 4. Wave 1 detailed plan by workstream

### 4.1 TLS / HTTPS / Cloudflare Full (Strict)

#### Intent

Ensure Cloudflare Full Strict + origin TLS + Django production HTTPS flags work together without redirect loops, and that Secure cookies / HSTS apply whenever traffic is HTTPS.

#### Files / configs

| Change | Tag | File / location |
|--------|-----|-----------------|
| Enable TLS server + HTTP→HTTPS redirect; Cloudflare real IP; forward `https` proto | SEC-CFG | `deploy/nginx/churchhub.conf` |
| Optional Cloudflare Origin Cert snippet / comments | SEC-CFG | `deploy/nginx/cloudflare-origin.md` **(new)** or section inside Nginx conf comments |
| Align staging Secure cookies with HTTPS mode (fix S-02) | SETTINGS | `church_system/settings/staging.py` |
| Document Cloudflare Full Strict + env matrix | DOCS | `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md` §8 |
| Env examples for HTTPS production | SETTINGS | `.env.example` |
| Production settings review only (likely **no logic change** if already correct) | SETTINGS | `church_system/settings/production.py` |
| Regression: Secure flags follow `_https_mode` | APP | `church_system/tests_security_hardening.py` (extend) |
| Update checklist | DOCS | `docs/PRODUCTION_SECURITY_CHECKLIST.md`, `docs/SECURITY_AND_DEPLOYMENT_AUDIT.md` (status notes) |

#### Nginx / Cloudflare specifics (planned)

1. Uncomment Phase B TLS block; enable `return 301 https://$host$request_uri` on `:80` (keep ACME challenge location).
2. Add Cloudflare IP ranges via `set_real_ip_from` + `real_ip_header CF-Connecting-IP` (or `X-Forwarded-For`) so Fail2Ban and Django see client IPs.
3. Origin: Let’s Encrypt **or** Cloudflare Origin Certificate (document both; pick one on VPS).
4. Django `.env` on VPS (ops):

```ini
SECURE_SSL_REDIRECT=true
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CHURCHHUB_PUBLIC_URL=https://example.com
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
```

5. Confirm `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` remains (already Current).
6. Confirm Gunicorn `forwarded_allow_ips=127.0.0.1` remains (already Current).

#### Explicit non-goals

- Do not force HTTPS redirect inside Cloudflare **and** Nginx in conflicting ways without testing.
- Do not enable HSTS preload until domain is stable (`SECURE_HSTS_PRELOAD` stays opt-in).

---

### 4.2 Server security — Fail2Ban + UFW

#### Intent

Ban repeat offenders on SSH and auth endpoints; restrict inbound ports to SSH + HTTP/HTTPS.

#### Files / configs

| Change | Tag | File / location |
|--------|-----|-----------------|
| SSH jail | SEC-CFG | `deploy/fail2ban/jail.d/churchhub-sshd.conf` **(new)** |
| Nginx auth filter (401/403 on login paths) | SEC-CFG | `deploy/fail2ban/filter.d/churchhub-nginx-auth.conf` **(new)** |
| Nginx auth jail | SEC-CFG | `deploy/fail2ban/jail.d/churchhub-nginx-auth.conf` **(new)** |
| UFW policy script | SEC-CFG | `deploy/firewall/ufw-churchhub.sh` **(new)** |
| Install/apply notes | DOCS | `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md` (new subsection) |
| Ops checklist | DOCS | `docs/PRODUCTION_SECURITY_CHECKLIST.md` |

#### VPS steps (after repo merge)

| Step | Tag |
|------|-----|
| `apt install fail2ban` / enable service | VPS |
| Copy jail/filter files → `/etc/fail2ban/` | VPS |
| `fail2ban-client reload` | VPS |
| Run UFW script (allow OpenSSH, 80, 443; deny rest) | VPS |
| Verify Cloudflare still reaches origin (if IP allowlisting Cloudflare-only is chosen later — **optional Phase 1b**, not default) | VPS |

#### Defaults (planned)

- SSH: 5 failures / 10 min → ban 1 hour (tunable).
- Nginx auth: match `/accounts/login`, `/portal/login`, `/accounts/mfa/verify` 401/403 bursts.
- UFW: default deny incoming; allow 22/tcp, 80/tcp, 443/tcp; allow established.

---

### 4.3 Backup improvements — Google Drive + verification + restore docs

#### Current state

- Local: `manage.py backup_database`, `scripts/backup.sh`, Celery Beat `backup_database_task`.
- Restore narrative: `docs/OPERATIONS_RUNBOOK.md` §5.
- **No Google Drive / rclone code in repo today.**

#### Intent

1. Wave 0 verifies existing Drive sync if any.  
2. Wave 1 adds a standard **rclone → Google Drive** offsite sync + integrity checks + clearer restore runbook.

#### Files / configs

| Change | Tag | File / location |
|--------|-----|-----------------|
| Extend backup command with `--verify` (gunzip test / size / optional checksum file) | APP | `church_system/management/commands/backup_database.py` |
| Optional post-backup hook env `CHURCHHUB_BACKUP_POST_HOOK` | APP / SETTINGS | `backup_database.py`, `.env.example` |
| rclone sync script | SEC-CFG | `deploy/backup/rclone-gdrive-sync.sh` **(new)** |
| Example rclone remote notes | DOCS | `deploy/backup/README.md` **(new)** |
| Wire Beat or cron to call sync after dump | APP or VPS | Prefer: post-hook from backup command; fallback: systemd timer / cron on VPS |
| Restore procedure expansion (GDrive download → staging restore → smoke) | DOCS | `docs/OPERATIONS_RUNBOOK.md`, `docs/PRODUCTION_RUNBOOK.md` |
| Env vars | SETTINGS | `.env.example` (`CHURCHHUB_BACKUP_DIR`, `CHURCHHUB_BACKUP_POST_HOOK`, retention) |

#### Verification checks (planned)

After each successful dump:

1. File exists and size > minimum threshold.  
2. `gzip -t` succeeds.  
3. Write sibling `.sha256` checksum.  
4. Post-hook syncs to Google Drive remote (rclone).  
5. Log success/failure to application/security log; fail the task if sync required and fails (`CHURCHHUB_BACKUP_REQUIRE_OFFSITE=true`).

#### VPS (ops)

| Step | Tag |
|------|-----|
| Install `rclone`; `rclone config` Google Drive remote (service account or OAuth — ops choice) | VPS |
| Store remote name in `.env` / hook script | VPS |
| Run one manual backup + sync; download to staging and restore drill | VPS |
| Record drill date in ops log / checklist | DOCS / VPS |

---

### 4.4 Media protection

#### Intent

Stop anonymous download of sensitive member/content files while keeping public branding (login logos) working.

#### Architecture (recommended — Wave 1 implements Phase A)

```
Browser
  → Nginx
      /media/public/**     → alias (public branding, site logos) — anonymous OK
      /media/private/**    → internal; only via X-Accel-Redirect
  → Django auth view
      checks login + church/denomination scope + object permission
      returns X-Accel-Redirect: /internal-media/...
```

**Sensitive (private):** `members/profile_pictures/`, `records/`, `history/`, `meetings/attachments/`, `exports/reports/`, payroll/docs if any.  
**Public:** site/denomination logos used on auth pages (path prefix `media/public/` or existing branding paths allowlisted).

#### Wave 1 Phase A (implement)

| Change | Tag | File / location |
|--------|-----|-----------------|
| Split Nginx: public alias vs internal private location | SEC-CFG | `deploy/nginx/churchhub.conf` |
| Authenticated media download view + URL | APP | `church_system/views_media.py` **(new)** or `church_system/media_views.py` **(new)** |
| Wire URL | APP | `church_system/urls.py` |
| Helper to classify public vs private paths | APP | `church_system/media_access.py` **(new)** |
| Template/storage guidance: new uploads for sensitive types stay under private prefixes (existing files: migrate or dual-read) | APP | Minimal path allowlist; optional management command to report exposed paths |
| Tests: anonymous 401/403; authorized 200 via accel or FileResponse fallback | APP | `church_system/tests_media_access.py` **(new)** |
| Docs | DOCS | `DEPLOYMENT_NOTES.md`, `SECURITY_AND_DEPLOYMENT_AUDIT.md` finding D-02 status |

#### Wave 1 Phase B (document only unless approved as same PR)

- S3/private buckets + pre-signed URLs for member documents.  
- Virus scan hook (future).

#### Explicit risk note

Moving Nginx off open `/media/` may break bookmarks and email links to absolute media URLs. Plan includes dual support: private paths require auth; optionally temporary redirect from old URLs through the auth view.

---

### 4.5 Redis security

#### Intent

Redis must not be reachable from the internet; prefer password ACL; document TLS for managed Redis.

#### Files / configs

| Change | Tag | File / location |
|--------|-----|-----------------|
| Example redis drop-in (bind + requirepass) | SEC-CFG | `deploy/redis/churchhub-redis.conf.snippet` **(new)** |
| `.env.example` shows `redis://:PASSWORD@127.0.0.1:6379/0` | SETTINGS | `.env.example` |
| Production notes | DOCS | `DEPLOYMENT_NOTES.md` |
| Optional health check message if Redis URL has no password on non-local host | APP | `church_system/health.py` (warning only — do not refuse loopback without pass in Wave 1) |

#### VPS

| Step | Tag |
|------|-----|
| Set `requirepass`; update `REDIS_URL` / Celery broker URLs; restart Redis + app units | VPS |
| Confirm `ss -lntp | grep 6379` → 127.0.0.1 only | VPS |

---

### 4.6 Application hardening

#### 4.6.1 MFA verification rate limiting

| Change | Tag | File / location |
|--------|-----|-----------------|
| Cache-backed attempt counter (IP + pending user id) on verify POST | APP | `accounts/mfa_views.py`, optionally `accounts/mfa.py` helpers |
| Cover recovery-code attempts | APP | same |
| Extend login rate middleware **or** dedicated helper (prefer dedicated MFA helper to avoid coupling) | APP | `accounts/mfa.py` |
| Tests | APP | `accounts/tests_mfa.py` |
| Docs | DOCS | `docs/SECURITY/AUTHENTICATION.md`, `KNOWN_LIMITATIONS.md` (KL-SEC-02 → mitigated) |

**Planned defaults:** 5 failed verifies / 15 minutes per IP+user → lock with clear message; audit log on lockout.

#### 4.6.2 Dedicated MFA encryption key

| Change | Tag | File / location |
|--------|-----|-----------------|
| Read `MFA_ENCRYPTION_KEY` (Fernet key or passphrase → Fernet) | SETTINGS / APP | `church_system/settings/base.py` (expose setting), `accounts/mfa.py` `_fernet()` |
| Fallback: derive from `SECRET_KEY` if unset (compat) | APP | `accounts/mfa.py` |
| Management command to re-encrypt all `User.mfa_secret` with new key | APP | `accounts/management/commands/reencrypt_mfa_secrets.py` **(new)** |
| `.env.example` + rotation notes | SETTINGS / DOCS | `.env.example`, `AUTHENTICATION.md`, `OPERATIONS_RUNBOOK.md` secret rotation |
| Tests | APP | `accounts/tests_mfa.py` |

**VPS after deploy:** generate key → set env → run reencrypt command in maintenance window → restart → verify MFA login.

#### 4.6.3 Export permission controls

| Change | Tag | File / location |
|--------|-----|-----------------|
| Gate report catalog exports by `can_export_reports_csv|excel|pdf` | APP | `reports/views.py` |
| Gate financial statement exports by `can_export_transactions` (or format-specific if added) | APP | `transactions/views.py` (statement export branches) |
| Confirm giving already uses `can_export_giving` (Current — verify only) | APP | `giving/views.py` |
| Tests for denied export | APP | `reports/tests*.py`, `transactions/tests.py` |
| Docs | DOCS | `KNOWN_LIMITATIONS.md` KL-SEC-03, `SECURITY_VALIDATION_REPORT.md` note, module specs if needed |

**Behavior:** Viewers can still **view** HTML reports when `can_view_reports`; download buttons/endpoints require export perms. UI should hide export links when denied (template/`can` tag) — server still enforces.

---

## 5. Complete file inventory

### 5.1 Application code (APP)

| File | Action |
|------|--------|
| `accounts/mfa.py` | MFA rate-limit helpers; Fernet key from `MFA_ENCRYPTION_KEY` |
| `accounts/mfa_views.py` | Call rate limit on verify |
| `accounts/management/commands/reencrypt_mfa_secrets.py` | **New** |
| `accounts/tests_mfa.py` | Extend |
| `reports/views.py` | Export permission gates |
| `transactions/views.py` | Statement export permission gates |
| `reports/tests*` / `transactions/tests.py` | Extend |
| `church_system/management/commands/backup_database.py` | `--verify`, checksum, post-hook |
| `church_system/tasks.py` | Pass verify/offsite flags if needed |
| `church_system/media_access.py` | **New** — path classification |
| `church_system/media_views.py` (or `views_media.py`) | **New** — auth download + X-Accel-Redirect |
| `church_system/urls.py` | Media download route |
| `church_system/tests_media_access.py` | **New** |
| `church_system/tests_security_hardening.py` | HTTPS cookie / staging alignment tests |
| `church_system/health.py` | Optional Redis-auth warning |

### 5.2 Django settings (SETTINGS)

| File | Action |
|------|--------|
| `church_system/settings/base.py` | `MFA_ENCRYPTION_KEY` setting; backup-related env docs via comments if needed |
| `church_system/settings/production.py` | Review only; change only if Wave 0 finds a real HTTPS bug |
| `church_system/settings/staging.py` | Bind Secure cookies/HSTS to HTTPS mode |
| `.env.example` | HTTPS, Redis password, MFA key, backup hook, Cloudflare notes |

### 5.3 Security configuration (SEC-CFG)

| File | Action |
|------|--------|
| `deploy/nginx/churchhub.conf` | TLS enablement template; CF real IP; public vs private media |
| `deploy/fail2ban/filter.d/churchhub-nginx-auth.conf` | **New** |
| `deploy/fail2ban/jail.d/churchhub-sshd.conf` | **New** |
| `deploy/fail2ban/jail.d/churchhub-nginx-auth.conf` | **New** |
| `deploy/firewall/ufw-churchhub.sh` | **New** |
| `deploy/redis/churchhub-redis.conf.snippet` | **New** |
| `deploy/backup/rclone-gdrive-sync.sh` | **New** |
| `deploy/backup/README.md` | **New** |
| `deploy/nginx/cloudflare-origin.md` | **New** (optional short guide) |

### 5.4 Server / VPS (VPS) — not all committed

| Action | Notes |
|--------|-------|
| Cloudflare SSL Full Strict | Dashboard |
| Certbot or Origin cert install | Host |
| Copy Nginx/Fail2Ban/UFW/Redis configs | Host |
| `rclone` Google Drive remote | Host |
| Set production `.env` HTTPS + Redis password + MFA key | Host |
| `collectstatic`, migrate (if any), restart units | Host |
| Restore drill on staging DB | Host + evidence |

### 5.5 Documentation (DOCS)

| File | Action |
|------|--------|
| `docs/WAVE1_PRODUCTION_HARDENING_PLAN.md` | This plan (created now) |
| `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md` | TLS/CF, Fail2Ban, UFW, Redis, media, backups |
| `docs/OPERATIONS_RUNBOOK.md` | Restore from GDrive; MFA key rotation |
| `docs/PRODUCTION_RUNBOOK.md` | Cross-links |
| `docs/PRODUCTION_SECURITY_CHECKLIST.md` | Checkboxes for Wave 1 |
| `docs/SECURITY/AUTHENTICATION.md` | MFA key + verify rate limit Current |
| `docs/KNOWN_LIMITATIONS.md` | Close/mitigate KL-SEC-01/02/03, KL-OPS notes |
| `docs/SECURITY_AND_DEPLOYMENT_AUDIT.md` | Mark findings addressed / residual |
| `docs/AI_CONTEXT/DOCUMENT_INDEX.md` | Link this plan + audit |

---

## 6. Implementation order (after approval)

```text
1. SETTINGS: staging HTTPS cookie alignment + MFA_ENCRYPTION_KEY + .env.example
2. APP: MFA rate limit + tests
3. APP: MFA Fernet key + reencrypt command + tests
4. APP: export permission gates + tests
5. APP: backup --verify / checksum / post-hook
6. SEC-CFG: Nginx TLS+CF real IP + media public/private
7. APP: media auth view + tests
8. SEC-CFG: Fail2Ban, UFW, Redis snippet, rclone script
9. DOCS: all runbooks / checklists / index
10. VPS: apply configs, rclone, MFA reencrypt, restore drill
11. Smoke: HTTPS login, MFA, export deny, private media deny, backup+Drive sync
```

Suggested PR split (if preferred):

| PR | Contents |
|----|----------|
| PR-A | MFA rate limit + MFA key + export gates + tests |
| PR-B | Backup verify/hook + rclone scripts + docs |
| PR-C | Nginx/Fail2Ban/UFW/Redis + media access + docs |

---

## 7. Test plan

| Area | Tests |
|------|-------|
| MFA | Failed verify lockout; success clears; recovery codes counted |
| MFA key | Encrypt/decrypt with dedicated key; fallback SECRET_KEY; reencrypt command dry-run |
| Exports | User with view-only cannot export CSV/Excel/PDF; exporter can |
| Media | Anonymous denied private path; scoped user allowed; public branding allowed |
| Settings | Staging Secure cookies false when SSL redirect false |
| Backup | `--verify` fails on corrupt gzip; checksum written |
| Manual VPS | Cloudflare Full Strict; UFW; Fail2Ban bans; rclone list remote; restore drill |

---

## 8. Risks and rollback

| Risk | Mitigation |
|------|------------|
| HTTPS redirect loop with Cloudflare | Test `X-Forwarded-Proto`; temporary `SECURE_SSL_REDIRECT=false` only on origin debug |
| Media links break | Auth redirect shim; keep `/media/public/` open |
| MFA reencrypt failure | Backup DB first; keep old key env until verified; command supports dry-run |
| Fail2Ban false positives | Start with moderate thresholds; whitelist office/VPN IPs |
| rclone OAuth expiry | Prefer Google service account for unattended sync |
| Redis requirepass mis-set | Restart order: Redis → web/celery; keep prior URL until ping works |

Rollback: revert Git PR; restore previous Nginx/Fail2Ban files from `/etc` backups taken before apply; restore `.env` from secure copy.

---

## 9. Out of scope (Wave 1)

- Soft-delete schema  
- Absolute session timeout / logout-all devices  
- Password history/expiration  
- Cloudflare WAF custom rules beyond SSL mode + real IP (can be Wave 2)  
- Full S3 migration for all media  
- Raising CI coverage floor to 80% (track separately)

---

## 10. Approval gate

**No application, settings, deploy, or documentation files will be edited for Wave 1 implementation until you approve this plan.**

Please confirm:

1. Approve Wave 0 verification execution (ops checklist) — yes/no  
2. Approve Wave 1 scope as written — yes/no / request cuts  
3. Preferred PR split: single PR vs PR-A/B/C  
4. Google Drive: confirm rclone is acceptable (recommended) vs custom Drive API  
5. Media: confirm Phase A (Nginx internal + Django auth) for Wave 1  

After approval, implementation will follow §6 order and update this document’s status to **IN PROGRESS**.
