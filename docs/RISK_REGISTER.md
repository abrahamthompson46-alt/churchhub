# ChurchHub — Risk Register

**Type:** Production risk register (read-only assessment)  
**Date:** 21 July 2026  
**Source of truth:** Live code + Phase 1 backlog + production readiness audit  
**Companions:** `PRODUCTION_READINESS_REPORT.md`, `DEPLOYMENT_CHECKLIST.md`, `OPERATIONS_RUNBOOK.md`, `PHASE_1_ENTERPRISE_BACKLOG.md`

| Severity | Meaning |
|----------|---------|
| **Critical** | Likely to cause outage, data loss, or security failure in production as configured |
| **High** | Significant integrity, security, or scale impact; mitigate before broad rollout |
| **Medium** | Important hardening; acceptable short-term with monitoring |
| **Low** | Debt / UX / polish; schedule in Phase 2 |

| Status | Meaning |
|--------|---------|
| **Open** | Not fully mitigated |
| **Accepted** | Known; go-live allowed with compensating controls |
| **Mitigated** | Control in place (verify periodically) |
| **Closed** | No longer applicable |

Effort: **S** ≤ 1 day · **M** 2–5 days · **L** > 1 week

---

## Summary

| Severity | Open count (approx.) |
|----------|----------------------|
| Critical | 2 |
| High | 6 |
| Medium | 8 |
| Low | 5 |

Overall readiness: **7.2 / 10** — conditional production (see Production Readiness Report).

---

## Critical

### R-01 · LocMem cache with multiple Gunicorn workers

| Field | Detail |
|-------|--------|
| **Severity** | Critical |
| **Status** | Mitigated (production settings require `REDIS_URL`; Render blueprint includes Redis) |
| **Area** | Security / Infrastructure |
| **Description** | Without `REDIS_URL`, Django uses `LocMemCache`. Login rate limits and cached data are **per worker**. |
| **Impact** | Credential stuffing effectiveness; uneven UX; permission cache drift |
| **Likelihood** | Low when using production settings / blueprint |
| **Mitigation** | Production validation refuses missing Redis; `render.yaml` links Redis; Compose includes Redis |
| **Effort** | S |
| **Owner** | Ops |

### R-02 · Ephemeral / unserved media in production

| Field | Detail |
|-------|--------|
| **Severity** | Critical (if uploads matter) |
| **Status** | Open until Disk/object storage + serving path |
| **Area** | Infrastructure / DR |
| **Description** | Default filesystem media; Render disk ephemeral without mount. `urls.py` serves media only when `DEBUG=True`. |
| **Impact** | Lost uploads on redeploy; 404 for attachments/images in prod |
| **Mitigation** | Render Disk + `MEDIA_ROOT`; or S3 + django-storages (not wired yet); reverse-proxy media when self-hosting |
| **Effort** | S–M |
| **Owner** | Ops / Eng |

---

## High

### R-03 · Test harness / CI confidence on Python 3.14

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Open |
| **Area** | CI/CD |
| **Description** | Full suite (599) showed failures/errors from MFA redirect (302) and Py3.14 `Context.__copy__` in Django test client. CI pins 3.13 (Render also 3.13) — local 3.14 can false-alarm. |
| **Impact** | Missed regressions if engineers ignore “red” suites; false confidence if only partial tests run |
| **Mitigation** | Shared ViewTestMixin (MFA off + template store patch); pin local/runtime to 3.13 or fix harness for 3.14 |
| **Effort** | M |
| **Owner** | Eng |
| **Ref** | P1-6 verification |

### R-04 · SECRET_KEY rotation breaks MFA secrets

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Open (process risk) |
| **Area** | Security / DR |
| **Description** | TOTP secrets Fernet-encrypted with key material from `DJANGO_SECRET_KEY`. |
| **Impact** | Privileged users cannot MFA-verify after naive key rotation |
| **Mitigation** | Document in runbook; re-enroll MFA or ship re-encrypt migration before rotate; dual-key window Recommended |
| **Effort** | M |
| **Owner** | Eng / Ops |

### R-05 · Remittance dual operational paths

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Mitigated (hard-gate) / Open (full SoR) |
| **Area** | Financial integrity |
| **Description** | MonthlyCutoff bank remit vs SettlementBatch coexist; cross-path hard-gate VERIFIED; full UI/SoR consolidation Planned (P1-1). |
| **Impact** | Ops confusion; residual double-pay risk if gate bypassed or misunderstood |
| **Mitigation** | Keep hard-gate; train ops; execute P1-1 consolidation |
| **Effort** | L |
| **Owner** | Finance + Eng |
| **Ref** | P0-4, P1-1 |

### R-06 · Coverage gate and missing security CI

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Open |
| **Area** | CI/CD |
| **Description** | Coverage `fail-under=50`; no lint, `pip-audit`, Bandit, or Dependabot in-repo. |
| **Impact** | Regressions and vulnerable deps ship unnoticed |
| **Mitigation** | Raise coverage gradually; add Dependabot + pip-audit; Ruff/Black job |
| **Effort** | M ongoing |
| **Owner** | Eng |
| **Ref** | P1-8 |

### R-07 · No Celery Beat / unscheduled backups

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Mitigated (Beat schedules + backup task Current; provider backups still operator-owned) |
| **Area** | DR / Infrastructure |
| **Description** | Previously no Beat; backups were manual only. |
| **Impact** | RPO miss if provider backups off and Beat/worker not running |
| **Mitigation** | Celery Beat schedules `backup_database_task`; enable provider backups; run workers in prod |
| **Effort** | S (ops) |
| **Owner** | Ops |

### R-08 · FinancialAuditLog not model-immutable

| Field | Detail |
|-------|--------|
| **Severity** | High |
| **Status** | Open |
| **Area** | Security / Compliance |
| **Description** | `PlatformAuditLog` blocks mutate/delete; `FinancialAuditLog` relies on admin discipline. |
| **Impact** | Break-glass admin could alter finance audit trail |
| **Mitigation** | Model save/delete guards; DB role restrictions; keep audit admins read-only |
| **Effort** | M |
| **Owner** | Eng |
| **Ref** | P1-9 |

---

## Medium

### R-09 · Absolute session timeout absent

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Open |
| **Area** | Security |
| **Description** | Idle timeout via SiteSettings; no absolute max session / logout-all devices. |
| **Mitigation** | Implement absolute age; logout-all on password change for privileged roles |
| **Effort** | M |
| **Ref** | P2-7 |

### R-10 · Giving / report aggregation performance

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Open |
| **Area** | Performance |
| **Description** | `church_giving_leaders` aggregates in Python; large dashboards/reports may N+1 or load heavy sets. |
| **Mitigation** | ORM `annotate`/`Sum`; indexes (P1-7); prefetch hierarchy templates |
| **Effort** | M |
| **Ref** | P1-5, P1-7 |

### R-11 · Fat finance services maintainability

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Open |
| **Area** | Maintainability |
| **Description** | Large `transactions`/`payroll`/`remittance` services; residual ORM in `transactions.services`. |
| **Impact** | Higher regression risk on changes |
| **Mitigation** | Finish repository migration; split modules without behavior change |
| **Effort** | L |
| **Ref** | P1-2, P1-6 |

### R-12 · Soft-delete not implemented

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Accepted (short term) |
| **Area** | Database / Compliance |
| **Description** | AGENTS soft-delete Planned; guarded hard deletes VERIFIED for several paths. |
| **Mitigation** | Keep guards + audit; design soft-delete as Phase 2 epic |
| **Effort** | L |
| **Ref** | P0-10, P2-5 |

### R-13 · Unused budget approve/lock permissions

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Open |
| **Area** | Authorization |
| **Description** | Registry codes without Budget status machine. |
| **Mitigation** | Implement workflow or remove codes from registry/docs |
| **Effort** | M |
| **Ref** | P1-4 |

### R-14 · Duplicate permission import paths

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Open |
| **Area** | Authorization |
| **Description** | `accounts.permissions` shims vs `permissions.checks`. |
| **Mitigation** | Canonicalize imports (P1-3) |
| **Effort** | M |

### R-15 · Celery optional on Render blueprint

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Accepted if async off |
| **Area** | Infrastructure |
| **Description** | `render.yaml` is web+DB only; async email/exports need worker. |
| **Mitigation** | Keep sync email default; add worker when enabling async features |
| **Effort** | M |

### R-16 · Unauthenticated health detail leakage

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Status** | Accepted |
| **Area** | Security |
| **Description** | `/health/` public; may reveal migration/cache failure strings. |
| **Mitigation** | Restrict to internal network if threat model requires; keep LB-compatible |
| **Effort** | S |

---

## Low

### R-17 · UI / naming inconsistency

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Status** | Open |
| **Area** | UX / Docs |
| **Description** | Spec folders ≠ apps (EVENTS→meetings, etc.). |
| **Mitigation** | Docs mapping only; do not rename apps |
| **Ref** | P2-1, P2-2 |

### R-18 · Announcement dual status fields

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Status** | Open |
| **Area** | Data model |
| **Ref** | P2-6 |

### R-19 · No first-class metrics / APM

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Status** | Open |
| **Area** | Observability |
| **Mitigation** | Sentry performance + platform metrics first |

### R-20 · Template `|safe` for chart JSON / actions

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Status** | Accepted |
| **Area** | XSS |
| **Description** | Trusted server-built fragments; ensure never user-controlled HTML. |
| **Mitigation** | Code review; prefer `json_script` for JS data |

### R-21 · Free-tier Render cold starts

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Status** | Accepted for trials |
| **Area** | Infrastructure |
| **Mitigation** | Starter+ plan for production always-on |

---

## Mitigated / Closed references (Phase 1 P0)

Keep monitoring; do not reopen without evidence.

| ID | Topic | Status |
|----|-------|--------|
| P0-1 | Transactions POST permission gates | Mitigated |
| P0-2 | Assets `view_assets` RBAC | Mitigated |
| P0-3 | Remittance district+ false POSTED | Mitigated |
| P0-4 | Remittance cross-path hard-gate | Mitigated (partial SoR) |
| P0-5 | MFA privileged enforcement | Mitigated |
| P0-6 | Login/portal/reset rate limits | Mitigated |
| P0-7 | DEBUG production defaults | Mitigated |
| P0-8 | Admin tenancy scoping | Mitigated |
| P0-9 | Export access audit | Mitigated |
| P0-10 | Guarded deletes | Mitigated (soft-delete still Planned) |
| P0-11 | Module journal maker-checker | Mitigated |
| P0-12 | Remittance unit scope | Mitigated |
| P0-W1 | Welfare disburse lock order | Mitigated |

---

## Risk acceptance for go-live

A **limited production** go-live may proceed when:

1. R-01 mitigated (`REDIS_URL`)  
2. R-02 mitigated if any media uploads are in scope  
3. R-07 compensated (provider backups on + restore drill scheduled)  
4. R-03 accepted only if release CI on **Python 3.13** is green  
5. R-05 hard-gate remains enabled; ops trained  
6. R-08, R-09 accepted with admin discipline + idle timeout until Phase 2  

Sign-off: Platform OWNER + Engineering lead + Finance lead (for remittance/finance scope).

---

## Review cadence

- Update this register after each production incident.  
- Re-score severity at least quarterly or before major releases.  
- Link new tickets to Risk IDs (`R-xx`) in PR descriptions.
