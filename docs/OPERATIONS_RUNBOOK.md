# ChurchHub — Operations Runbook

**Audience:** On-call engineers and platform operators  
**Source of truth:** Live app behavior, health checks, management commands, deploy scripts  
**Companions:** `PRODUCTION_READINESS_REPORT.md`, `DEPLOYMENT_CHECKLIST.md`, `RISK_REGISTER.md`, `DEVELOPMENT/DEPLOYMENT_NOTES.md`

| Label | Meaning |
|-------|---------|
| **Current** | Supported ops actions today |
| **Recommended** | Improve when capacity allows |

---

## 1. Service map (Current)

| Service | Role | How to verify |
|---------|------|----------------|
| Web (Gunicorn) | Django WSGI | `GET /health/`, platform logs |
| PostgreSQL | System of record | Health DB probe; `psql` / provider console |
| Redis (optional) | Cache + rate limits | Health cache probe; `redis-cli ping` |
| Celery worker (optional) | Email/export/depreciation tasks | Worker logs; task results |
| WhiteNoise | Static files | Browser Network tab `/static/` |
| Media filesystem / Disk | Uploads | Upload smoke test |
| Sentry (optional) | Errors / traces | Project Issues |

Primary production path: **Render** web + Postgres. Compose provides local staging with Redis + Celery.

---

## 2. Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live/` | Liveness (process + DB ping) |
| `GET /health/ready/` | Readiness (DB, migrations, cache/redis, debug-safe) |
| `GET /health/` | Full health (+ celery broker informational) |
| `GET /metrics/` | Basic JSON process metrics |

Probes (`church_system.health`):

| Check | Pass criteria |
|-------|----------------|
| `database` | Connection + `SELECT 1` |
| `cache` | set/get/delete probe key |
| `migrations` | No pending migration plan |
| `debug` | `DEBUG` must not be True on production-like hosts |
| `redis` | Required when `DJANGO_ENV=production` |

| HTTP | Meaning |
|------|---------|
| 200 | `status: ok` |
| 503 | `status: degraded` — inspect `*_detail` fields |

**Alerting (Recommended):** Page on consecutive ready/health 503s; warn on elevated 5xx in Sentry.

**Settings:** `DJANGO_ENV=development|staging|production` selects `church_system.settings.*`.

**Celery Beat (Current):** daily notification purge, daily `backup_database` (Postgres), hourly health probe. Logs under `CHURCHHUB_LOG_DIR` (`application.log`, `security.log`, `audit.log`) when file logging enabled.

---

## 3. Routine operations

### Daily / weekly

- [ ] Skim Sentry (or error logs) for new issues
- [ ] Confirm `/health/` 200 from outside the VPC/platform
- [ ] Review failed login lockout noise (abuse vs misconfig)
- [ ] Confirm provider DB backup job succeeded (if scheduled)

### Monthly

- [ ] Run restore drill on a **non-prod** copy (see §5)
- [ ] Review platform audit for impersonation / break-glass
- [ ] Rotate operator passwords / confirm MFA enrollment
- [ ] Review disk usage for `MEDIA_ROOT` / Disk

### After each release

- Follow `DEPLOYMENT_CHECKLIST.md` smoke tests
- Confirm `CHURCHHUB_BOOTSTRAP=0`
- Watch finance posting and remittance for 24–48h

---

## 4. Common management commands

Run via Render Shell, Compose exec, or bastion with production env loaded.

| Command | Purpose |
|---------|---------|
| `python manage.py migrate` | Apply migrations (normally on start) |
| `python manage.py seed_permissions` | Sync permission matrix |
| `python manage.py bootstrap_production --no-input` | First-boot platform owner (bootstrap flag) |
| `python manage.py backup_database --output-dir backups --retention 30` | `pg_dump` gzip archive |
| `python manage.py purge_old_notifications` | Dashboard notification cleanup (if used) |
| `python manage.py check` | Django system checks |

**Never** run destructive DB commands against production without approved change window.

---

## 5. Backup and restore

### Backup (Current)

1. **Provider:** Enable Render (or host) Postgres automatic backups.  
2. **App command:**

```bash
# Directory: --output-dir or CHURCHHUB_BACKUP_DIR (default backups/)
python manage.py backup_database --verify
# Optional: CHURCHHUB_BACKUP_ENCRYPT=true + CHURCHHUB_BACKUP_AGE_RECIPIENT=age1...
```

Requires PostgreSQL client `pg_dump` on the host and DB credentials from settings.
Files are written mode `0600`. Streaming pipeline does not load the full dump into RAM.

3. **Automation:** Celery Beat and/or `churchhub-backup.timer` (see `deploy/systemd/`).  
4. **Offsite (optional):** `deploy/backup/rclone-sync.sh` via `CHURCHHUB_BACKUP_POST_HOOK` — only if remote configured.  
5. **Media:** Copy/snapshot `MEDIA_ROOT` / Disk independently.

### Restore (Current)

Prefer **staging** `DATABASE_URL`. Destructive confirmation is mandatory.

```bash
python manage.py restore_database \
  --input "$CHURCHHUB_BACKUP_DIR/churchhub_YYYYMMDD_HHMMSS.sql.gz" \
  --confirm DESTROY_LOCAL_DATA

# If restoring on a production-configured host / DEBUG=False:
python manage.py restore_database \
  --input ... \
  --confirm DESTROY_LOCAL_DATA \
  --i-understand-production \
  --no-input
```

Encrypted dumps (`.sql.gz.age`) need `--age-identity` or `CHURCHHUB_BACKUP_AGE_IDENTITY`.

### Restore drill checklist

1. Provision empty Postgres (staging).  
2. Point staging `.env` `DATABASE_URL` at that DB.  
3. `restore_database` with confirm flags.  
4. `migrate` (should be no-op if dump is current).  
5. Verify login, one church scoped list, one transaction detail.  
6. Restore media snapshot if testing uploads.  
7. Document RTO/RPO + date/operator in ops log.

### Rollback (backup hardening)

| Change | Rollback |
|--------|----------|
| New flags/env | Unset `CHURCHHUB_BACKUP_*`; old CLI `--output-dir backups --retention 30` still works |
| systemd timer | `sudo systemctl disable --now churchhub-backup.timer` |
| Encryption | `CHURCHHUB_BACKUP_ENCRYPT=false` |
| rclone hook | Unset `CHURCHHUB_BACKUP_POST_HOOK` / remote |

### Secret rotation

- Rotating `DJANGO_SECRET_KEY` invalidates sessions and **breaks Fernet decryption of MFA TOTP secrets** (key derived from `SECRET_KEY`). Plan a maintenance window + re-enrollment or re-encrypt migration before rotating.  
- Rotate SMTP / Redis / DB passwords via platform env; restart web (and Celery).

---

## 6. Incidents

### 0. Downtime response (first 5 minutes)

1. **Confirm blast radius:** Can you reach `https://zreta.com/` or only some pages?
2. **Service status:**

```bash
sudo systemctl status churchhub-web nginx postgresql redis-server \
  churchhub-celery churchhub-celerybeat --no-pager
```

3. **Health JSON** (prefer header token):

```bash
curl -sS -H "X-Health-Token: $CHURCHHUB_HEALTH_TOKEN" https://zreta.com/health/live/ | jq .
curl -sS -H "X-Health-Token: $CHURCHHUB_HEALTH_TOKEN" https://zreta.com/health/ready/ | jq .
```

Interpret `checks.*`: `ok` / `error` / `skipped`. Production `*_detail` is a safe code (`unavailable`, `timeout`, `pending_migrations`, `misconfigured`) — full errors are in server logs only.

4. **Recent errors:**

```bash
sudo journalctl -u churchhub-web -n 100 --no-pager
sudo journalctl -u churchhub-celery -n 50 --no-pager
ls -lah "${CHURCHHUB_LOG_DIR:-logs}/"
```

5. **Listen / exposure:**

```bash
ss -lntp | grep -E ':80 |:443 |:8000 |:5432 |:6379 '
```

6. If Sentry is enabled, open the project for the matching `SENTRY_ENVIRONMENT` / `SENTRY_RELEASE`.
7. Follow the matching subsection below (database / cache / migrations / debug / CSRF).

### A. Health 503 — database

1. Check provider Postgres status / connections.  
2. Confirm `DATABASE_URL` not overwritten.  
3. Inspect web logs for connection errors.  
4. Do not switch to SQLite.  
5. If disk full / failover: restore from backup to new instance (change control).

### B. Health 503 — cache

1. If `REDIS_URL` set: check Redis up, URL, TLS, ACL.  
2. If LocMem only: expect OK unless process crash; multi-worker rate limits still unreliable — add Redis.  
3. Temporary mitigation: reduce workers to 1 until Redis restored (accept capacity loss).

### C. Health 503 — migrations

1. Pending migrations on running code — deploy may have partially failed.  
2. Run `migrate` in Shell during maintenance.  
3. If migrate fails: freeze deploys; restore DB; investigate migration.

### D. Health 503 — debug

1. `DJANGO_DEBUG=True` on production-like host.  
2. Set `DJANGO_DEBUG=False`; remove `DJANGO_ALLOW_DEBUG_IN_PROD`.  
3. Redeploy / restart.

### E. CSRF 403 / DisallowedHost

1. Align `DJANGO_CSRF_TRUSTED_ORIGINS` and `DJANGO_ALLOWED_HOSTS` with exact hostname.  
2. On Render, confirm `RENDER_EXTERNAL_HOSTNAME` still matches custom domain setup.

### F. Login lockouts / cannot log in

1. Confirm Redis shared across workers.  
2. Clear cache keys `login_lock:*` / `login_fail:*` carefully (ops only).  
3. Check MFA: privileged users need enroll/verify; SiteSettings `mfa_required_for_privileged`.  
4. Check `is_active`, maintenance mode, platform IP allowlist.

### G. Media 404 in production

1. Confirm `DEBUG=False` (Django does not serve media via `urls.py` then).  
2. Verify Disk mount / `MEDIA_ROOT` and reverse-proxy or object storage config.  
3. Re-upload if ephemeral disk was wiped on redeploy.

### H. Failed deploy / bad release

1. Freeze auto-deploy if possible.  
2. Roll back web service to previous known-good image/commit.  
3. If migrations forward-only and incompatible: restore DB to pre-migrate snapshot **before** starting old code (coordinate carefully).  
4. Confirm `/health/` 200 and smoke checklist.  
5. Post-incident: root cause in Risk Register / ticket.

### I. Suspected financial integrity issue

1. Stop further void/approve experiments in affected church.  
2. Capture transaction id, church, user, timestamp.  
3. Inspect `FinancialAuditLog` and journal lines (debits = credits).  
4. Prefer **reversal / void workflows** — never silent row edits.  
5. Escalate to finance + engineering lead.

### J. Security incident (account takeover / export abuse)

1. Disable `is_active` on compromised user; force logout via session flush if available.  
2. Rotate passwords for affected privileged accounts; verify MFA.  
3. Review `UserActivityLog`, `PlatformAuditLog`, `ReportAccessAuditLog`.  
4. Preserve logs; do not wipe audit tables.  
5. Notify stakeholders per policy.

---

## 7. Celery (when enabled)

| Task | Purpose |
|------|---------|
| `send_invitation_email_task` | Async invitations (`CHURCHHUB_ASYNC_EMAIL=1`) |
| `generate_report_export_task` | Async report files |
| `run_church_depreciation_task` | Monthly depreciation |

**Ops tips:**

- Broker must match `CELERY_BROKER_URL` / Redis.  
- Without a worker, leave async email **off** (sync default).  
- **Celery Beat is not configured** — schedule backups and recurring jobs via platform cron / external scheduler until Beat is added.

---

## 8. Platform control room

| Path | Use |
|------|-----|
| `/platform/` | SaaS control room |
| `/admin/` | Break-glass Django admin (restricted) |
| `/health/` | LB probe |

Maintenance mode: SiteSettings — blocks institution users; platform operators exempt. Confirm before enabling during business hours.

Impersonation: audit logged; end session via platform impersonation end URL when finished.

---

## 9. Escalation

| Severity | Example | Action |
|----------|---------|--------|
| SEV1 | Site down / data loss risk | Page on-call; restore path; notify owners |
| SEV2 | Finance posting broken for many churches | Freeze related features; investigate journals |
| SEV3 | Single-tenant bug / UI | Ticket; next business day |
| SEV4 | Cosmetic / docs | Backlog |

Keep a current contact list outside this repo (pager, finance lead, platform OWNER).

---

## 10. Related commands / docs

- Deploy checklist: `DEPLOYMENT_CHECKLIST.md`  
- Readiness scorecard: `PRODUCTION_READINESS_REPORT.md`  
- Risks: `RISK_REGISTER.md`  
- Security: `docs/SECURITY/*`  
- Render narrative: `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md`
