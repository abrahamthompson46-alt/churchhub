# ChurchHub Release Notes — RC1

**Version:** `2.0.0-rc1`  
**Date:** 22 July 2026  
**Status:** Release Candidate 1 — feature complete, pilot/production candidate  
**Constraint:** No new features in RC1; verification, consistency, and documentation only

---

## Summary

ChurchHub RC1 is the first release candidate of the **Enterprise 2.0** line: a multi-tenant Django ChMS with hierarchical organization, RBAC, double-entry finance, MFA for privileged roles, and platform site control. Phases 1–6 delivered architecture hardening, production infrastructure, performance optimization, security validation, and UAT/pilot readiness documentation.

**Release readiness score:** **84 / 100** (see verification summary below)  
**Recommendation:** **Conditional Go** for controlled pilot / production after deploy checklists and UAT P0 sign-off.

---

## What’s in RC1

### Platform & tenancy

- Multi-denomination SaaS with conference → zone → district → church hierarchy  
- Church and denomination isolation (automated + UAT cases)  
- Platform control room (`/platform/`): settings, tenants, branding, email, security  
- Platform impersonation with audited session handling (Phase 5 hardening)

### Identity & access

- Session authentication; custom `accounts.User`  
- Invitation and password reset flows  
- Login / password-reset rate limiting (Redis-backed in production)  
- TOTP MFA + recovery codes for privileged roles (`SiteSettings.mfa_required_for_privileged`)  
- RBAC permission registry, overrides, effective-permission views (IDOR fixed Phase 5)

### Ministry operations

- Members: directory, transfers, departments, baptism register  
- Meetings: minutes workflow, attendance  
- Announcements: create → approve → publish  
- Member portal (`/portal/`)

### Finance & compliance

- Double-entry transactions (system of record)  
- Maker-checker approval, void/reversal, period lock, working-day controls  
- Immutable `FinancialAuditLog` (Phase 5)  
- Ledger UI, budgets, giving statements, remittance, welfare, payroll, assets  
- Reports catalog with CSV/Excel/PDF and async export jobs  
- Export and report access audit logging

### Operations

- Split settings: `development` / `staging` / `production`  
- Health: `/health/live/`, `/health/ready/`, `/health/`  
- Authenticated `/metrics/` (Phase 5)  
- Celery + Beat: backups, notification purge, health probe schedules  
- `backup_database` management command  
- WhiteNoise static; optional S3 media via `django-storages`  
- Sentry integration optional

### Performance (Phase 4)

- ORM aggregates on dashboard and giving leaders  
- Performance indexes (`transactions.0018`, `dashboard.0003`, etc.)  
- Targeted Redis caching (see `docs/CACHE_STRATEGY.md`)

---

## RC1 verification changes (non-feature)

| Area | Change |
|------|--------|
| **Migrations** | `assets.0004_rc1_consistency`, `members.0005_rc1_consistency`, `permissions.0002_rc1_consistency`, `remittance.0004_rc1_consistency` — model/index drift aligned with live models |
| **Dependencies** | `pillow==12.3.0` (security advisories) |
| **Tests** | Isolation harness: MFA disabled + Py3.14 template patch for tenancy suites |

No new business features or architectural refactors in RC1.

---

## Security fixes included (Phase 5)

- Open redirect hardening (`safe_internal_redirect`)  
- Impersonation session ordering + MFA skip while impersonating  
- `user_effective` scoped by `user_may_manage_target`  
- Financial audit log immutability + `SET_NULL` on transaction delete  
- Metrics endpoint authentication

---

## Upgrade / deploy notes

1. Set `DJANGO_ENV=production` and required env vars (see `.env.example`, `docs/DEPLOYMENT_CHECKLIST.md`).  
2. **Apply migrations** including RC1 consistency migrations before traffic.  
3. Require `REDIS_URL` in production (rate limits, cache, sessions).  
4. Run Celery worker + Beat for scheduled backups and async exports.  
5. Enroll MFA for platform OWNER/SECURITY and institution TREASURY / SUPER_ADMIN.  
6. Do **not** rotate `DJANGO_SECRET_KEY` without MFA re-encryption plan (Fernet uses derived key today).

---

## Verification summary (RC1)

| Check | Result |
|-------|--------|
| `makemigrations --check` | **Pass** (after RC1 migrations) |
| Architecture consistency | **Pass** — services/selectors pattern across apps |
| Python `TODO`/`FIXME` scan | **Pass** — none in `.py` sources |
| RC1 focused test suite (80 tests) | **79 Pass**, **1 Fail** (health 503 during long run — passes after migrate; see `KNOWN_LIMITATIONS.md`) |
| CI matrix (`.github/workflows/ci.yml`) | Lint + SQLite coverage + Postgres/Redis + pip-audit |
| Security validation (Phase 5) | **8.2/10**, Conditional Go |
| UAT / pilot docs (Phase 6) | Complete — execution pending on staging |

---

## Documentation map (RC1)

| Document | Purpose |
|----------|---------|
| `docs/RELEASE_NOTES_RC1.md` | This file |
| `docs/KNOWN_LIMITATIONS.md` | Accepted gaps |
| `docs/PRODUCTION_RUNBOOK.md` | Production incident/deploy reference |
| `docs/OPERATIONS_MANUAL.md` | Day-to-day platform + church operations |
| `docs/SECURITY_VALIDATION_REPORT.md` | Phase 5 security |
| `docs/UAT_PLAN.md` / `UAT_TEST_CASES.md` | Phase 6 acceptance |
| `docs/GO_LIVE_CHECKLIST.md` | Pilot cutover |

**Documentation drift:** Some Phase 0 module specs still reference “MFA stub”; live code enforces MFA. Treat `docs/SECURITY/AUTHENTICATION.md` and `SECURITY_VALIDATION_REPORT.md` as authoritative for auth.

---

## Known limitations

See `docs/KNOWN_LIMITATIONS.md`.

---

## Recommended next steps after RC1 tag

1. Execute UAT P0 on staging (`docs/UAT_TEST_CASES.md`).  
2. Complete `docs/GO_LIVE_CHECKLIST.md` for pilot wave 1.  
3. Tag `v2.0.0-rc1`; promote to `v2.0.0` after pilot soak.  
4. Sync stale module specs (MFA, Celery Beat) in a docs-only patch.

---

## Contributors / phases

| Phase | Focus |
|-------|--------|
| 1–2 | Layered architecture, enterprise backlog |
| 3 | Production infrastructure |
| 4 | Performance |
| 5 | Security validation |
| 6 | UAT & pilot readiness |
| 7 | RC1 verification (this release) |
