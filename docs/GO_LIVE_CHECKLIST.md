# ChurchHub — Go-Live Checklist (Pilot)

**Date:** 22 July 2026  
**Use:** Cutover gate for **pilot** production.  
**Companions:** `PILOT_DEPLOYMENT_PLAN.md`, `UAT_PLAN.md`, `UAT_TEST_CASES.md`, `DEPLOYMENT_CHECKLIST.md`, `PRODUCTION_SECURITY_CHECKLIST.md`

Mark each item **Done** before declaring pilot live. Do not commit secrets.

---

## 0. Decision

| Field | Value |
|-------|-------|
| Release candidate SHA | |
| Pilot wave | Wave 1 |
| Go-live date/time (UTC) | |
| Decision | ☐ Go · ☐ Conditional Go · ☐ No-Go |
| Conditions / waivers | |

---

## 1. UAT gate

- [ ] All **P0** cases in `UAT_TEST_CASES.md` executed on staging
- [ ] Zero open **Blocker** / **Critical** defects
- [ ] Major defects listed with owner + workaround (or fixed)
- [ ] Multi-tenant P0 (UAT-TEN-*) Pass
- [ ] Financial integrity P0 (UAT-ACC-*) Pass
- [ ] UAT sign-off sheet completed

---

## 2. Security gate

- [ ] `PRODUCTION_SECURITY_CHECKLIST.md` completed for this environment
- [ ] `mfa_required_for_privileged=True`
- [ ] Platform OWNER/SECURITY and all Wave 1 TREASURY users MFA-enrolled
- [ ] `/metrics/` not publicly reachable (401 anonymous)
- [ ] Impersonation policy briefed to support staff

---

## 3. Infrastructure gate

- [ ] `DEPLOYMENT_CHECKLIST.md` sections A–C complete
- [ ] `DJANGO_ENV=production`, `DEBUG=False`, strong `SECRET_KEY`
- [ ] Postgres + **Redis** + Celery worker + Beat
- [ ] Media strategy durable (disk or S3)
- [ ] TLS + HSTS + secure cookies verified
- [ ] Provider automated DB backups **and** app `backup_database` path verified
- [ ] Restore drill documented (date: ________)

---

## 4. Configuration gate

- [ ] `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / public URL correct
- [ ] SMTP tested (invite + password reset)
- [ ] Site branding/denomination labels acceptable to pilot churches
- [ ] Login lockout thresholds reviewed
- [ ] Session idle timeout acceptable to finance users
- [ ] `CHURCHHUB_BOOTSTRAP=0` after first bootstrap
- [ ] Permissions seeded (`seed_permissions`)

---

## 5. Data & access gate

- [ ] Wave 1 hierarchy created (denomination → … → churches)
- [ ] Users invited with correct roles and home churches
- [ ] Test/demo users removed or disabled
- [ ] Open working day procedure agreed
- [ ] Month-end period lock owners named (maker + unlocker)
- [ ] Chart of accounts / defaults verified per church

---

## 6. Module enablement (Wave 1)

Enable only what UAT accepted and churches will use:

| Module | Enabled? | Notes |
|--------|----------|-------|
| Membership | ☐ | |
| Transfers | ☐ | |
| Baptism/profession | ☐ | |
| Finance + ledger | ☐ | Required for finance pilot |
| Remittance | ☐ | Optional |
| Payroll | ☐ | Optional |
| Assets | ☐ | Optional |
| Budgets | ☐ | Optional |
| Giving | ☐ | Optional |
| Meetings | ☐ | |
| Announcements | ☐ | |
| Reports | ☐ | Limit exporters |
| Permissions admin | ☐ | Church Admin only |
| Site Control | ☐ | Platform only |

---

## 7. Cutover steps (run in order)

1. [ ] Announce maintenance window (if any)
2. [ ] Final staging backup / confirm RC SHA
3. [ ] Deploy production (migrate, collectstatic, restart web/worker/beat)
4. [ ] Smoke: `/health/live/`, `/health/ready/`, login, platform home
5. [ ] Smoke: one receipt → approve by second user → audit visible
6. [ ] Smoke: member create + cross-church URL denied
7. [ ] Send invites / confirm MFA enroll complete
8. [ ] Open pilot channel; declare **Pilot Live**
9. [ ] Disable bootstrap flags; remove temporary break-glass if any

---

## 8. First 48 hours

- [ ] Daily health check (ready + error logs + Sentry)
- [ ] Confirm overnight backup artifact exists
- [ ] Collect user blockers; triage Critical same day
- [ ] No SECRET_KEY rotation
- [ ] No schema-destructive migrations

---

## 9. Sign-off

| Role | Name | Date | Ack |
|------|------|------|-----|
| Engineering | | | ☐ |
| Operations | | | ☐ |
| Finance champion | | | ☐ |
| Denomination / church sponsor | | | ☐ |

**Pilot is live when sections 1–7 are complete and Decision = Go or Conditional Go with listed waivers.**
