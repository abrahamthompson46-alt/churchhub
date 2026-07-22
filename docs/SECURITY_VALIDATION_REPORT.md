# ChurchHub — Security Validation Report (Phase 5)

**Type:** Enterprise security validation (code as source of truth)  
**Date:** 22 July 2026  
**Scope:** Authentication, authorization, financial controls, data protection, infrastructure, dependencies  
**Constraint:** No new business features; verified security defects fixed only  
**Companions:** `COMPLIANCE_CHECKLIST.md`, `PRODUCTION_SECURITY_CHECKLIST.md`

---

## Executive verdict

| Metric | Result |
|--------|--------|
| **Overall security score** | **8.2 / 10** |
| **Critical vulnerabilities** | **None** (with production settings + Redis) |
| **Go / No-Go** | **Conditional Go** — controlled production after ops checklist |

ChurchHub has strong multi-tenant RBAC, MFA for privileged roles, maker-checker finance controls, production HTTPS/cookie hardening, and isolation test coverage. Phase 5 closed open redirects, an impersonation/MFA binding gap, a permissions IDOR, FinancialAuditLog mutability, unauthenticated `/metrics/`, and Pillow CVEs in `requirements.txt`.

---

## Scorecard by area

| Area | Score (/10) | Notes |
|------|-------------|-------|
| Authentication | 8.5 | Sessions, lockout, MFA enroll/verify; MFA verify not separately rate-limited |
| Authorization | 8.5 | RBAC + church/denomination scope; export permission granularity uneven |
| Financial controls | 8.5 | Maker-checker, periods, working days, audit immutability (post-fix) |
| Data protection | 7.5 | PII in DB; export gates incomplete on some report paths |
| Infrastructure | 8.5 | Split settings, HSTS, secure cookies, Redis required in prod |
| Dependencies | 8.0 | Pillow pinned to 12.3.0 after pip-audit; keep CI audit green |

**Overall: 8.2 / 10**

---

## 1. Authentication

### Verified strengths

| Control | Evidence |
|---------|----------|
| Session auth | Custom `accounts.User`; cookie session |
| Idle timeout | `PlatformSessionMiddleware` + `SiteSettings` |
| Login lockout | `LoginRateLimitMiddleware` (cache-backed; needs Redis multi-worker) |
| Password reset throttle | Same middleware (`/accounts/password_reset`) |
| MFA (TOTP + recovery) | `accounts.mfa`, `MfaEnforcementMiddleware` when `mfa_required_for_privileged` |
| Invitation accept | Exempt from MFA enroll; password set on accept |

### Phase 5 fixes

| Issue | Fix |
|-------|-----|
| Impersonation set operator id **before** `login()` (session flush) | Set `platform_impersonator_id` / `impersonation_active` **after** `login()` |
| Impersonation could force MFA enroll on target | Middleware skips MFA when impersonation session keys present |

### Remaining gaps (not Critical)

| Severity | Issue |
|----------|-------|
| Medium | MFA Fernet key derived from `SECRET_KEY` — rotate `SECRET_KEY` rotates MFA ciphertext; prefer dedicated `MFA_ENCRYPTION_KEY` |
| Medium | MFA verify endpoint not separately rate-limited (login lockout does not cover TOTP brute force as tightly) |
| Medium | Privileged MFA scope may omit some finance approvers depending on role matrix |
| Low | Absolute session timeout / logout-all-devices still Planned |
| Low | Password-reset throttle may count successful posts depending on middleware path |

---

## 2. Authorization

### Verified strengths

- Permission checks via `permissions.checks` / services  
- Church active context + object scoping in members, transactions, assets, payroll  
- Denomination isolation helpers and tests  
- Platform vs institution lanes in sitecontrol / admin tenancy  

### Phase 5 fixes

| Issue | Fix |
|-------|-----|
| Open redirect via unsanitized `next` | `safe_internal_redirect` in remittance welfare + denomination context set/clear |
| `user_effective` `is_superuser` bypass of `user_may_manage_target` | Scope via `user_may_manage_target` only |
| Unauthenticated `/metrics/` | Requires authenticated platform/staff/superuser |

### Remaining gaps

| Severity | Issue |
|----------|-------|
| Medium | Report exports (`reports/views.py`) gate on report access / view, not always `can_export_reports_*` |
| Medium | Some module export paths still rely on manage-finance fallbacks rather than dedicated `can_export_*` |
| Low | Docs drift: older Phase 0 notes may still call MFA a “stub” (code enforces MFA) |

---

## 3. Financial controls

### Verified strengths

| Control | Status |
|---------|--------|
| Maker-checker | Maker cannot approve own transaction (`transactions.tests_auto_approve`) |
| Approval workflow | PENDING → APPROVED; module journals respect checker rules |
| Period locking | Financial periods block posting when locked |
| Working-day controls | Open working day required for posting paths |
| Journal immutability | Approved journals locked against re-approve / mutation paths |
| Audit logging | `FinancialAuditLog` write-on-event |

### Phase 5 fixes

| Issue | Fix |
|-------|-----|
| FinancialAuditLog updatable / CASCADE wipe | Immutable `save()`/`delete()`; FK to transaction `SET_NULL`; migration `0019_financial_audit_immutability` |

### Remaining gaps

| Severity | Issue |
|----------|-------|
| Medium | Some void/reversal paths may auto-approve reversal journals — review ops policy |
| Low | Soft-delete / retention policy for PII-linked finance rows still Planned |

---

## 4. Data protection

| Topic | Assessment |
|-------|------------|
| PII | Members, employees, users store names, contacts, identifiers in PostgreSQL |
| Sensitive fields | MFA secrets Fernet-encrypted at rest; passwords hashed |
| Export permissions | Present in registry; enforcement incomplete on some report export formats |
| Backup / restore | `backup_database` + Beat schedule + ops scripts; restore drill operator-owned |
| Media | Production must not rely on DEBUG media serving |

---

## 5. Infrastructure security

| Control | Production (`church_system/settings/production.py`) |
|---------|-----------------------------------------------------|
| DEBUG | Must be False (ImproperlyConfigured otherwise) |
| SECRET_KEY | Rejects insecure default |
| HTTPS | `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER` |
| Cookies | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` |
| HSTS | 1 year + includeSubDomains (+ optional preload) |
| Clickjacking | `X_FRAME_OPTIONS = DENY` |
| Redis | Required via `validate_production_environment` |
| Logging | File logs on by default; Sentry optional |

**Ops risk (deployment, not code defect):** LocMemCache if Redis missing with multiple Gunicorn workers → inconsistent rate limits / caches. Production settings now refuse missing Redis.

---

## 6. Dependency review

**Tool:** `pip-audit -r requirements.txt` (22 July 2026)

| Package | Finding | Action |
|---------|---------|--------|
| `pillow==12.1.0` | Multiple PYSEC/CVE advisories (fix ≥ 12.1.1 / 12.2.0 / **12.3.0**) | **Pinned to `pillow==12.3.0` in `requirements.txt`** |

No other packages reported in that audit run. Re-run `pip-audit` in CI on every dependency change. Local environments may lag `requirements.txt` (e.g. Django install vs pin) — deploy from lock/requirements, not ad-hoc venv drift.

---

## 7. Testing executed / reviewed

| Suite | Focus | Result (post Phase 5) |
|-------|-------|------------------------|
| `church_system.tests_infra` + tenant + denomination isolation | Metrics auth + tenancy | **17/17 OK** |
| Prior Phase 5 full slice (67 tests) | layers + dashboard | Failures were MFA 302s (fixed harness); infra/isolation green |
| Related finance tests | Maker-checker / auto-approve | Reviewed (`transactions.tests_auto_approve`) |

**Note:** Isolation harness disables privileged MFA and applies the Py3.14 template-context patch so assertions measure tenancy (403/404), not MFA redirects or Django test-client crashes.

---

## 8. Issue register (post Phase 5)

### Critical

*None identified for correctly configured production.*

### High (addressed in Phase 5)

| ID | Issue | Status |
|----|-------|--------|
| H1 | Open redirects (`next`) | **Fixed** |
| H2 | Impersonation session / MFA enroll on target | **Fixed** |
| H3 | `user_effective` superuser IDOR | **Fixed** |
| H4 | Unauthenticated metrics | **Fixed** |
| H5 | Pillow known CVEs (12.1.0) | **Fixed** (pin 12.3.0) |

### Medium (accepted / deferred)

| ID | Issue | Recommendation |
|----|-------|----------------|
| M1 | MFA crypto tied to `SECRET_KEY` | Dedicated env key |
| M2 | MFA verify rate limit | Per-IP/user throttle on TOTP |
| M3 | Report export vs `can_export_reports_*` | Enforce format-specific export perms |
| M4 | Void/reversal auto-approve edge cases | Policy + code review |
| M5 | MFA role coverage gaps | Align with finance approver roles |
| M6 | Password-reset success counting | Count failures only |

### Low

| ID | Issue |
|----|-------|
| L1 | Absolute session timeout / device list |
| L2 | Password history / expiration |
| L3 | Documentation drift on MFA maturity |
| L4 | Soft-delete / retention automation |

---

## 9. Compliance readiness (summary)

See `COMPLIANCE_CHECKLIST.md`.

| Domain | Readiness |
|--------|-----------|
| Access control / least privilege | **Ready with gaps** (export granularity) |
| Financial SoD / audit | **Ready** (post audit immutability) |
| Encryption in transit | **Ready** (prod HTTPS/HSTS) |
| Encryption at rest (app-level) | **Partial** (MFA secrets; DB disk encryption is ops) |
| Privacy / PII exports | **Partial** |
| Ops / DR evidence | **Partial** (backup code Current; drill evidence ops) |

---

## 10. Go / No-Go

**Recommendation: Conditional Go for controlled production.**

**Must-have before / at go-live (ops):**

1. `DJANGO_ENV=production`, `DEBUG=False`, strong `DJANGO_SECRET_KEY`  
2. `REDIS_URL` on all web/worker instances  
3. Deploy with `pillow>=12.3.0`  
4. TLS terminator + verified HSTS/cookies  
5. Backup schedule + one restore drill recorded  

**Should-have soon after go-live:** M1–M3 (MFA key, MFA verify throttle, export permission consistency).

**Do not treat as No-Go:** Remaining Medium/Low items above, provided ops checklist is completed and privileged MFA remains enabled in production SiteSettings.
