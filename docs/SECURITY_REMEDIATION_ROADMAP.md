# ChurchHub Security Remediation Roadmap

**Audit date:** 14 August 2026  
**Commit reviewed:** `8eb5730f91b18212e17f48b3550afa952492437b` (`main`)  
**Companion reports:** `docs/SECURITY_AUDIT_REPORT.md`, `docs/SECURITY_FINDINGS_REGISTER.md`  

This document is a plan only. No application code was changed during the audit.

Priority bands:

- **P0 — Immediate:** stop active data leakage or account takeover paths.
- **P1 — High priority:** close remaining HIGH integrity and isolation defects.
- **P2 — Medium priority:** races, SoD, enumeration, incomplete audit.
- **P3 — Hardening:** CSRF logout, pin drift, HSTS, compose ports.

---

## P0 — Immediate

Do these first. They are the reason the verdict is **READY WITH CRITICAL REMEDIATIONS** rather than production-hardened.

### P0-1 — Object-scope private media (CH-SEC-001)

**Goal:** A logged-in user of Church A cannot read Church B’s files.

**Work:**

1. Map each `/media/...` prefix to the owning model (`Member`, `Meeting`, `WelfareCase`, `Announcement`, report export job, etc.).
2. Authorize against `get_manageable_churches(user)` / portal member ownership / export job owner.
3. Return 404 (not 403) for out-of-scope paths to reduce enumeration.
4. Do not serve `exports/reports/` except to the job owner (or an equivalent scoped finance role).
5. Prefer UUID storage names so original filenames are not guessable.
6. Rewrite `church_system/tests_media_access.py` so the current “any authenticated user may fetch any private path” assertion becomes a **deny** test.

**Acceptance test:** User in denomination A receives 404 for denomination B member photo, welfare file, meeting attachment, and another user’s export file.

**Owner:** media / members / reports  
**Effort:** 1–3 days  

---

### P0-2 — Throttle MFA verification (CH-SEC-003)

**Goal:** A stolen password cannot be completed by brute-forcing a 6-digit OTP.

**Work:**

1. Extend `LoginRateLimitMiddleware` (or a dedicated limiter) to `/accounts/mfa/verify/` and email-OTP resend.
2. Lock by user id + IP after N failures (align with login lockout defaults).
3. Keep constant-time OTP compare.

**Acceptance test:** N+1 invalid MFA POSTs return 429/lockout; a valid code during the lockout window is rejected.

**Owner:** accounts  
**Effort:** half day  

---

## P1 — High priority

### P1-1 — Denomination-own general announcements (CH-SEC-002, CH-SEC-008)

**Work:**

1. Add a denomination FK (or forbid `church=None` rows).
2. Filter `announcements_for_church_ids` / `visible_announcements` by `get_user_denomination`.
3. Load `announcement_detail` from a scoped queryset; never grant `can_see` from a global capability flag alone.

**Acceptance tests:**

- General announcement created in denom A is invisible in denom B.
- Approver in church A cannot GET pending announcement detail in church B.

---

### P1-2 — Tenant district moves must run model validation (CH-SEC-004)

**Work:**

1. Call `full_clean()` in `repo.save_church` / tenant edit persist.
2. Constrain `TenantChurchForm.district` queryset to denominations the operator can manage.
3. Re-check destination district denomination after POST.

**Acceptance test:** POST `tenant_edit` with another denomination’s `district_id` is rejected; `Church.district` unchanged.

---

### P1-3 — Asset journals must post like core money (CH-SEC-005)

**Work:**

1. After creating CAPITAL journals, approve and lock using the same path as other module journals.
2. Call `assert_working_day_allows_posting`.
3. Add SoD on dispose (creator ≠ approver, or require `can_manage_finances`).

**Acceptance test:** Depreciation on a closed working day raises; on success the related `Transaction` is APPROVED and locked.

---

### P1-4 — Contribution posting idempotency (CH-SEC-006)

**Work:**

1. Claim `FinancialIdempotencyKey` in `record_member_contribution` and the import path.
2. Optionally unique-constrain (campaign, member, date, amount, client nonce).

**Acceptance test:** Two identical POSTs yield one `MemberContribution` and one receipt.

---

### P1-5 — Separate view vs mutate on remittance and bank-rec (CH-SEC-007)

**Work:**

1. Stop using `_finance_required` (OR of view/receipts/expenses) on mutating remittance and reconciliation views.
2. Require `can_manage_finances` (or a dedicated remittance permission) for remittance POST.
3. Require `can_manage_reconciliation` for create/match; keep `can_finalize_reconciliation` on finalize.

**Acceptance test:** User with only `view_transactions` receives 403 on remittance POST and recon create.

---

## P2 — Medium priority

| ID | Finding | Action | Acceptance |
|----|---------|--------|------------|
| P2-1 | CH-SEC-009 | Filter `platform_stats()` and over-limit alerts with `filter_churches_for_operator` | Operator limited to denom A never sees denom B names or counts |
| P2-2 | CH-SEC-010 | Generic portal login error; log reason server-side | Unknown vs known email produce identical public text |
| P2-3 | CH-SEC-011 | Reject welfare approve when `created_by_id == user.id` | Creator approve raises |
| P2-4 | CH-SEC-012 | `select_for_update` on original txn; unique on `reversal_of` | Concurrent voids → one reversal |
| P2-5 | CH-SEC-013 | Lock incomplete idempotency keys; reject in-flight reuse | Parallel receipt POSTs with same key create one txn |
| P2-6 | CH-SEC-014 | Disable delete on `UserActivityLog` admin; raise on model `delete()` | Admin delete denied |
| P2-7 | CH-SEC-015 | Replace DOB-as-password with invite/OTP; keep device confirm | After set-password, DOB login fails |
| P2-8 | CH-SEC-016 | Call `audit_export` on asset/contribution CSV | Export appears in activity/audit log |
| P2-9 | CH-SEC-L1 | Require church or denomination on SUPER_ADMIN at save (not only `clean()`) | Unanchored superadmin cannot be persisted |
| P2-10 | CH-SEC-L2 | Magic-byte / content sniff on uploads | `.jpg` that is HTML/SVG is rejected |
| P2-11 | CH-SEC-L3 | Row lock or unique constraint on settlement / district remittance | Concurrent posts create one journal |

---

## P3 — Hardening

| ID | Finding | Action |
|----|---------|--------|
| P3-1 | CH-SEC-017 | Logout via POST + CSRF; change portal navbar |
| P3-2 | CH-SEC-018 | Church switch via POST + CSRF |
| P3-3 | CH-SEC-019 | Prefer IP-primary lockout; CAPTCHA after N; avoid locking victim identifiers from unauthenticated guesses |
| P3-4 | CH-SEC-020 | Pin `Django==5.1.15` or actually upgrade and test 6.x |
| P3-5 | CH-SEC-021 | Never publish Postgres/Redis host ports in a production overlay; rotate compose default passwords if ever used live |
| P3-6 | CH-SEC-022 | Align Django `SECURE_HSTS_SECONDS` with Nginx `max-age=31536000` |
| P3-7 | CH-SEC-L4 | Revoke trusted devices on every password-change / reset path |
| P3-8 | CH-SEC-P1 | Compare health tokens with `hmac.compare_digest` |
| P3-9 | CH-SEC-P2 | Confirm live Nginx `server_name` is `mychurch.zreta.com` (repo template may differ) |
| P3-10 | deps | Add read-only `pip-audit` (and npm audit if JS is added) to CI |

---

## Sequence (recommended)

```text
Week 0 (hotfix)
  P0-1 media object scope
  P0-2 MFA throttle

Week 1
  P1-1 announcement isolation
  P1-2 tenant_edit full_clean
  P1-5 remittance/recon wrappers

Week 2
  P1-3 asset journal finalize
  P1-4 contribution idempotency
  P2-4 / P2-5 concurrency locks

Week 3
  Remaining P2 (enumeration, welfare SoD, activity-log immutability, platform stats)
  Start P3 hardening
```

Do not treat P3 as a substitute for P0. Logout CSRF does not reduce the media IDOR.

---

## Regression tests that should exist (not added by this audit)

Do **not** modify production code in this audit. Add these tests when remediating:

| Finding | Proposed test |
|---------|----------------|
| CH-SEC-001 | Cross-tenant media 404 |
| CH-SEC-002 | General announcement not visible outside denomination |
| CH-SEC-003 | MFA lockout after N failures |
| CH-SEC-004 | Cross-denomination district POST rejected |
| CH-SEC-005 | Closed working day blocks depreciation; success locks journal |
| CH-SEC-006 | Duplicate contribution POST creates one receipt |
| CH-SEC-007 | `view_transactions`-only user 403 on remittance POST |
| CH-SEC-008 | Out-of-scope pending announcement detail 404 |
| CH-SEC-011 | Welfare creator cannot approve own case |
| CH-SEC-012 | Concurrent void creates one reversal |
| CH-SEC-L1 | Unanchored SUPER_ADMIN save rejected |

---

## Definition of done for a later “security-hardened” claim

All of the following must be true:

1. Private media is object- and tenant-scoped; tests assert deny.
2. MFA verify is throttled.
3. General announcements cannot cross denominations.
4. Core and satellite financial paths share approve/lock, working-day, SoD, and idempotency.
5. Platform operator stats are denomination-scoped.
6. `pip-audit` (or equivalent) runs in CI with a tracked exception list.

Until then, keep the verdict at **READY WITH CRITICAL REMEDIATIONS**.
