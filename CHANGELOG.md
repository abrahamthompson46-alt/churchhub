# Changelog

All notable changes to ChurchHub are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning per [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- Owner-only Marketing Hub in Platform Control with campaign attribution, lead workflow, conversion summaries, approved collateral links, and copy-ready website CTAs.
- CSRF-protected public `/contact/` inquiry form with explicit consent, honeypot protection, proxy-aware throttling, denomination validation, branded sales notifications, and privacy-safe platform audit events.
- Audited lead export, closed-lead anonymization, retention controls, durable notification status, and retryable Celery delivery.

### Security

- Dedicated `manage_marketing` platform capability is restricted to Platform Owners.
- Marketing collateral accepts HTTPS links only; lead PII is excluded from audit details and application logs.
- Public inquiry activation now requires an HTTPS privacy policy and consent configuration; throttling combines validated IP, hashed email, campaign and global limits.
- Forwarded client IPs are accepted only from explicitly trusted proxy addresses.

### Fixed

- Institution hierarchy-admin invitations no longer fail email rendering when no home church is assigned.
- Submitting an already-pending invitation now refreshes and resends it instead of silently leaving the recipient without another delivery attempt.
- Churchless pending-invitation lookup is denomination-scoped.

---

## [1.0.0] — 2026-07-22

### Added — General Availability

First production release of ChurchHub Enterprise ChMS.

- Multi-tenant hierarchy: conference → zone → district → church  
- Denomination isolation and platform site control (`/platform/`)  
- Session authentication with invitations, password reset, and login rate limiting  
- TOTP MFA + recovery codes for privileged roles  
- RBAC permission registry, overrides, and scoped effective-permission views  
- Members: directory, transfers, departments, baptism register  
- Finance: double-entry transactions, maker-checker, periods, working days, audit log  
- Ledger UI, budgets, giving statements, remittance, welfare, payroll, assets  
- Meetings, minutes workflow, announcements with approval  
- Reports catalog with CSV/Excel/PDF and async export jobs  
- Member portal, dashboard, notifications  
- Health endpoints (`/health/live/`, `/health/ready/`, `/health/`)  
- Celery + Beat scheduled backups and maintenance tasks  
- Production settings split, Redis cache, WhiteNoise static, optional S3 media  
- Performance indexes and targeted caching (Phase 4)  

### Security (Phase 5)

- Open redirect hardening (`safe_internal_redirect`)  
- Impersonation session fix; MFA skipped while impersonating  
- `user_effective` IDOR fix  
- Immutable `FinancialAuditLog`  
- Authenticated `/metrics/`  
- `pillow==12.3.0` dependency pin  

### Fixed — RC1 consistency

- `assets.0004_rc1_consistency` — index name alignment  
- `members.0005_rc1_consistency` — audit action field alignment  
- `permissions.0002_rc1_consistency` — role field alignment  
- `remittance.0004_rc1_consistency` — audit action field alignment  

### Documentation

- Phase 5: security validation, compliance, production security checklists  
- Phase 6: UAT plan, test cases, pilot deployment, go-live checklist  
- Phase 7: RC1 release notes, known limitations, production runbook, operations manual  
- Phase 8: `VERSION.md`, `CHANGELOG.md`, `RELEASE_NOTES.md` (this release)  

### Known limitations

See `docs/KNOWN_LIMITATIONS.md`. Notable: MFA key derived from `SECRET_KEY`, export permission granularity, no soft-delete, absolute session timeout planned.

---

## [2.0.0-rc1] — 2026-07-22 (internal)

Release candidate verification track. See `docs/RELEASE_NOTES_RC1.md`.

---

## Pre-GA development phases (summary)

| Phase | Focus |
|-------|--------|
| 1–2 | Layered architecture, enterprise foundation |
| 3 | Production infrastructure |
| 4 | Performance optimization |
| 5 | Security validation |
| 6 | UAT & pilot readiness |
| 7 | RC1 verification |
| 8 | GA release (1.0.0) |

[1.0.0]: https://github.com/churchhub/churchhub/releases/tag/v1.0.0
[2.0.0-rc1]: https://github.com/churchhub/churchhub/releases/tag/v2.0.0-rc1
