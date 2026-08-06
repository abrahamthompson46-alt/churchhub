# ChurchHub — Security & Deployment Audit

**Type:** Production readiness audit (read-only)  
**Date:** 6 August 2026  
**Auditor role:** Lead Security / DevOps (code + deploy artifacts as source of truth)  
**Constraint:** No application or deploy files were modified for this report  
**Companions:** `KNOWN_LIMITATIONS.md`, `SECURITY_VALIDATION_REPORT.md`, `PRODUCTION_READINESS_REPORT.md`, `DEVELOPMENT/DEPLOYMENT_NOTES.md`, `SECURITY/*`

| Label | Meaning |
|-------|---------|
| **Current** | Observed in code / repo today |
| **Ops gap** | Not represented in repo; must be verified on the live VPS |
| **Accepted (pilot)** | Documented limitation with compensating control |

---

## Executive summary

| Metric | Result |
|--------|--------|
| **Overall readiness** | **7.8 / 10** for controlled production; **not** full enterprise GA |
| **Critical in-repo defects** | None that unconditionally prevent boot when production settings + Redis + Postgres are configured correctly |
| **Critical ops risks** | TLS still optional (Phase A HTTP), media URL exposure, missing Fail2Ban/firewall/offsite backup evidence in repo |
| **Go / No-Go** | **Conditional Go** for a small pilot **after** Wave 0 ops verification; **No-Go** for open internet HTTPS marketing claims until Phase B TLS + media access control |

ChurchHub’s Django production settings, Gunicorn/Nginx/systemd templates, RBAC/tenancy, MFA, and finance integrity controls are substantially stronger than a typical mid-stage ChMS. Remaining risk is concentrated in **ops maturity** (TLS, host firewall, Fail2Ban, backup restore proof), **media confidentiality**, and a short list of **application hardening** items (MFA verify throttling, dedicated MFA crypto key, export permission granularity).

---

## Scorecard

| Area | Score (/10) | Notes |
|------|-------------|-------|
| Django settings / env validation | 8.5 | Strong production refuse path; Phase A HTTP is intentional but risky |
| Deploy stack (Gunicorn/Nginx/systemd) | 8.0 | Solid templates; TLS block still commented; media open by URL |
| Infrastructure (DB/backup/monitor/host) | 6.0 | Backup command exists; Fail2Ban/firewall/Cloudflare **absent from repo** |
| Application security (tenancy/authz/audit) | 8.5 | Strong RBAC + MFA + audit immutability; export/MFA gaps remain |
| **Overall** | **7.8** | |

---

## Methodology

Reviewed:

1. `church_system/settings/{base,production,staging,development}.py`, `church_system/env.py`, `debug_config.py`
2. `gunicorn.conf.py`, `deploy/nginx/churchhub.conf`, `deploy/systemd/*`, `scripts/deploy_selfhost.sh`, `scripts/backup.sh`
3. Health/metrics auth, Celery Beat schedules, backup management command
4. Auth/MFA (`accounts/mfa*`), platform IP middleware, login rate limit, reports export views, `FinancialAuditLog`, media URL mounting
5. Searched repo for Fail2Ban, UFW/iptables, Cloudflare, host cron — **no configs found**

Severity legend:

| Severity | Meaning |
|----------|---------|
| **Critical** | Exploit or misconfig can cause full compromise, silent auth bypass, or production-breaking multi-worker failure |
| **High** | Significant data exposure or control-plane risk under realistic attack/ops error |
| **Medium** | Meaningful gap; acceptable for short pilot with compensating controls |
| **Low** | Hardening / hygiene; track for GA |

---

## 1. Django settings

### Strengths (Current)

- Split settings package with `DJANGO_ENV` selection (`church_system/settings/__init__.py`).
- Production **refuses** `DEBUG=True`, default insecure `SECRET_KEY`, empty/`*` `ALLOWED_HOSTS`, SQLite (unless PA exception), missing Redis (VPS), missing CSRF origins, localhost public URL, missing health token (non-PA).
- `DEBUG` resolution blocks accidental True on production-like hosts unless `DJANGO_ALLOW_DEBUG_IN_PROD`.
- HTTPS mode drives `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS together (`production.py`).
- Proxy trust: `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`.
- Headers: `X_FRAME_OPTIONS=DENY`, nosniff, same-origin referrer.
- Redis cache + `cached_db` sessions when `REDIS_URL` set.
- `.env` is gitignored; template in `.env.example`.

---

### Finding S-01 — Production may run without TLS (Phase A)

| Field | Detail |
|-------|--------|
| **Severity** | **Critical** (if exposed on the public internet over HTTP) / **High** (controlled IP-only pilot with MFA) |
| **Evidence** | `SECURE_SSL_REDIRECT = env_flag(..., True)` but operators set `false` for IP access; cookies Secure flag follows that flag |
| **Risk** | Session, CSRF, and MFA enrollment traffic travel in cleartext; MITM can steal sessions |
| **Impact** | Account takeover of platform/institution users; finance and member PII exposure |
| **Fix** | Complete Phase B (domain + Let’s Encrypt) promptly; keep Phase A only on VPN/private network; never market HTTP IP as “production HTTPS” |

### Finding S-02 — Staging hard-sets Secure cookies when DEBUG=False

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `staging.py`: if `not DEBUG`, `SESSION_COOKIE_SECURE = True` and `CSRF_COOKIE_SECURE = True` even when `SECURE_SSL_REDIRECT` is false |
| **Risk** | Browser will not send Secure cookies over HTTP staging → login loops |
| **Impact** | Staging unusable on HTTP; operators may weaken DEBUG to “fix” login |
| **Fix** | Align staging with production: bind Secure cookies / HSTS to `_https_mode` |

### Finding S-03 — Default `ALLOWED_HOSTS` includes PythonAnywhere hostnames

| Field | Detail |
|-------|--------|
| **Severity** | **Low** |
| **Evidence** | `base.py` default string embeds `churchhub.pythonanywhere.com` |
| **Risk** | Host-header confusion if a misconfigured proxy accepts those hosts on another deploy |
| **Impact** | Usually none when production validation forces explicit hosts; confusing for VPS operators |
| **Fix** | Empty/default to `localhost,127.0.0.1,testserver` only; require explicit hosts in staging/production |

### Finding S-04 — Postgres SSL not required for self-host by default

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** (High if DB is on a separate network without TLS) |
| **Evidence** | `configure_databases`: `sslmode=require` only when `ON_RENDER` or `DB_SSL_REQUIRE` |
| **Risk** | Credentials/data on the wire if Postgres is remote without SSL |
| **Impact** | Credential theft / data interception |
| **Fix** | Set `DB_SSL_REQUIRE=true` for remote DBs; document loopback exception for local socket/127.0.0.1 |

### Finding S-05 — Redis URL examples lack AUTH / TLS

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `.env.example` / docs show `redis://127.0.0.1:6379/0` |
| **Risk** | Unauthenticated Redis on a host with other local users or exposed port stores sessions, rate-limit counters, MFA OTP |
| **Impact** | Session forgery / rate-limit bypass / OTP theft |
| **Fix** | Require Redis `requirepass` (or ACL) on VPS; bind to 127.0.0.1; prefer `rediss://` for managed Redis |

### Finding S-06 — `CSRF_COOKIE_HTTPONLY = False`

| Field | Detail |
|-------|--------|
| **Severity** | **Low** |
| **Evidence** | Explicit in `base.py` / `production.py` (Django default; some JS CSRF patterns need it) |
| **Risk** | XSS can read CSRF cookie (still needs XSS; session cookie remains HttpOnly) |
| **Impact** | Easier CSRF token theft **after** XSS |
| **Fix** | Keep False only if a JS form pattern requires it; otherwise set True and use cookie-less CSRF from forms |

---

## 2. Deployment stack

### Strengths (Current)

- Gunicorn defaults to **`127.0.0.1`** with `forwarded_allow_ips=127.0.0.1` (defense in depth for VPS).
- Nginx proxies with `X-Forwarded-Proto`, timeouts, `client_max_body_size 25m`, static/media aliases, basic hardening headers.
- systemd units: non-root `churchhub`, `NoNewPrivileges`, `PrivateTmp`, journal logging, restart policies, Redis/Postgres ordering.
- WhiteNoise for static when not using Nginx; `collectstatic` in deploy script.
- Health endpoints token-gated; metrics require authenticated platform/staff/superuser.

---

### Finding D-01 — TLS server block still commented (Phase B incomplete in template)

| Field | Detail |
|-------|--------|
| **Severity** | **High** (ops) |
| **Evidence** | `deploy/nginx/churchhub.conf` Phase B block commented; HTTP `server_name _` |
| **Risk** | Operators leave HTTP forever |
| **Impact** | Same as S-01 |
| **Fix** | After certbot, uncomment TLS + HTTP→HTTPS redirect; set Django `SECURE_SSL_REDIRECT=true` |

### Finding D-02 — Media served by Nginx without authentication

| Field | Detail |
|-------|--------|
| **Severity** | **High** |
| **Evidence** | `location /media/ { alias /opt/churchhub/media/; }` — no auth; Django only mounts media when `DEBUG=True` |
| **Risk** | Anyone who learns/guesses a media URL can download member photos, documents, branding, export files |
| **Impact** | PII / document confidentiality breach (UUID paths reduce guessability but not link leakage via email/referrer) |
| **Fix** | Short term: tight filesystem perms + disallow indexing + short-lived signed URLs for sensitive docs. Medium term: auth-gated download views or S3 pre-signed URLs for member documents |

### Finding D-03 — No Cloudflare (or other WAF) configuration in repo

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** (ops) |
| **Evidence** | No Cloudflare origin cert / Real IP / WAF docs in deploy tree |
| **Risk** | Direct-to-origin attacks if DNS points at VPS without CDN/WAF |
| **Impact** | DDoS / bot abuse / origin IP exposure |
| **Fix** | If using Cloudflare: orange-cloud proxy, Authenticated Origin Pulls or firewall allowlist Cloudflare IPs, restore real client IP (`CF-Connecting-IP` / `set_real_ip_from`), WAF rules for `/accounts/login`, `/portal/login` |

### Finding D-04 — systemd hardening incomplete vs enterprise baseline

| Field | Detail |
|-------|--------|
| **Severity** | **Low**–**Medium** |
| **Evidence** | Units set `PrivateTmp` + `NoNewPrivileges` but not `ProtectSystem=strict`, `ProtectHome=true`, `CapabilityBoundingSet=`, `SystemCallFilter=`, etc. |
| **Risk** | Compromised app process has broader filesystem access than necessary |
| **Impact** | Lateral movement after RCE |
| **Fix** | Add ProtectSystem/ProtectHome/ReadOnlyPaths; keep `ReadWritePaths` for logs/media/var/staticfiles |

### Finding D-05 — Static `Cache-Control: immutable` with 7d expiry

| Field | Detail |
|-------|--------|
| **Severity** | **Low** |
| **Evidence** | Nginx `/static/` headers |
| **Risk** | Stale assets if filenames are not content-hashed (WhiteNoise compressed storage usually hashes) |
| **Impact** | UI bugs after deploy until cache expires |
| **Fix** | Confirm Manifest/WhiteNoise hashed names; bump cache-buster query for non-hashed CSS already used in `base.html` |

---

## 3. Infrastructure

### Strengths (Current)

- PostgreSQL-first production path; `pg_dump` backup command + `scripts/backup.sh`.
- Celery Beat schedules daily DB backup + notification purge + health probe.
- Rotating application/security/audit file logs + journald.
- `/health/live|ready/` + token auth for probes.
- CI: Ruff (subset), coverage (fail-under 50), Postgres+Redis job, pip-audit.

### Ops gaps (not in repo)

| Item | Status |
|------|--------|
| Fail2Ban jails | **Absent** |
| UFW / iptables / nftables | **Absent** |
| Host crontab (aside from Celery Beat) | **Absent** (Beat is preferred) |
| Offsite backup replication | **Absent** (local `backups/` only; gitignored) |
| Documented restore drill evidence | Operator-owned (KL-OPS-03) |

---

### Finding I-01 — No Fail2Ban configuration

| Field | Detail |
|-------|--------|
| **Severity** | **High** (ops) |
| **Evidence** | Repo search: no fail2ban filters/jails |
| **Risk** | SSH and HTTP auth brute force only limited by app middleware (and only when Redis works) |
| **Impact** | Credential stuffing / SSH compromise |
| **Fix** | Install Fail2Ban jails for `sshd` and Nginx 401/403 on login paths; ban recurring offenders |

### Finding I-02 — No firewall policy as code

| Field | Detail |
|-------|--------|
| **Severity** | **High** (ops) |
| **Evidence** | No UFW/nftables scripts in `deploy/` |
| **Risk** | Accidental exposure of Postgres (5432), Redis (6379), Gunicorn (if mis-bound) |
| **Impact** | Direct DB/cache compromise |
| **Fix** | UFW default deny; allow 22 (or jump host), 80, 443 only; keep Postgres/Redis on localhost |

### Finding I-03 — Backups are local-only; restore unproven in repo

| Field | Detail |
|-------|--------|
| **Severity** | **High** |
| **Evidence** | `backup_database` writes `backups/churchhub_*.sql.gz`; retention deletes old local files; no offsite sync script |
| **Risk** | VPS disk failure / ransomware destroys DB **and** backups together |
| **Impact** | Catastrophic data loss |
| **Fix** | Copy dumps to offsite object storage daily; encrypt at rest; run and record a restore drill quarterly |

### Finding I-04 — Backup command loads DB password into process env

| Field | Detail |
|-------|--------|
| **Severity** | **Low** |
| **Evidence** | `PGPASSWORD` set for `pg_dump` subprocess |
| **Risk** | Local attackers with process inspection may see password briefly |
| **Impact** | Credential disclosure on shared host |
| **Fix** | Prefer `.pgpass` with 0600 perms or peer auth over local socket |

### Finding I-05 — Monitoring depends on optional Sentry + tokenized health

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | Sentry via `SENTRY_DSN`; health requires `CHURCHHUB_HEALTH_TOKEN` in production validation |
| **Risk** | Silent outages if Sentry unset and no external uptime check |
| **Impact** | Extended downtime unnoticed |
| **Fix** | Enable Sentry; external uptime on `/health/ready/?token=…`; alert on Celery Beat silence |

### Finding I-06 — CI coverage floor is 50%

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `.github/workflows/ci.yml` `--fail-under=50` |
| **Risk** | Security regressions in untested paths (exports, tenancy edge cases) |
| **Impact** | Undetected privilege bugs |
| **Fix** | Raise floor for finance/permissions/accounts packages; keep overall target climbing toward 80% |

---

## 4. Application security

### Strengths (Current)

- Session auth + CSRF; custom `accounts.User`; platform vs institution lanes.
- RBAC via `permissions.services.user_has_permission` + org/church/denomination scoping helpers.
- MFA (TOTP + recovery + email OTP + trusted device) with enrollment secret stability fix.
- Login / portal / password-reset / apply rate limiting (cache-backed — needs Redis).
- Open-redirect hardening (`safe_internal_redirect`).
- `FinancialAuditLog` save/delete immutability guards.
- Health token + authenticated metrics.
- Platform IP allowlist optional; MFA-first posture for dynamic ISPs (by design).

---

### Finding A-01 — MFA verify endpoint not separately rate-limited

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** (High if MFA policy is the only second factor and login lockout does not cover `/accounts/mfa/verify/`) |
| **Evidence** | `LoginRateLimitMiddleware` paths omit MFA verify; KL-SEC-02 |
| **Risk** | Online TOTP brute force within the valid window (mitigated somewhat by 6-digit space + window=2) |
| **Impact** | Second-factor bypass after password theft |
| **Fix** | Cache-backed attempt counters on `mfa_verify` (and recovery codes) per session/IP |

### Finding A-02 — MFA Fernet key derived from `DJANGO_SECRET_KEY`

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `accounts/mfa.py` `_fernet()` hashes `settings.SECRET_KEY`; KL-SEC-01 |
| **Risk** | SECRET_KEY rotation decrypts to failure → all MFA secrets unreadable (already soft-handled as unenrolled) |
| **Impact** | Forced mass re-enrollment; operational lockout of privileged users |
| **Fix** | Introduce dedicated `MFA_ENCRYPTION_KEY` with migration/re-encrypt tooling |

### Finding A-03 — Report exports gated by view permission, not `can_export_reports_*`

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `reports/views.py` uses `can_view_reports` (and finance helpers on some paths); dedicated export helpers exist in `permissions/checks.py` but are not consistently enforced; KL-SEC-03 |
| **Risk** | Users allowed to view on-screen reports can download CSV/Excel/PDF of sensitive aggregates |
| **Impact** | Data exfiltration beyond intended SoD |
| **Fix** | Gate each export format with `can_export_reports_csv|excel|pdf`; audit every export |

### Finding A-04 — Soft-delete / retention not implemented

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | Schema docs: no `is_deleted` columns; AGENTS Planned |
| **Risk** | Hard deletes lose auditability; GDPR-style erasure incomplete |
| **Impact** | Compliance and recovery gaps |
| **Fix** | Design additive soft-delete **with approval**; never claim Current until shipped |

### Finding A-05 — Absolute session timeout / logout-all devices missing

| Field | Detail |
|-------|--------|
| **Severity** | **Low**–**Medium** |
| **Evidence** | Idle timeout via `PlatformSessionMiddleware` + SiteSettings; KL-SEC-04 |
| **Risk** | Long-lived sessions on stolen devices (4h cookie age + trusted device 30d MFA skip) |
| **Impact** | Extended post-theft access |
| **Fix** | Absolute timeout; “logout all sessions”; shorten trusted-device TTL for privileged roles |

### Finding A-06 — Platform IP allowlist optional by default

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** (Accepted for dynamic ISP + MFA) |
| **Evidence** | `REQUIRE_PLATFORM_IP_ALLOWLIST` default `False` in production |
| **Risk** | Password+MFA (or password alone for non-MFA audiences) sufficient from any IP |
| **Impact** | Larger attack surface for `/platform/` |
| **Fix** | Keep MFA required for OWNER/SECURITY; add static/VPN allowlist when available; never rely on residential IPs alone |

### Finding A-07 — Trusted-device cookie skips MFA for 30 days

| Field | Detail |
|-------|--------|
| **Severity** | **Medium** |
| **Evidence** | `TRUSTED_DEVICE_DAYS = 30` in `accounts/mfa.py` |
| **Risk** | Stolen browser profile bypasses MFA |
| **Impact** | Privileged account compromise without second factor |
| **Fix** | Shorter TTL for platform roles; bind to user-agent hash; admin revoke devices |

### Finding A-08 — Password history / expiration not implemented

| Field | Detail |
|-------|--------|
| **Severity** | **Low** |
| **Evidence** | KL-SEC-05; validators cover length/uppercase/common/numeric only |
| **Risk** | Password reuse over time |
| **Impact** | Credential stuffing success after old breach |
| **Fix** | SiteSettings-driven history + max age for privileged roles |

---

## 5. Finding index (priority order)

| ID | Severity | Area | Title |
|----|----------|------|-------|
| S-01 | Critical/High | Settings | HTTP Phase A without TLS on public internet |
| D-02 | High | Deploy | Unauthenticated `/media/` via Nginx |
| I-01 | High | Infra | No Fail2Ban |
| I-02 | High | Infra | No firewall policy as code |
| I-03 | High | Infra | Local-only backups / unproven restore |
| D-01 | High | Deploy | TLS block still commented in Nginx template |
| A-01 | Medium | App | MFA verify not rate-limited |
| A-02 | Medium | App | MFA key tied to SECRET_KEY |
| A-03 | Medium | App | Export permission granularity |
| A-04 | Medium | App | No soft-delete / retention |
| A-05 | Medium | App | No absolute session / logout-all |
| A-06 | Medium | App | Platform IP allowlist optional |
| A-07 | Medium | App | 30-day trusted device |
| S-02 | Medium | Settings | Staging Secure-cookie mismatch |
| S-04 | Medium | Settings | DB SSL not default for remote Postgres |
| S-05 | Medium | Settings | Redis without AUTH in examples |
| I-05 | Medium | Infra | Sentry / uptime optional |
| I-06 | Medium | Infra | CI coverage floor 50% |
| D-03 | Medium | Deploy | No Cloudflare/WAF guidance |
| D-04 | Low–Med | Deploy | systemd Protect* incomplete |
| S-03 | Low | Settings | Default ALLOWED_HOSTS includes PA hosts |
| S-06 | Low | Settings | CSRF cookie not HttpOnly |
| I-04 | Low | Infra | PGPASSWORD in backup env |
| A-08 | Low | App | No password history/expiration |
| D-05 | Low | Deploy | Static immutable cache assumptions |

---

## 6. Recommended remediation waves

### Wave 0 — Ops verification (do first, no code required)

1. Confirm `DJANGO_ENV=production`, `DEBUG=False`, unique `SECRET_KEY`, Postgres, **Redis**, health token.
2. Confirm Gunicorn bound to `127.0.0.1`; UFW allows only 22/80/443.
3. Confirm Celery worker + Beat active; inspect a fresh backup file.
4. Confirm MFA enrolled for OWNER / SECURITY / SUPER_ADMIN / TREASURY.
5. Decide Phase A vs B; schedule TLS if still on HTTP IP.

### Wave 1 — Close Critical/High (code + deploy)

1. Enable Phase B TLS + `SECURE_SSL_REDIRECT=true`.
2. Add Fail2Ban + UFW scripts under `deploy/`.
3. Offsite encrypted backup sync + restore drill runbook entry.
4. Media access control plan (signed URLs or auth views for sensitive docs).
5. Redis `requirepass` + localhost bind.

### Wave 2 — Application hardening

1. Rate-limit MFA verify / recovery.
2. Dedicated `MFA_ENCRYPTION_KEY`.
3. Enforce `can_export_reports_*` on all export paths.
4. Align staging Secure cookies with HTTPS mode.
5. Shorten trusted-device TTL for platform roles.

### Wave 3 — Enterprise GA track

1. Absolute session timeout + logout-all.
2. Soft-delete design (approval required).
3. Password history/expiration.
4. Raise CI coverage floors for security-critical apps.
5. Optional Cloudflare WAF playbook.

---

## 7. Explicit non-findings (do not “fix” without need)

- **No DRF `/api/v1/`** — Current by design; inventing a public API now would expand attack surface.
- **Ledger is not a second GL** — Correct architecture.
- **IP allowlist optional** — Intentional MFA-first tradeoff for dynamic ISPs; tighten when static/VPN IP exists.
- **PythonAnywhere LocMem exception** — Acceptable only on that host class; **not** for multi-worker VPS.

---

## 8. Approval gate

This report is **documentation only**. No settings, Nginx, systemd, or application code were changed.

**Awaiting owner approval** before implementing any Wave 0–3 fixes. Recommended first approval target: **Wave 0 verification checklist + Wave 1 TLS/Fail2Ban/firewall/backups/media**.

---

## 9. Document control

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-08-06 | Initial production readiness audit from live repo |
