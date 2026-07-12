# ChurchHub

Enterprise Church Management System for local churches, districts, zones, and conferences.

## Stack

- **Django 6+** / Python 3.13+
- **PostgreSQL** (production) or **SQLite** (development)
- **Bootstrap 5** UI with a shared design system

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
copy .env.example .env          # set DJANGO_SECRET_KEY

python manage.py setup_churchhub --no-input
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in.

## Default demo credentials

Created by `setup_churchhub` (change in production):

| Role | Username | Password |
|------|----------|----------|
| Super Admin | `admin` | `admin12345` |
| Treasury | `treasury` | `treasury123` |
| Local Pastor | `pastor` | `pastor123` |
| Secretary | `secretary` | `secretary123` |

## Architecture

```
Conference → Zone → District → Church
```

| App | Purpose |
|-----|---------|
| `accounts` | Users, invitations, activity log |
| `permissions` | Role matrix, overrides, RBAC |
| `organization` | Hierarchy CRUD |
| `members` | Directory, transfers, departments, gifts |
| `transactions` | Ledger, approvals, periods, reconciliation |
| `budgets` | Budget planning UI |
| `giving` | Member giving statements |
| `reports` | Analytics + CSV/Excel/PDF export |
| `meetings` | Meetings, minutes, attendance |
| `announcements` | News with approval workflow |
| `dashboard` | Home, notifications, cut-off |

Business logic lives in **services** (`transactions/services.py`, `permissions/services.py`, etc.). Views should stay thin.

### Thin apps (UI / reporting facades)

| App | Models live in | Role |
|-----|----------------|------|
| `budgets` | `transactions.Budget` | Budget planning CRUD UI |
| `giving` | `transactions` ledger | Member giving statements |
| `reports` | `reports/registry.py` + services | Analytics catalog and exports |

## Management commands

```bash
python manage.py setup_churchhub              # Migrate + seed demo data
python manage.py setup_churchhub --reset      # Fresh SQLite DB (dev only)
python manage.py bootstrap_production         # Production bootstrap (Render/VPS)
python manage.py seed_permissions             # Sync permission matrix from registry
python manage.py check
python manage.py test
```

## Production checklist

1. Set `DJANGO_DEBUG=False` and a strong `DJANGO_SECRET_KEY`
2. Use PostgreSQL (`DB_ENGINE=postgresql` + DB_* vars)
3. Set `DJANGO_ALLOWED_HOSTS` to your domain(s)
4. Run `python manage.py migrate` and `python manage.py seed_permissions`
5. Run `python manage.py collectstatic`
6. Serve with Gunicorn/uWSGI behind HTTPS

Health check: `GET /health/` → `{"status": "ok", "service": "churchhub"}`

## Deploy to Render.com

See **[DEPLOY_RENDER.md](DEPLOY_RENDER.md)** for the full production guide.

Quick steps:

1. Push to GitHub
2. Render → **New** → **Blueprint** → select this repo (`render.yaml` included)
3. Set `DJANGO_SUPERUSER_PASSWORD`, email, and your `onrender.com` hostname in Environment
4. After first deploy, set `CHURCHHUB_BOOTSTRAP=0`
5. Sign in → `/platform/` (control room)

## Docker (PostgreSQL staging)

```bash
docker compose up --build
```

First run applies migrations and seeds permissions. Open http://localhost:8000/

Load demo data (optional):

```bash
docker compose run --rm -e DJANGO_SETUP_DEMO=1 web python manage.py setup_churchhub --no-input
```

Environment variables for the `web` service are defined in `docker-compose.yml`. Override secrets before any real deployment.

## Tests

```bash
python manage.py test
```

CI runs the full suite on push/PR to `main`, `master`, and `develop`.

## Documentation

See [AGENTS.md](AGENTS.md) for architecture rules, financial integrity constraints, and AI/developer workflow.
