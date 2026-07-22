# ChurchHub — Compliance Checklist

**Date:** 22 July 2026  
**Companion:** `SECURITY_VALIDATION_REPORT.md`, `PRODUCTION_SECURITY_CHECKLIST.md`  
**Purpose:** Map enterprise control expectations to current ChurchHub posture. Not a formal certification.

Legend: **Met** · **Partial** · **Gap** · **Ops** (operator/process, not only code)

---

## 1. Identity & access management

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Unique user accounts | **Met** | `accounts.User` |
| Strong password policy | **Met** | Django validators + platform length/complexity |
| MFA for privileged roles | **Met** | TOTP + recovery; SiteSettings flag (default on) |
| Session timeout | **Partial** | Idle timeout Current; absolute timeout Planned |
| Account lockout / rate limit | **Met** | Login + password reset middleware (Redis in prod) |
| Invitation / onboarding path | **Met** | Invite accept flow |
| Privilege separation (platform vs institution) | **Met** | Roles + sitecontrol + admin tenancy |
| Impersonation controls | **Met** | Post-login session keys; MFA skipped on target; audit separately |

---

## 2. Authorization & tenancy

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Role-based permissions | **Met** | `permissions` registry / checks |
| Object-level church scope | **Met** | Isolation tests + view scoping |
| Denomination isolation | **Met** | Scope helpers + tests |
| No naked superuser IDOR on user mgmt screens | **Met** | `user_effective` scoped (Phase 5) |
| Export least privilege | **Partial** | Registry exists; report exports not always format-gated |

---

## 3. Financial integrity (SoD / audit)

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Maker-checker | **Met** | Maker cannot approve own txn |
| Approval workflow | **Met** | PENDING / APPROVED paths |
| Period lock | **Met** | Financial periods |
| Working-day control | **Met** | Open day required |
| Journal immutability after approval | **Met** | Locked approved journals |
| Financial audit trail immutability | **Met** | Phase 5 model guards + SET_NULL |
| Void / reversal dual control | **Partial** | Review auto-approve reversal edge cases |

---

## 4. Data protection & privacy

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| PII inventory awareness | **Partial** | Members/payroll/users; formal RoPA not in repo |
| Password hashing | **Met** | Django PBKDF2/argon2 stack |
| MFA secret protection | **Partial** | Fernet at rest; key derived from SECRET_KEY |
| HTTPS in production | **Met** | Production settings |
| Secure cookies | **Met** | Secure session/CSRF cookies |
| Right to erasure / retention | **Gap / Ops** | Soft-delete Planned; process ops-owned |
| Export audit | **Partial** | Report access audit + platform export caps |

---

## 5. Logging, monitoring & incident

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Application logs | **Met** | Structured + rotating files in prod |
| Security-relevant audit tables | **Met** | Platform + financial + report access |
| Health / readiness | **Met** | `/health/`, `/live/`, `/ready/` |
| Metrics authorization | **Met** | Authenticated privileged only (Phase 5) |
| Error tracking | **Partial** | Sentry optional |
| Incident runbook | **Ops** | See `OPERATIONS_RUNBOOK.md` |

---

## 6. Change & dependency management

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Dependency vulnerability scan | **Partial** | pip-audit; Pillow upgraded Phase 5 |
| CI quality gates | **Partial** | Present; keep audit in CI |
| Secrets not in repo | **Met** | Env-based; insecure default blocked in prod |
| Migration discipline | **Met** | Django migrations for security model changes |

---

## 7. Backup & continuity

| Control | Status | Evidence / notes |
|---------|--------|------------------|
| Automated DB backup | **Met / Ops** | Command + Beat; verify schedule live |
| Restore procedure documented | **Partial** | Scripts/docs; drill evidence Ops |
| Media durability | **Ops** | Disk/object storage + proxy |

---

## 8. Overall compliance readiness

| Domain | Verdict |
|--------|---------|
| Access & MFA | **Ready for controlled production** |
| Multi-tenant isolation | **Ready** |
| Financial SoD / audit | **Ready** (monitor void/reversal policy) |
| Privacy / export governance | **Near-ready** — close export permission gaps |
| Ops evidence (DR, monitoring) | **Operator-dependent** |

**Compliance readiness summary:** Suitable for controlled production under documented ops controls. Not a claim of GDPR/SOC2/ISO certification without independent assessment and evidence packs.
