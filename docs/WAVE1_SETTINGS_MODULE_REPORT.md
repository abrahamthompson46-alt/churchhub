# Wave 1 — DJANGO_SETTINGS_MODULE / production loading report

**Status:** FIXED (implemented)  
**Date:** 6 August 2026  
**Goal:** Production VPS, systemd, Gunicorn, and Django shell consistently load production settings via `DJANGO_ENV`.

---

## 1. Verdict

| Mode | What happens | Looks like |
|------|----------------|------------|
| **A — Wrong settings package** | `development.py` imported instead of `production.py` | Soft cookies; `settings.DJANGO_ENV == "development"` |
| **B — Production loaded, HTTPS off** | `production.py` loads but `SECURE_SSL_REDIRECT=false` | Secure cookies / HSTS appear “off” |

Mode A is fixed below. Mode B is ops (`SECURE_SSL_REDIRECT=true` when TLS is live).

---

## 2. Settings loading flow (Current — after fix)

```
manage.py / wsgi.py / asgi.py / celery.py
  → DJANGO_SETTINGS_MODULE=church_system.settings  (default)
  → settings/__init__.py
       → ensure_dotenv_loaded()     # project .env; never overwrites process env
       → resolve_django_env()
       → import production | staging | development
            → base.py → ensure_dotenv_loaded() (idempotent)
```

| Entry point | Behavior |
|-------------|----------|
| manage.py shell / migrate | Same package; `.env` `DJANGO_ENV` now visible |
| Gunicorn (wsgi) | Same |
| Celery | Same |
| systemd | **Unchanged** — still `DJANGO_SETTINGS_MODULE=church_system.settings` + `Environment=DJANGO_ENV=production` |

Process environment variables always win over `.env`.

---

## 3. Root cause A (fixed)

Previously `load_dotenv` ran only inside `base.py`, **after** `__init__.py` had already chosen the environment module. Interactive shell without an exported `DJANGO_ENV` selected development even when `.env` said `production`.

---

## 4. Fix applied

| Change | File |
|--------|------|
| `project_root()`, `ensure_dotenv_loaded()` | `church_system/env.py` |
| Load `.env` before `resolve_django_env()` | `church_system/settings/__init__.py` |
| Idempotent dotenv via helper | `church_system/settings/base.py` |
| Regression tests | `church_system/tests_settings_loading.py` |
| Docs | this file, `DEPLOYMENT_NOTES.md`, `SETUP_GUIDE.md` |
| Systemd units | **no change** |

---

## 5. Verify

```bash
.venv/bin/python manage.py shell -c "from django.conf import settings; print(settings.DJANGO_ENV, settings.DEBUG, settings.SESSION_COOKIE_SECURE)"
```

Expect production VPS: `production False True` (when `SECURE_SSL_REDIRECT=true`).
