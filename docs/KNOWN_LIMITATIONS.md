# ChurchHub — Known Limitations (RC1)

**Version:** `2.0.0-rc1`  
**Date:** 22 July 2026  
**Companion:** `RELEASE_NOTES_RC1.md`, `SECURITY_VALIDATION_REPORT.md`, `RISK_REGISTER.md`

This document lists **accepted** limitations at RC1. Items marked **Blocker** must be resolved before general availability; **Pilot OK** may proceed with documented mitigations.

---

## 1. Security & identity

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-SEC-01 | MFA encryption key derived from `DJANGO_SECRET_KEY` | Medium | Yes | Do not rotate SECRET_KEY during pilot; plan dedicated `MFA_ENCRYPTION_KEY` post-GA |
| KL-SEC-02 | MFA verify endpoint not separately rate-limited | Medium | Yes | Keep login lockout; monitor auth logs |
| KL-SEC-03 | Report exports not always gated by `can_export_reports_*` | Medium | Yes | Limit report access roles; review export audit |
| KL-SEC-04 | Absolute session timeout / logout-all devices not implemented | Low | Yes | Idle timeout via `SiteSettings` |
| KL-SEC-05 | Password history / expiration not implemented | Low | Yes | Policy via external IdP if required |

---

## 2. Data & privacy

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-DAT-01 | No automated soft-delete / retention for PII | Medium | Yes | Manual export + DB procedures |
| KL-DAT-02 | Formal RoPA / DPIA not in repository | Low | Yes | Ops privacy pack external |
| KL-DAT-03 | Member erasure is manual / partial | Medium | Yes | Document church-level process |

---

## 3. Finance

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-FIN-01 | Some void/reversal paths may auto-approve reversal journals | Medium | Yes | Dual-control policy; review audit log |
| KL-FIN-02 | MFA privileged set may not include all finance approver roles | Medium | Yes | Enroll approvers as TREASURY or override MFA policy in staging only |
| KL-FIN-03 | Ledger app is UI over `transactions` SoR — not a second ledger | Info | Yes | Train treasurers on single SoR |

---

## 4. Operations & infrastructure

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-OPS-01 | Media not served by Django when `DEBUG=False` | High | Yes **if** disk/S3 + proxy configured | Follow `DEPLOYMENT_CHECKLIST.md` media strategy |
| KL-OPS-02 | LocMemCache if Redis missing with multi-worker Gunicorn | Critical | **No** | `REDIS_URL` required in production settings |
| KL-OPS-03 | Restore drill evidence is operator-owned | Medium | Yes | Run drill before pilot; record in runbook |
| KL-OPS-04 | Celery/Beat optional in dev; required for backups/async at scale | Medium | Yes | Run worker + Beat in pilot prod |
| KL-OPS-05 | No built-in blue/green or canary deploy | Low | Yes | Render/manual rollback |

---

## 5. Testing & quality

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-QA-01 | No in-repo load/performance test harness | Medium | Yes | Phase 4 static review; monitor pilot |
| KL-QA-02 | Python 3.14 local dev may hit Django test-client template copy bug | Low | Yes | CI uses Python 3.13; use `SiteControlClientHarness` in isolation tests |
| KL-QA-03 | RC1 focused suite: 1/80 health test flaky on long runs | Low | Yes | Re-run after migrate; CI full suite |
| KL-QA-04 | Local venv may run Django 5.x while `requirements.txt` pins `Django>=6.0.6` | Medium | Yes | Deploy from CI lock / fresh venv on 3.13+ |

---

## 6. Documentation

| ID | Limitation | Severity | Pilot OK? | Mitigation |
|----|------------|----------|-----------|------------|
| KL-DOC-01 | Phase 0 module specs still say “MFA stub” in places | Low | Yes | Use `docs/SECURITY/AUTHENTICATION.md` |
| KL-DOC-02 | `OPERATIONS_RUNBOOK.md` predates authenticated `/metrics/` | Low | Yes | Use `PRODUCTION_RUNBOOK.md` |
| KL-DOC-03 | `PRODUCTION_READINESS_REPORT.md` some Beat/audit items stale vs code | Low | Yes | This file + Security report |

---

## 7. Product scope (not bugs)

| Item | Notes |
|------|-------|
| No public REST API | Server-rendered Django only |
| No mobile native apps | Responsive web |
| No built-in payment gateway | Manual / external giving reconciliation |
| No multi-language UI | English primary |
| Events module | Spec exists; meetings cover core path |

---

## 8. RC1 migration note

RC1 adds **consistency-only** migrations (index renames, audit `action` field alignment). They do not change business rules. **All environments must run `migrate` before serving traffic** or `/health/ready/` will return 503 (pending migrations check).

---

## Severity legend

| Level | Meaning |
|-------|---------|
| Critical | Must fix or mitigate before any production traffic |
| High | Must fix for pilot unless explicit waiver + compensating control |
| Medium | Track; waiver acceptable for pilot |
| Low | Post-GA backlog |
| Info | By design |
