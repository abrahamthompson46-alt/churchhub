# ChurchHub — Wave 0 Verification Report

**Date:** 6 August 2026 (v0.3)  
**Mode:** Read-only / non-destructive  
**Production:** `https://zreta.com` · VPS `162.35.179.20`  
**Legacy only:** `churchhub.pythonanywhere.com` (§4)  
**Wave 1:** Not started

| Mark | Meaning |
|------|---------|
| **PASS** | Confirmed by operator VPS evidence and/or remote probe |
| **FAIL** | Confirmed failing vs target production posture |
| **NEEDS ACTION** | Incomplete evidence or residual gap before Wave 0 can close |

---

## Production identity

| Item | Value | Status |
|------|--------|--------|
| Domain | `https://zreta.com` (+ `www.zreta.com`) | **PASS** |
| VPS | `162.35.179.20` · Ubuntu 24.04 | **PASS** |
| Stack | Nginx · Gunicorn/systemd · PostgreSQL · Redis · Cloudflare · LE · rclone | **PASS** |

---

## 1. Confirmed production status

### 1.1 Edge / TLS / HTTPS

| ID | Check | Status | Evidence |
|----|--------|--------|----------|
| C-01 | Cloudflare proxy enabled | **PASS** | Operator confirmed; remote `CF-Ray` observed on at least one of apex/`www` |
| C-02 | HTTP → HTTPS redirect | **PASS** | Operator; remote `http://zreta.com/...` → **301** `https://…` |
| C-03 | LE cert `zreta.com` + `www.zreta.com` | **PASS** | Operator expiry **2026-11-04**; remote SAN match, issuer Let's Encrypt |
| C-04 | `certbot renew --dry-run` | **PASS** | Operator |
| C-05 | Login over HTTPS | **PASS** | `GET /accounts/login/` → **200** |
| C-06 | CSRF cookie `Secure` | **PASS** | Remote `Set-Cookie: csrftoken=…; Secure` |
| C-07 | HSTS header present | **PASS** | `max-age=31536000; includeSubDomains; preload` (may be Cloudflare and/or Django/Nginx — see R-04) |

### 1.2 Host security / data / ops

| ID | Check | Status | Evidence |
|----|--------|--------|----------|
| C-08 | UFW active (OpenSSH + Nginx Full) | **PASS** | Operator |
| C-09 | Fail2Ban active (`sshd` jail, bans seen) | **PASS** | Operator |
| C-10 | PostgreSQL running | **PASS** | Operator |
| C-11 | DB owner `churchhub_db` → `churchhub_user` | **PASS** | Operator |
| C-12 | Backup script works | **PASS** | `/home/churchhub/scripts/churchhub_backup.sh` |
| C-13 | Google Drive upload works | **PASS** | Operator (rclone) |
| C-14 | Health monitor script works | **PASS** | `/home/churchhub/monitoring/churchhub_health_check.sh` |
| C-15 | Cron jobs active | **PASS** | Operator |

---

## 2. Remaining VPS checks

| ID | Check | Status | Notes |
|----|--------|--------|-------|
| R-01 | Cloudflare SSL mode = **Full (Strict)** | **NEEDS ACTION** | Proxy confirmed; **Strict** mode not explicitly evidenced |
| R-02 | Apex + `www` both consistently proxied | **NEEDS ACTION** | Remote probes sometimes hit `Server: cloudflare`, sometimes origin `nginx/1.24.0` depending on name/path — confirm both DNS records are orange-clouded |
| R-03 | Live process uses `DJANGO_ENV=production` / imports `production.py` | **NEEDS ACTION** | No Django shell printout pasted in-chat yet; run flags one-liner or `wave0_verify.sh` |
| R-04 | `SECURE_SSL_REDIRECT` / `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` / `SECURE_HSTS_*` from **Django settings** | **NEEDS ACTION** | Browser shows Secure CSRF + HSTS, but HSTS may be edge-injected; must print `django.conf.settings` values on VPS |
| R-05 | Session cookie `Secure` after successful login | **NEEDS ACTION** | Only CSRF observed anonymously |
| R-06 | Redis up, localhost bind, auth posture | **NEEDS ACTION** | Redis “in stack” confirmed by operator narrative; bind/`requirepass` not printed |
| R-07 | Gunicorn listen `127.0.0.1:8000` only | **NEEDS ACTION** | Need `ss -lntp \| grep 8000` |
| R-08 | systemd `churchhub-web` (+ celery/beat) active | **NEEDS ACTION** | Site up implies web process; unit names/status not pasted |
| R-09 | Fail2Ban jails beyond `sshd` (e.g. nginx-auth) | **NEEDS ACTION** | `sshd` **PASS**; HTTP auth jail not confirmed |
| R-10 | Current backup artifact listing (filename/date) | **NEEDS ACTION** | Script/Drive upload **PASS**; list one local + remote object name/date |
| R-11 | Restore drill documented / dry-run | **NEEDS ACTION** | Upload success ≠ restore readiness |
| R-12 | `/health/ready/` requires health token | **NEEDS ACTION** | Not probed with/without token |
| R-13 | Postgres `5432` not public | **NEEDS ACTION** | UFW helps; confirm listen address |
| R-14 | systemd paths match live tree (`/home/churchhub/...` vs repo `/opt/churchhub`) | **NEEDS ACTION** | Template mismatch is a known footgun for `.env` / `DJANGO_ENV` loading — verify live unit |

### Minimum to mark Wave 0 **COMPLETE**

**PASS required:** R-01, R-03, R-04, R-06, R-07, R-08, R-10 (R-02 strongly recommended same day).

---

## 3. Application security checks

| ID | Check | Status | Notes |
|----|--------|--------|-------|
| A-01 | Public branding via `/media/` (login logos) | **PASS** | Anonymous **200** on `/media/platform/branding/…` (expected for login UX) |
| A-02 | Sensitive media not anonymously readable | **FAIL** | Open `/media/` alias pattern confirmed; any existing member/doc/export object URL is fetchable without auth — Wave 1 Phase A |
| A-03 | MFA verify rate limit | **NEEDS ACTION** | Code gap (Wave 1 Phase C); not a host Wave 0 blocker |
| A-04 | Dedicated `MFA_ENCRYPTION_KEY` | **NEEDS ACTION** | Code gap (Wave 1 Phase C) |
| A-05 | Export gates `can_export_reports_*` | **NEEDS ACTION** | Code gap (Wave 1 Phase C) |
| A-06 | MFA policy audiences on zreta | **NEEDS ACTION** | Confirm Site Settings on prod |
| A-07 | Platform IP allowlist vs MFA-first | **NEEDS ACTION** | Policy confirmation only |

---

## 4. PythonAnywhere legacy environment notes

| Item | Status | Notes |
|------|--------|-------|
| `churchhub.pythonanywhere.com` is **not** production | **PASS** (corrected) | Legacy/staging only |
| Do not treat PA Wave 0 probes as zreta evidence | **PASS** | v0.1 report superseded |
| Wave 1 VPS hardening applies to zreta, not PA by default | **PASS** | Explicit exception required to touch PA |

---

## 5. Wave 0 scoreboard

| Area | Status |
|------|--------|
| Identity / TLS cert / HTTP→HTTPS / UFW / Fail2Ban sshd / DB / backups→Drive / health cron | **PASS** |
| Cloudflare **Full (Strict)** + Django settings proof + Redis bind/auth + Gunicorn bind + units + restore drill | **NEEDS ACTION** |
| Private media posture | **FAIL** (queued for Wave 1; does not block finishing host Wave 0) |
| **Overall Wave 0** | **INCOMPLETE** |

**Gate:** Do **not** start Wave 1 until §2 minimum checks are evidenced and this report is bumped to **COMPLETE**.

---

## 6. Django production settings — root cause (no fix yet)

### What people call the “settings loading issue”

Symptoms typically reported:

- Expectation: with `DJANGO_ENV=production`, Django must enforce `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS.
- Observation (especially during/after Phase A IP HTTP): those protections appear “off” even though the app is “in production.”

### Exact root cause (code)

**`production.py` is often loaded correctly; HTTPS hardening is intentionally gated by one env flag.**

In `church_system/settings/production.py`:

```python
SECURE_SSL_REDIRECT = env_flag("SECURE_SSL_REDIRECT", True)
_https_mode = bool(SECURE_SSL_REDIRECT)

SESSION_COOKIE_SECURE = _https_mode
CSRF_COOKIE_SECURE = _https_mode
SECURE_HSTS_SECONDS = 31536000 if _https_mode else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _https_mode
```

So:

1. Settings selection (`church_system/settings/__init__.py`) imports `production.py` only when `resolve_django_env()` → `production` (`DJANGO_ENV` / `CHURCHHUB_ENV`).
2. Even after `production.py` imports successfully, **all Secure-cookie and HSTS values follow `SECURE_SSL_REDIRECT`**.
3. VPS Phase A docs/operators set `SECURE_SSL_REDIRECT=false` for HTTP-by-IP. That leaves production module active while `_https_mode` is **False**, so cookies are non-Secure and HSTS is **0**.
4. That looks like “production settings not loaded,” but the real mechanism is: **production settings loaded + HTTPS mode disabled by env.**

### Secondary root cause (true non-load of `production.py`)

If the live systemd unit’s `EnvironmentFile` path is wrong (repo template uses `/opt/churchhub/.env`; zreta layout is under `/home/churchhub/...`) **and** the unit does not set `Environment=DJANGO_ENV=production`, then:

- `resolve_django_env()` falls through to **development**
- `__init__.py` imports `development.py`
- `production.py` HTTPS block never runs

The leading `-` on `EnvironmentFile=-/path` makes a missing file non-fatal, which hides this misconfiguration.

### What remote evidence does *not* prove yet

- Secure CSRF on `zreta.com` shows Django is **not** on a naïve development cookie profile, but it does **not** replace a VPS printout of `settings.SECURE_SSL_REDIRECT` / `SESSION_COOKIE_SECURE` / `DJANGO_ENV`.
- HSTS with `preload` may be Cloudflare, not Django (`SECURE_HSTS_PRELOAD` defaults to false in `production.py`).

### Fix posture (for later — not applied now)

Wave 1 Phase A should: (1) confirm live unit env + `django.conf.settings` values; (2) set `SECURE_SSL_REDIRECT=true` now that Cloudflare + LE are live; (3) align systemd paths with `/home/churchhub/...`; (4) only then treat residual mismatches as code bugs.

---

## 7. Asks to close Wave 0

Paste redacted output of:

```bash
bash deploy/scripts/wave0_verify.sh
# plus Cloudflare dashboard: SSL/TLS mode = Full (Strict)
```

Or at minimum the Django flags one-liner from §2 of v0.2 (R-03/R-04) plus `ss -lntp | grep -E '8000|6379|5432'` and `fail2ban-client status`.

---

## Document control

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2026-08-06 | Wrong target (PythonAnywhere) — superseded |
| 0.2 | 2026-08-06 | Corrected to zreta.com; remaining checks listed |
| 0.3 | 2026-08-06 | PASS / FAIL / NEEDS ACTION marks; Django HTTPS gate root cause documented; Wave 1 still blocked |
