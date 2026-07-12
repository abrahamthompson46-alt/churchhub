# ChurchHub — Deploy to Render.com

Production deployment guide for the ChurchHub Django application on [Render](https://render.com).

## What you get

| Component | Render service |
|-----------|----------------|
| Web app | Python Web Service (Gunicorn + WhiteNoise) |
| Database | PostgreSQL |
| Health check | `GET /health/` |
| Platform control room | `https://your-app.onrender.com/platform/` |

Optional later: Redis on Render for shared cache and Celery workers.

---

## Quick deploy (Blueprint)

1. Push this repository to GitHub.
2. Open [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
3. Connect the repository. Render reads `render.yaml`.
4. Review the plan and click **Apply**.
5. After the first deploy succeeds, open **Environment** on the `churchhub` web service and set:
   - `DJANGO_ALLOWED_HOSTS` → your Render hostname (e.g. `churchhub.onrender.com`)
   - `DJANGO_CSRF_TRUSTED_ORIGINS` → `https://churchhub.onrender.com`
   - `CHURCHHUB_PUBLIC_URL` → `https://churchhub.onrender.com`
   - `DJANGO_SUPERUSER_EMAIL` → your real email
   - `DJANGO_SUPERUSER_PASSWORD` → a strong password (replace the generated one if needed)
6. Set `CHURCHHUB_BOOTSTRAP=0` after the first successful boot (prevents re-running bootstrap on every deploy).

Sign in at `/accounts/login/` with the platform owner credentials, then open `/platform/` for the control room.

---

## Manual deploy (without Blueprint)

### 1. PostgreSQL database

1. **New** → **PostgreSQL**
2. Name: `churchhub-db`
3. Copy the **Internal Database URL**

### 2. Web service

1. **New** → **Web Service**
2. Connect your Git repo
3. Settings:

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build Command | `chmod +x scripts/render_build.sh scripts/render_start.sh && ./scripts/render_build.sh` |
| Start Command | `./scripts/render_start.sh` |
| Health Check Path | `/health/` |

### 3. Environment variables

| Variable | Required | Example |
|----------|----------|---------|
| `DJANGO_DEBUG` | Yes | `False` |
| `DJANGO_SECRET_KEY` | Yes | long random string |
| `DATABASE_URL` | Yes | from Render PostgreSQL |
| `DJANGO_ALLOWED_HOSTS` | Yes | `your-app.onrender.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes | `https://your-app.onrender.com` |
| `CHURCHHUB_PUBLIC_URL` | Yes | `https://your-app.onrender.com` |
| `DJANGO_SUPERUSER_USERNAME` | Bootstrap | `platform` |
| `DJANGO_SUPERUSER_EMAIL` | Bootstrap | `you@example.com` |
| `DJANGO_SUPERUSER_PASSWORD` | Bootstrap | strong password |
| `CHURCHHUB_BOOTSTRAP` | First deploy only | `1` then `0` |
| `PYTHON_VERSION` | Recommended | `3.13.0` |
| `SENTRY_DSN` | Optional | Sentry project DSN |
| `REDIS_URL` | Optional | Render Redis internal URL |

Render automatically sets `RENDER=true` and `RENDER_EXTERNAL_HOSTNAME`; the app adds these to `ALLOWED_HOSTS` and CSRF origins.

---

## First-time bootstrap

On first deploy with `CHURCHHUB_BOOTSTRAP=1`, the start script runs:

```bash
python manage.py migrate --noinput
python manage.py seed_permissions
python manage.py bootstrap_production --no-input
```

This creates:

- Permission matrix
- Default subscription plans and payment methods
- Built-in denominations
- Platform owner (`DJANGO_SUPERUSER_*` env vars)

It does **not** create demo treasury/pastor users or sample transactions.

To also seed a demo church hierarchy (still no sample transactions):

```bash
CHURCHHUB_BOOTSTRAP_DEMO=1
```

Run that only once via Render Shell, then remove it.

---

## Post-deploy checklist

- [ ] Sign in as platform owner → `/platform/`
- [ ] Update **Site Settings** (name, support email)
- [ ] Configure **Branding** and **Email (SMTP)** for invitations
- [ ] Review **Plans** and **Payment Methods**
- [ ] Provision your first tenant via **Provision Tenant** or approve `/apply/` applications
- [ ] Set `CHURCHHUB_BOOTSTRAP=0`
- [ ] Change platform owner password if a generated one was used
- [ ] Optional: add custom domain in Render and update `DJANGO_ALLOWED_HOSTS` + `DJANGO_CSRF_TRUSTED_ORIGINS`

---

## Media uploads (logos, attachments)

Render web service disks are **ephemeral** — uploaded files are lost on redeploy unless you attach persistent storage.

Options:

1. **Render Disk** (paid): mount at e.g. `/var/data` and set `MEDIA_ROOT=/var/data/media`
2. **Object storage** (recommended at scale): S3-compatible bucket + `django-storages` (future enhancement)
3. **Re-upload** after redeploy for small deployments

---

## Operations

| Task | How |
|------|-----|
| Run migrations | Automatic on each deploy (`render_start.sh`) |
| Health check | `GET /health/` |
| Render Shell | Dashboard → Service → Shell → `python manage.py ...` |
| Backup DB | Render PostgreSQL → Backups (plan-dependent) or `python manage.py backup_database` via Shell |
| View logs | Render Dashboard → Logs |

---

## Troubleshooting

**502 / app not starting**
- Check Logs for migration or bootstrap errors.
- Confirm `DATABASE_URL` is linked to the web service.
- Ensure `DJANGO_SUPERUSER_PASSWORD` is set when `CHURCHHUB_BOOTSTRAP=1`.

**CSRF / 403 on login**
- Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://your-exact-hostname.onrender.com`

**Static files missing**
- Build must run `collectstatic` (included in `scripts/render_build.sh`).

**DisallowedHost**
- Add hostname to `DJANGO_ALLOWED_HOSTS` or rely on `RENDER_EXTERNAL_HOSTNAME` (auto-added).

---

## Local production smoke test

```bash
export DJANGO_DEBUG=False
export DJANGO_SECRET_KEY=local-prod-test-key-change-me
export DATABASE_URL=postgresql://...
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
chmod +x scripts/render_build.sh scripts/render_start.sh
./scripts/render_build.sh
CHURCHHUB_BOOTSTRAP=1 DJANGO_SUPERUSER_PASSWORD='YourStrongPass123!' ./scripts/render_start.sh
```
