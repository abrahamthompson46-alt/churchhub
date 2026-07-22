# ChurchHub — Production Runbook (RC1)

**Version:** `2.0.0-rc1`  
**Date:** 22 July 2026  
**Audience:** On-call engineers, DevOps, platform operators  
**Supersedes for production:** Stale items in older runbooks (e.g. public `/metrics/`)  
**Companions:** `OPERATIONS_MANUAL.md`, `DEPLOYMENT_CHECKLIST.md`, `PRODUCTION_SECURITY_CHECKLIST.md`, `GO_LIVE_CHECKLIST.md`

---

## 1. Service topology

```
                    ┌─────────────┐
   Users ──HTTPS──► │ Edge / TLS  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Gunicorn   │  DJANGO_ENV=production
                    │  (Django)   │  WEB_CONCURRENCY ≥ 2
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │ PostgreSQL  │ │    Redis    │ │ Celery      │
    │   (SoR)     │ │ cache/rate  │ │ worker+Beat │
    └─────────────┘ └─────────────┘ └─────────────┘
           │
    ┌──────▼──────┐
    │ Media disk  │  or S3 via django-storages
    │ / object    │
    └─────────────┘
```

| Component | Required in prod? | Verify |
|-----------|-------------------|--------|
| PostgreSQL | **Yes** | `GET /health/ready/` → `database: ok` |
| Redis | **Yes** | Settings validation + `cache: ok` |
| Celery worker | **Yes** if async email/exports | Task logs |
| Celery Beat | **Yes** for scheduled backups | Beat log at 03:00 UTC backup |
| WhiteNoise | **Yes** (default) | `/static/` 200 |
| Sentry | Recommended | Test event in staging |

---

## 2. Health & monitoring

| Endpoint | Auth | Pass | Fail action |
|----------|------|------|-------------|
| `GET /health/live/` | None | HTTP 200 | Restart web process |
| `GET /health/ready/` | None | HTTP 200 | Stop routing traffic; check DB/migrations/cache |
| `GET /health/` | None | HTTP 200 | Investigate failing check in JSON body |
| `GET /metrics/` | **Staff / platform user** | HTTP 200 | 401 expected for anonymous |

### Readiness checks (`church_system/health.py`)

| Check | Failure symptom | Fix |
|-------|-----------------|-----|
| `database` | Connection error | Restore Postgres connectivity |
| `migrations` | Pending migrations | `python manage.py migrate --noinput` |
| `cache` | Redis down | Restore `REDIS_URL` |
| `debug` | DEBUG=True on prod-like host | `DJANGO_DEBUG=False` |
| `redis` | Missing in production env | Set `REDIS_URL` |

### Logs

- Console + rotating files when `CHURCHHUB_FILE_LOGS` enabled (default prod on)  
- Location: `CHURCHHUB_LOG_DIR` (default `logs/`)  
- Finance audit: `FinancialAuditLog` + report `ReportAccessAuditLog`  
- Platform: `PlatformAuditLog` (immutable)

---

## 3. Deploy procedure (standard release)

1. **Pre-flight:** CI green; `makemigrations --check` clean; review `RELEASE_NOTES_RC1.md`.  
2. **Backup:** Provider snapshot + optional `manage.py backup_database`.  
3. **Deploy web:** Build (`collectstatic`), migrate, restart Gunicorn.  
4. **Deploy worker/beat:** Same image/commit; restart both.  
5. **Smoke:** `/health/ready/`, login, one receipt approve, member list.  
6. **Watch:** Error rate 15 min; Sentry; Celery queue depth.

### Render (primary path)

- Build: `scripts/render_build.sh`  
- Start: `scripts/render_start.sh` (refuses SQLite, runs migrate)  
- See `DEPLOY_RENDER.md`, `render.yaml`

### Rollback

1. Revert to previous release artifact on platform.  
2. **Do not** run backward migrations unless DBA-approved.  
3. If schema forward-only: fix-forward with hotfix.  
4. Restore DB only from pre-deploy backup if data corruption.

---

## 4. Environment variables (production minimum)

| Variable | Required | Notes |
|----------|----------|-------|
| `DJANGO_ENV` | Yes | `production` |
| `DJANGO_SECRET_KEY` | Yes | Strong, unique |
| `DJANGO_DEBUG` | Yes | `False` |
| `DATABASE_URL` | Yes | PostgreSQL |
| `REDIS_URL` | Yes | Production validation |
| `DJANGO_ALLOWED_HOSTS` | Yes | Exact hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes | `https://` origins |
| `CHURCHHUB_PUBLIC_URL` | Yes | Email links |
| `CHURCHHUB_BOOTSTRAP` | First deploy only | `0` after bootstrap |
| SMTP or `EMAIL_*` | Yes | Invites + password reset |
| `SENTRY_DSN` | Recommended | Error tracking |

Full list: `.env.example`

---

## 5. Incident playbooks

### P1 — Site down (5xx / health failing)

1. Check `/health/ready/` JSON for failing check.  
2. Postgres: provider status, connection limits, disk.  
3. Redis: ping, memory, eviction.  
4. Recent deploy? Rollback web if migrations not the cause.  
5. Communicate ETA to pilot sponsors.

### P1 — Suspected data leak (cross-church)

1. Capture user id, URL, timestamp, church context.  
2. Reproduce in staging with isolation test pattern (`UAT-TEN-*`).  
3. Disable impersonation if platform involved.  
4. Hotfix + force password reset if account compromise.  
5. Document in incident log.

### P2 — Finance integrity (wrong approval / double post)

1. Freeze period if needed (`transactions:period_lock`).  
2. Pull `FinancialAuditLog` for transaction ids.  
3. Do **not** delete audit rows (immutable).  
4. Void via approved reversal path only.  
5. Treasurer + pastor sign-off on correction.

### P2 — Celery backlog

1. Check worker alive; broker URL matches web.  
2. Inspect failed tasks in logs.  
3. Scale workers temporarily.  
4. Re-queue export jobs if safe.

### P2 — MFA lockout

1. Platform OWNER resets user via admin or support procedure.  
2. Recovery codes one-time use — re-issue after identity verify.  
3. Never disable `mfa_required_for_privileged` in production without sponsor approval.

### P3 — Email not delivering

1. Platform → Email settings or `EMAIL_*` env.  
2. Send test password reset.  
3. Check provider suppression/bounce.  
4. Fall back to sync send if `CHURCHHUB_ASYNC_EMAIL` was enabled without worker.

---

## 6. Scheduled jobs (Celery Beat)

| Schedule | Task | Disable |
|----------|------|---------|
| Daily 03:00 | `backup_database_task` | `CHURCHHUB_CELERY_BEAT=0` |
| Daily 02:15 | Purge old notifications | same |
| Hourly | Health probe task | same |

Manual backup: `python manage.py backup_database`

---

## 7. Security quick reference (RC1)

- HTTPS: `SECURE_SSL_REDIRECT`, HSTS, secure cookies (`settings/production.py`)  
- CSRF: enabled; trusted origins required  
- XSS: Django auto-escape; avoid `|safe` on user content  
- Sessions: 4h cookie age + idle timeout middleware  
- MFA: enforced for OWNER, SECURITY, SUPER_ADMIN, TREASURY when flag on  
- Metrics: authenticated only (Phase 5)  
- Impersonation: post-login session keys; MFA skipped on target; audit required

---

## 8. RC1 release checklist (ops)

- [ ] Migrations through `*_rc1_consistency` applied  
- [ ] `pillow==12.3.0` in deployed image  
- [ ] Redis + Beat confirmed  
- [ ] Media uploads work end-to-end  
- [ ] Backup artifact from first night verified  
- [ ] `GO_LIVE_CHECKLIST.md` signed for pilot

---

## 9. Escalation

| Level | Contact | When |
|-------|---------|------|
| L1 | On-call engineer | Health fail, deploy issue |
| L2 | Engineering lead | Data integrity, security |
| L3 | Sponsor / finance champion | Pilot communication, waiver |

---

## 10. Related documents

| Doc | Use |
|-----|-----|
| `OPERATIONS_MANUAL.md` | Routine tasks for operators and church admins |
| `OPERATIONS_RUNBOOK.md` | Legacy companion (some endpoints outdated) |
| `KNOWN_LIMITATIONS.md` | Accepted RC1 gaps |
| `RISK_REGISTER.md` | Risk IDs and mitigations |
