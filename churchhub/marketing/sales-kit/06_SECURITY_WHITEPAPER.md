# ChurchHub — Security Whitepaper

**Audience:** Security reviewers, compliance, enterprise IT  
**Classification:** Prospect evaluation (non-certified claims)  
**Companions:** `docs/SECURITY/AUTHENTICATION.md`, `AUTHORIZATION.md`, `AUDIT_COMPLIANCE.md`

| Label | Meaning |
|-------|---------|
| **Current** | Implemented in code |
| **Planned** | AGENTS.md aspirations |
| **Recommended** | Hardening backlog |

---

## 1. Security philosophy

ChurchHub treats security as an **operating model**: least privilege, tenant isolation, financial immutability patterns, and auditable administration. Convenience never disables auth, CSRF, or permission checks.

---

## 2. Identity & authentication (Current)

| Control | Detail |
|---------|--------|
| Staff login | Django sessions · `/accounts/login/` |
| Portal login | Member email + DOB first password (`YYYY-MM-DD`) then forced change |
| Password storage | Django password hashers (never plaintext) |
| CSRF | Required on browser POSTs |
| Rate limiting | Login throttling middleware; stricter portal caps |
| Password reset | Staff + portal reset flows |
| MFA | TOTP / email OTP / recovery codes — **policy-configurable**; not universally enforced by default |
| Platform vs institution | `is_platform_user` redirects to `/platform/`; separate capability model |

**Not Current:** OAuth/OIDC IdP federation, API token product auth, DRF browsable API.

---

## 3. Authorization (Current)

- Central RBAC: permission registry, role matrix, implies, overrides  
- Hierarchy-aware church scope on church-owned queries  
- Template `{% can %}` is **UI only** — server checks are mandatory  
- Platform operators use **sitecontrol capabilities**, not institution “superadmin” shortcuts  
- Django admin is **break-glass / platform-restricted**

---

## 4. Multi-tenant isolation (Current)

1. **Denomination wall** — SaaS boundary  
2. **Church scope** — operational records  
3. **Dual lanes** — institution UI vs platform UI  

Cross-tenant reports/exports and client-only filtering are **forbidden** patterns.

---

## 5. Financial security (Current)

| Control | Behavior |
|---------|----------|
| Double-entry | Transaction lines must balance |
| Posting discipline | Working day / period gates |
| Approvals | Maker-checker where configured |
| Immutability | No silent edit of approved/locked journals |
| Corrections | Void via reversing entries |
| Idempotency | On critical financial POSTs where implemented |
| PII in logs | No passwords, tokens, or decrypted payroll PII |

---

## 6. Application security (Current)

- ORM-first data access; parameterized queries if raw SQL ever required  
- Output escaping via Django templates  
- Upload validation (type, size, extension allowlists)  
- Security headers / HTTPS / secure cookies in production settings  
- Production env validation (refuse weak `SECRET_KEY`, `DEBUG`, SQLite, missing Redis/CSRF origins)  
- Structured logging; optional Sentry  

---

## 7. Audit & monitoring (Current)

Domain audit logs (finance, permissions, platform, etc.) record sensitive actions.  
Health endpoints: `/health/`, `/health/live/`, `/health/ready/`, `/metrics/`.

**Planned (AGENTS):** unified soft-delete audit model, broader retention tooling — not claimed as Current.

---

## 8. Deployment security checklist (Current expectations)

- [ ] `DJANGO_DEBUG=False`  
- [ ] Unique `DJANGO_SECRET_KEY`  
- [ ] HTTPS terminated; `CSRF_TRUSTED_ORIGINS` set  
- [ ] PostgreSQL + Redis  
- [ ] Restricted admin access  
- [ ] Backups tested  
- [ ] `CHURCHHUB_PUBLIC_URL` correct for email links  

See [`07_DEPLOYMENT_GUIDE.md`](./07_DEPLOYMENT_GUIDE.md) and `docs/PRODUCTION_SECURITY_CHECKLIST.md` when present.

---

## 9. Shared responsibility

| ChurchHub / operator | Customer institution |
|----------------------|----------------------|
| Secure defaults, patches, tenancy controls | Role assignment hygiene |
| Platform audit, feature flags | Working-day / approval discipline |
| Hosting hardening (if managed) | Endpoint device & password practices |

---

## 10. Disclosure posture

This whitepaper describes **engineering controls**, not a formal certification. Do not claim SOC 2 / ISO / GDPR “certified” unless independently attested. Privacy principles (minimization, access control) are supported by product design.

**Contact for security questionnaires:** security@churchhub.example (replace before publish).
