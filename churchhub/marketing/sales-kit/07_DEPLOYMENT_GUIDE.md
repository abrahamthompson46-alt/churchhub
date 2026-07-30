# ChurchHub — Deployment Guide (Sales / Ops Pack)

**Audience:** DevOps, hosting partners, customer IT  
**Depth:** Evaluation + go-live orientation  
**Full engineering detail:** `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md`, `docs/DEPLOYMENT_CHECKLIST.md`, `docs/OPERATIONS_RUNBOOK.md`

---

## 1. Supported deploy paths (Current)

| Path | When to use |
|------|-------------|
| **Render.com** | Managed cloud (`render.yaml` web + Redis + Celery + Beat + Postgres) |
| **Docker Compose** | `docker-compose.yml` / `docker-compose.prod.yml` |
| **Self-host** | Gunicorn + Nginx + systemd/Supervisor (`deploy/`) |

Minimum production services: **web · PostgreSQL · Redis · Celery worker · Celery Beat**.

---

## 2. Reference architecture

```text
Client → HTTPS edge (Nginx / Render)
      → Gunicorn → Django
      → PostgreSQL
      → Redis ← Celery worker / Beat
      → Static (WhiteNoise/Nginx) · Media (disk or S3)
```

---

## 3. Environment essentials

| Variable | Production expectation |
|----------|------------------------|
| `DJANGO_ENV` | `production` |
| `DJANGO_SECRET_KEY` | Strong unique secret |
| `DJANGO_DEBUG` | `False` |
| `DATABASE_URL` | PostgreSQL |
| `REDIS_URL` | Required |
| `DJANGO_ALLOWED_HOSTS` | Your hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://…` origins |
| `CHURCHHUB_PUBLIC_URL` | Public site root for emails |

Template: `.env.example`. Production validation refuses insecure combinations.

---

## 4. Release sequence (typical)

1. Provision Postgres + Redis  
2. Set secrets and hosts  
3. Migrate: `python manage.py migrate`  
4. Seed permissions / optional demo: follow `SETUP_GUIDE.md`  
5. `collectstatic`  
6. Start Gunicorn + Celery + Beat  
7. Verify `/health/ready/` and login  
8. Configure backups and log retention  

Docker entrypoints and Render start scripts automate portions of this.

---

## 5. Health & observability

| Endpoint | Purpose |
|----------|---------|
| `/health/` | General |
| `/health/live/` | Liveness |
| `/health/ready/` | Readiness (deps) |
| `/metrics/` | Metrics-ready posture |

Optional: `SENTRY_DSN`. File logs via `CHURCHHUB_FILE_LOGS` / `CHURCHHUB_LOG_DIR`.

---

## 6. Backups & recovery

- Automated DB backup task patterns exist in Celery Beat schedules (verify in target env)  
- Test restore before go-live  
- Media: backup disk volume or S3 bucket versioning  

---

## 7. Customer checklist before pilot

- [ ] DNS + TLS  
- [ ] SMTP / email for portal confirmations & resets  
- [ ] Platform operator account secured  
- [ ] Hierarchy + chart of accounts seeded  
- [ ] Feature flags for payroll/assets decided  
- [ ] Named support channel  

---

## 8. Related runbooks

- `docs/PRODUCTION_RUNBOOK.md` / `OPERATIONS_RUNBOOK.md`  
- `docs/GO_LIVE_CHECKLIST.md`  
- `deploy/nginx/`, `deploy/systemd/`  

**Sales note:** Managed hosting SLAs are commercial terms — not implied by open-source-style self-host docs alone.
