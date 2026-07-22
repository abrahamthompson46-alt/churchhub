# ChurchHub — Production Security Checklist

**Date:** 22 July 2026  
**Use:** Gate controlled production go-live. Pair with `SECURITY_VALIDATION_REPORT.md` and `DEPLOYMENT_CHECKLIST.md`.

Mark each item **Done** before declaring production live.

---

## A. Environment & secrets

- [ ] `DJANGO_ENV=production` (loads `church_system.settings.production`)
- [ ] `DJANGO_DEBUG=False` (production module raises if DEBUG True)
- [ ] Strong unique `DJANGO_SECRET_KEY` (not the insecure default)
- [ ] `ALLOWED_HOSTS` exact production hostnames
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https://` origins
- [ ] Database URL points to managed PostgreSQL (not SQLite)
- [ ] `REDIS_URL` set on **all** web and Celery workers
- [ ] Email credentials / API keys via env only
- [ ] Optional: dedicated `MFA_ENCRYPTION_KEY` once implemented (today MFA uses SECRET_KEY-derived Fernet)

---

## B. Transport & cookies

- [ ] TLS terminated at reverse proxy / platform
- [ ] `SECURE_SSL_REDIRECT=True` (or platform-equivalent HTTPS-only)
- [ ] `SECURE_PROXY_SSL_HEADER` honored (`X-Forwarded-Proto`)
- [ ] Session cookie Secure + HttpOnly (Django defaults + production Secure)
- [ ] CSRF cookie Secure
- [ ] HSTS enabled (1y includeSubDomains; preload only if intentional)
- [ ] `X_FRAME_OPTIONS=DENY` confirmed at app layer

---

## C. Authentication & MFA

- [ ] SiteSettings MFA policy set intentionally (off until ready, or on with selected roles)
- [ ] If MFA on: selected platform/institution roles enrolled before go-live
- [ ] Login lockout thresholds reviewed (`login_max_attempts`, `login_lockout_minutes`)
- [ ] Password reset email delivery verified (no open redirect in reset links)
- [ ] Impersonation only used by authorized platform operators; exit path tested
- [ ] Session idle timeout acceptable for finance users

---

## D. Authorization smoke tests

- [ ] Church A user cannot open Church B member / transaction / asset URLs (expect 403/404)
- [ ] Cross-denomination member URL blocked
- [ ] Non-approver cannot approve pending journals
- [ ] Maker cannot approve own transaction
- [ ] Platform admin cannot escalate institution roles outside managed scope
- [ ] `/metrics/` returns 401 unauthenticated; 403 for non-privileged authenticated users
- [ ] Report/member/finance exports denied without export (or equivalent) permission where required

---

## E. Financial controls smoke tests

- [ ] Posting blocked when financial period locked
- [ ] Posting blocked when working day not open
- [ ] Approved journal cannot be silently edited
- [ ] Void/reversal leaves audit trail
- [ ] `FinancialAuditLog` cannot be updated/deleted via ORM (immutability)

---

## F. Data protection & backups

- [ ] Media stored on durable volume or object storage (not ephemeral container disk alone)
- [ ] DB automated backup schedule active (Celery Beat or platform backup)
- [ ] One restore drill completed and documented (date + operator)
- [ ] Export downloads restricted to requesting user (job ownership)
- [ ] PII export events reviewed in audit logs after smoke export

---

## G. Dependencies & deploy artifact

- [ ] Deploy uses current `requirements.txt` (`pillow==12.3.0` or newer)
- [ ] CI `pip-audit` (or equivalent) green on release commit
- [ ] Migrations applied including `transactions.0019_financial_audit_immutability`
- [ ] Static files collected; WhiteNoise / CDN verified
- [ ] Celery worker + Beat running if async exports/backups enabled

---

## H. Observability

- [ ] `/live/` and `/ready/` monitored by platform health checks
- [ ] Application error alerting configured (Sentry or host logs)
- [ ] Log retention / rotation acceptable for incident review
- [ ] On-call knows `OPERATIONS_RUNBOOK.md` location

---

## I. Go-live sign-off

| Role | Name | Date | Signature / ack |
|------|------|------|-----------------|
| Engineering | | | |
| Ops / Hosting | | | |
| Finance control owner (optional) | | | |

**Go-live decision:** ☐ Go · ☐ Conditional Go · ☐ No-Go  

**Conditions / waivers (if any):**  
_______________________________________________

---

## Quick reference — Phase 5 security fixes already in code

Do not regress these:

1. `safe_internal_redirect` on remittance / denomination `next` parameters  
2. Impersonation session keys set after `login()`; MFA skipped while impersonating  
3. `permissions.views.user_effective` scoped by `user_may_manage_target`  
4. Authenticated privileged `/metrics/`  
5. Immutable `FinancialAuditLog`  
6. `pillow==12.3.0` in requirements  
