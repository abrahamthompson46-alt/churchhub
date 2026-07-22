# ChurchHub v1.0.0 — Release Notes

**Release date:** 22 July 2026  
**Status:** General Availability (GA)  
**Type:** Production launch — feature complete, no new capabilities in this release

---

## Overview

ChurchHub **v1.0.0** is the first General Availability release of the enterprise Church Management System. It delivers multi-tenant church administration from platform operators through local treasurers and secretaries, with double-entry finance, RBAC, MFA, and audited workflows.

This release packages the RC1 candidate (`docs/RELEASE_NOTES_RC1.md`) for production deployment after verification and operational checklists.

---

## Highlights

| Area | Capability |
|------|------------|
| **Tenancy** | Denomination wall + church scope on all church-owned data |
| **Finance** | Maker-checker, period lock, working day, immutable audit trail |
| **Security** | MFA for privileged roles, rate-limited login, HTTPS production defaults |
| **Operations** | Health probes, scheduled DB backups, Celery async exports |
| **Ministry** | Members, meetings, announcements, reports, giving |

---

## Upgrade from RC1 / pilot

1. Tag / deploy commit with `v1.0.0`.  
2. `python manage.py migrate --noinput` (includes RC1 consistency migrations).  
3. `python manage.py collectstatic --noinput`.  
4. Restart web, Celery worker, and Celery Beat.  
5. Verify `/health/ready/` → HTTP 200.  
6. Complete smoke tests (see `docs/GO_LIVE_CHECKLIST.md`).  
7. Monitor 72 hours per `docs/PRODUCTION_RUNBOOK.md`.

No database destructive migrations in this release.

---

## Deployment verification (Phase 8)

### Pre-launch (release engineering)

| Check | Status |
|-------|--------|
| Migrations complete (`makemigrations --check`) | ✓ Pass |
| GA verification tests (44 tests: infra, isolation, MFA, finance) | ✓ Pass |
| `collectstatic` | ✓ Pass (147 assets) |
| Health `/health/live/`, `/health/ready/`, `/health/` | ✓ HTTP 200 |
| `/metrics/` anonymous | ✓ HTTP 401 |
| `check --deploy` (development env) | ⚠ Expected warnings (DEBUG, HSTS — production settings resolve) |

### Production environment (operator sign-off required)

| Check | Operator |
|-------|----------|
| PostgreSQL healthy | Ops |
| Redis healthy | Ops |
| Celery worker + Beat | Ops |
| HTTPS + domain + CSRF origins | Ops |
| SMTP / email delivery | Ops |
| Scheduled backups + restore drill | Ops |
| Sentry / monitoring | Ops |
| File logging | Ops |

Use `docs/DEPLOYMENT_CHECKLIST.md`, `docs/GO_LIVE_CHECKLIST.md`, and `docs/PRODUCTION_SECURITY_CHECKLIST.md` for production sign-off.

---

## Smoke-test matrix (route + automated coverage)

| Module | Route smoke | Automated regression |
|--------|-------------|----------------------|
| Login | `/accounts/login/` | `accounts.tests_mfa`, login rate tests |
| Dashboard | `dashboard:home` | `dashboard.tests` |
| Members | `members:list` | Tenant + denomination isolation |
| Transactions | `transactions:pending_approvals` | `transactions.tests_auto_approve` |
| Giving | `giving:index` | `giving.tests` |
| Reports | `reports:index` | `reports.tests_export_audit` |
| Remittance | `remittance:*` | `remittance.tests` |
| Payroll | `payroll:employee_list` | `payroll.tests` |
| Assets | `assets:asset_list` | `assets.tests` |
| Meetings | `meetings:*` | `meetings.tests` |
| Announcements | `announcements:announcement_list` | `announcements.tests` |
| Permissions | `permissions:matrix` | `permissions.tests_layers` |
| Platform | `sitecontrol:dashboard` | `sitecontrol.tests` |

Full CI suite: `.github/workflows/ci.yml` (lint, SQLite+coverage, Postgres+Redis, pip-audit).

---

## Known issues at GA

See `docs/KNOWN_LIMITATIONS.md`. None are Critical when production is configured with Redis, Postgres, TLS, and applied migrations.

---

## Support & documentation

| Document | Purpose |
|----------|---------|
| `docs/OPERATIONS_MANUAL.md` | Day-to-day operations |
| `docs/PRODUCTION_RUNBOOK.md` | Incidents and deploy |
| `docs/KNOWN_LIMITATIONS.md` | Accepted gaps |
| `docs/UAT_TEST_CASES.md` | Acceptance reference |

---

## Thank you

Phases 1–8 prepared architecture, security, performance, UAT, RC1, and GA release. Monitor closely for the first **72 hours** after production cutover.
