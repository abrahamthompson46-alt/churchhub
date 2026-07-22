# ChurchHub — Deployment Checklist

**Audience:** Operators deploying to production (Render primary; Docker self-host secondary)  
**Source of truth:** `render.yaml`, `scripts/render_*.sh`, `church_system/settings.py`, `.env.example`  
**Companions:** `PRODUCTION_READINESS_REPORT.md`, `OPERATIONS_RUNBOOK.md`, `RISK_REGISTER.md`, `DEVELOPMENT/DEPLOYMENT_NOTES.md`, root `DEPLOY_RENDER.md`

Use this checklist for every production (or production-like) release. Check boxes in your change ticket or runbook copy — do not commit secrets.

---

## A. Pre-deploy (environment & secrets)

- [ ] Target branch CI green (`lint` + `test-sqlite` + `test-postgresql` on Python 3.13)
- [ ] `DJANGO_ENV=production` (or `DJANGO_SETTINGS_MODULE=church_system.settings.production`)
- [ ] `DJANGO_DEBUG=False`
- [ ] Strong unique `DJANGO_SECRET_KEY` (never reuse insecure default)
- [ ] `DATABASE_URL` linked to managed PostgreSQL (not SQLite)
- [ ] `DJANGO_ALLOWED_HOSTS` includes exact production hostname(s)
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` includes `https://<exact-host>`
- [ ] `CHURCHHUB_PUBLIC_URL` set to public HTTPS base URL
- [ ] `REDIS_URL` set (**required** for production settings validation)
- [ ] Celery worker + Beat running when async email / scheduled backups are expected
- [ ] `SENTRY_DSN` + `SENTRY_ENVIRONMENT` set (strongly recommended)
- [ ] SMTP configured (Platform → Email **or** `EMAIL_*` env fallback)
- [ ] `SECURE_SSL_REDIRECT=True` (default when not DEBUG) unless edge terminates TLS specially
- [ ] Media strategy chosen: Render Disk (`MEDIA_ROOT`) **or** S3 (`AWS_STORAGE_BUCKET_NAME`)
- [ ] Provider PostgreSQL automated backups enabled
- [ ] Migrations reviewed for this release (no destructive drops without approval)

### First-ever environment only

- [ ] `CHURCHHUB_BOOTSTRAP=1`
- [ ] `DJANGO_SUPERUSER_USERNAME` / `EMAIL` / `PASSWORD` set (strong password)
- [ ] Optional: `CHURCHHUB_BOOTSTRAP_DEMO` only if demo hierarchy is intentional

### Subsequent deploys

- [ ] `CHURCHHUB_BOOTSTRAP=0` (or unset)
- [ ] Confirm secret rotation policy if `DJANGO_SECRET_KEY` changes (MFA Fernet depends on it — see Risk Register)

---

## B. Build & start (Render)

- [ ] Blueprint / service uses `scripts/render_build.sh` (install + `collectstatic`)
- [ ] Start uses `scripts/render_start.sh`
- [ ] Start refuses missing `DATABASE_URL` and refuses SQLite
- [ ] `migrate --noinput` succeeds
- [ ] `seed_permissions` succeeds
- [ ] Bootstrap ran once successfully (first deploy only)
- [ ] Gunicorn listening on `$PORT` with intended `WEB_CONCURRENCY` / `GUNICORN_TIMEOUT`

### Docker / Compose (staging or self-host)

- [ ] Override all default weak secrets from `docker-compose.yml`
- [ ] Set `DJANGO_DEBUG=False` for any internet-facing compose deploy
- [ ] Postgres + Redis healthy before web
- [ ] If using Celery tasks in prod: worker service running with matching broker URL
- [ ] Reverse proxy (Nginx/Caddy) serves TLS + media if not using platform edge

---

## C. Smoke tests (immediately after deploy)

- [ ] `GET /health/live/` → HTTP 200
- [ ] `GET /health/ready/` → HTTP 200 (DB, migrations, cache/redis, debug-safe)
- [ ] `GET /health/` → HTTP 200; checks include `database`, `cache`, `migrations`, `debug`
- [ ] Staff login `/accounts/login/` works
- [ ] Portal login `/portal/login/` works (if portal used)
- [ ] Failed login eventually rate-limits (verify shared Redis if multi-worker)
- [ ] Platform owner can open `/platform/`
- [ ] MFA enroll/verify for privileged role (if `mfa_required_for_privileged`)
- [ ] Institution dashboard loads for a test church user
- [ ] Create/approve a small test journal (or use ledger receipt) in a non-prod church if available
- [ ] Export a small CSV and confirm `ReportAccessAuditLog` / domain export audit
- [ ] Static assets load (CSS/JS via WhiteNoise)
- [ ] Media upload + retrieve works under chosen media strategy
- [ ] Password reset email delivers
- [ ] Sentry receives a test event (optional deliberate 500 in staging only)

---

## D. Post-bootstrap hardening (first deploy)

- [ ] Set `CHURCHHUB_BOOTSTRAP=0` and redeploy or update env
- [ ] Change platform owner password if it was generated/shared
- [ ] Enroll MFA for OWNER / SECURITY / SUPER_ADMIN / TREASURY
- [ ] Configure Site Settings (session timeout, lockout thresholds, branding)
- [ ] Configure plans / subscriptions as required
- [ ] Approve or provision first real tenant
- [ ] Restrict Django `/admin/` to break-glass operators only
- [ ] Document operator contacts and escalation

---

## E. Release documentation

- [ ] Version / release notes recorded
- [ ] Migration notes attached if schema changed
- [ ] Rollback plan known (previous image + DB restore point)
- [ ] Risk Register items accepted or mitigated for this release
- [ ] On-call knows `OPERATIONS_RUNBOOK.md` location

---

## F. Rollback triggers

Rollback or freeze traffic if any of:

- [ ] `/health/` returns 503 for > 5 minutes after deploy
- [ ] Widespread 500s in Sentry / logs
- [ ] Cannot authenticate privileged operators
- [ ] Migrations partially applied with data risk (stop; restore from backup — do not invent fixes under load)
- [ ] Financial posting systematically unbalanced / refused incorrectly for all churches

Rollback steps: see `OPERATIONS_RUNBOOK.md` → Incident: failed deploy.

---

## Quick env matrix (production)

| Variable | Required | Notes |
|----------|----------|-------|
| `DJANGO_DEBUG` | Yes | `False` |
| `DJANGO_SECRET_KEY` | Yes | Unique |
| `DATABASE_URL` | Yes | Postgres |
| `DJANGO_ALLOWED_HOSTS` | Yes | Hostname(s) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes | HTTPS origins |
| `CHURCHHUB_PUBLIC_URL` | Yes | Absolute URL |
| `REDIS_URL` | Strongly yes | Multi-worker |
| `SENTRY_DSN` | Recommended | Errors |
| `MEDIA_ROOT` | If Disk | Persistent path |
| `CELERY_BROKER_URL` | If async | Worker must run |
| `CHURCHHUB_ASYNC_EMAIL` | Optional | Only with worker |
| `CHURCHHUB_BOOTSTRAP` | First only | Then `0` |
