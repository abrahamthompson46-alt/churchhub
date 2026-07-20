# ChurchHub — Local Setup Guide

**Audience:** New developers and AI agents bootstrapping a machine  
**Source of truth:** `README.md`, `.env.example`, `requirements.txt`, management commands  
**Companions:** `DEVELOPMENT_RULES.md`, `DEPLOYMENT_NOTES.md`, `TESTING_GUIDE.md`

| Label | Meaning |
|-------|---------|
| **Current** | Supported local setup paths |
| **Planned / Recommended** | Optional improvements |

---

## 1. Prerequisites (Current)

| Requirement | Notes |
|-------------|-------|
| Python **3.13+** | CI and Docker use 3.13; README states 3.13+ |
| `pip` / venv | Standard library `venv` |
| Git | Clone the repository |
| Optional: Docker Desktop | For `docker compose` PostgreSQL + Redis stack |
| Optional: PostgreSQL 16 | If not using SQLite or Docker |
| Optional: Redis | Shared cache / Celery locally |

OS: Windows, macOS, or Linux (README shows Windows activate path).

---

## 2. Python / Django versions (Current)

| Component | Version source |
|-----------|----------------|
| Python | 3.13 (CI `setup-python`, Docker `python:3.13-slim`, Render `PYTHON_VERSION=3.13.0`) |
| Django | `Django>=6.0.6` in `requirements.txt` |
| Gunicorn | `gunicorn>=23.0.0` (prod / Docker) |
| DB drivers | `psycopg2-binary`, `dj-database-url` |

---

## 3. Virtual environment and dependencies (Current)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Do not commit `.venv/`.

---

## 4. Environment variables (Current)

```bash
# Windows
copy .env.example .env

# Linux / macOS
# cp .env.example .env
```

Edit `.env`. Settings load via `_load_dotenv` in `church_system/settings.py` (no python-dotenv package required).

### Minimum local `.env`

| Variable | Local typical |
|----------|---------------|
| `DJANGO_SECRET_KEY` | Any long random string |
| `DJANGO_DEBUG` | `True` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |

SQLite is used automatically when `DATABASE_URL` / `DB_ENGINE=postgresql` are unset (and not on Render).

### Important variables (from `.env.example`)

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Required when `DEBUG=False` |
| `DJANGO_DEBUG` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | Host allowlist |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | HTTPS CSRF origins |
| `CHURCHHUB_PUBLIC_URL` | Absolute links in emails |
| `DATABASE_URL` or `DB_*` | PostgreSQL |
| `REDIS_URL` | Cache / rate-limit sharing |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery |
| `CHURCHHUB_ASYNC_EMAIL` | Async email only if worker running |
| `EMAIL_*` | SMTP fallback (Platform Email UI preferred) |
| `SENTRY_DSN` | Optional monitoring |
| `MEDIA_ROOT` | Optional media path override |
| `DJANGO_SUPERUSER_*` / `CHURCHHUB_BOOTSTRAP` | Production bootstrap (see Deployment) |

Never commit `.env`.

---

## 5. Database setup (Current)

### Option A — SQLite (simplest local)

No extra config. Database file: `db.sqlite3` at project root after migrate/setup.

### Option B — PostgreSQL via env

```env
DB_ENGINE=postgresql
DB_NAME=churchhub
DB_USER=churchhub
DB_PASSWORD=churchhub
DB_HOST=localhost
DB_PORT=5432
```

Or:

```env
DATABASE_URL=postgresql://churchhub:password@localhost:5432/churchhub
```

### Option C — Docker Compose (PostgreSQL + Redis + web + Celery)

```bash
docker compose up --build
```

Opens http://localhost:8000/  
Entrypoint runs migrate, `seed_permissions`, optional demo seed, collectstatic, Gunicorn.

Optional demo data:

```bash
docker compose run --rm -e DJANGO_SETUP_DEMO=1 web python manage.py setup_churchhub --no-input
```

---

## 6. Migrations and seed (Current)

### Recommended one-command local bootstrap

```bash
python manage.py setup_churchhub --no-input
```

This migrates and seeds demo data (see README).

Other useful commands:

```bash
python manage.py migrate
python manage.py seed_permissions
python manage.py setup_churchhub --reset    # Fresh SQLite — DEV ONLY
python manage.py check
```

### Creating a superuser (Current)

| Path | How |
|------|-----|
| Demo bootstrap | `setup_churchhub` creates demo users including Super Admin |
| Manual | `python manage.py createsuperuser` |
| Production | `bootstrap_production` with `DJANGO_SUPERUSER_*` (see Deployment) |

#### Default demo credentials (from README — change in production)

| Role | Username | Password |
|------|----------|----------|
| Super Admin | `admin` | `admin12345` |
| Treasury | `treasury` | `treasury123` |
| Local Pastor | `pastor` | `pastor123` |
| Secretary | `secretary` | `secretary123` |

---

## 7. Running the development server (Current)

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/ → redirects to login.

Health: http://127.0.0.1:8000/health/

### Optional Celery (local)

With Redis available and broker env set:

```bash
celery -A church_system worker -l info
```

Compose already defines a `celery` service. Invitation email is synchronous unless `CHURCHHUB_ASYNC_EMAIL=1`.

---

## 8. Static and media (local)

| Item | Behavior |
|------|----------|
| Static | Project `static/`; WhiteNoise in production settings |
| Media | Default `media/` under project; override with `MEDIA_ROOT` |
| DEBUG | Django may serve media when `DEBUG=True` |

---

## 9. Verify installation

```bash
python manage.py check
python manage.py test
python manage.py runserver
```

Sign in with demo credentials (if seeded) or your superuser.

---

## 10. Common troubleshooting (Current)

| Symptom | Likely cause / fix |
|---------|-------------------|
| `ImproperlyConfigured` secret key | Set `DJANGO_SECRET_KEY` when `DJANGO_DEBUG=False` |
| No such table | Run `migrate` or `setup_churchhub` |
| Permission denials everywhere | Run `seed_permissions` / ensure matrix via setup |
| DisallowedHost | Add host to `DJANGO_ALLOWED_HOSTS` |
| CSRF 403 | Set `DJANGO_CSRF_TRUSTED_ORIGINS` for HTTPS hosts |
| Login lockouts in multi-worker | Use `REDIS_URL` so rate-limit cache is shared |
| Postgres connection errors | Check `DB_*` / `DATABASE_URL` and that DB is running |
| Docker port 8000 in use | Stop other servers or change compose ports |
| Windows script CRLF on Render | Build strips CRLF in `render_build.sh` (deploy concern) |

---

## 11. Planned / recommended

| Item | Notes |
|------|-------|
| Devcontainer | Not in repo today — optional future |
| Make/taskfile | Not required — use manage.py / compose |
| Separate `.env` templates per OS | `.env.example` is the single template |

---

## 12. Related documents

- Production: `DEPLOYMENT_NOTES.md`, root `DEPLOY_RENDER.md`  
- Rules: `DEVELOPMENT_RULES.md`  
- Tests: `TESTING_GUIDE.md`  
- Architecture: `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md`  
