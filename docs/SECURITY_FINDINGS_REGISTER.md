# ChurchHub Security Findings Register

**Audit date:** 14 August 2026  
**Commit:** `8eb5730f91b18212e17f48b3550afa952492437b` (`main`)  
**Status vocabulary:** CONFIRMED / LIKELY / POTENTIAL  
**Remediation vocabulary:** OPEN / PARTIALLY FIXED / FIXED (does not erase historical findings)

This register does **not** replace `docs/SECURITY_AND_DEPLOYMENT_AUDIT.md`.

**Remediation checkpoints:**
- Phase 1 (`44f5575`): media ACL (CH-SEC-001 partial), MFA throttle, remittance/recon write gates
- Phase 2 (working tree on `feature/sec-phase1-media-mfa-finance`): CH-SEC-002 / CH-SEC-008 announcement denomination isolation

---

## Inventory

| ID | Sev | Audit status | Remediation | Title | Cross-tenant | Auth required |
|----|-----|--------------|-------------|-------|--------------|---------------|
| CH-SEC-001 | HIGH | CONFIRMED | PARTIALLY FIXED | Private media lacks object/tenant authorization | Yes | Yes |
| CH-SEC-002 | HIGH | CONFIRMED | FIXED | General announcements cross denomination wall | Yes | Yes |
| CH-SEC-003 | HIGH | CONFIRMED | FIXED (Phase 1) | MFA verification not throttled | No | Post-password |
| CH-SEC-004 | HIGH | CONFIRMED | FIXED (Phase 3) | Tenant district reassignment skips `Church.clean()` | Yes | Platform |
| CH-SEC-005 | HIGH | CONFIRMED | FIXED (Phase 3) | Asset journals pending; working day skipped | No | Staff |
| CH-SEC-006 | HIGH | CONFIRMED | FIXED (Phase 3) | Contribution posting has no idempotency | No | Staff |
| CH-SEC-007 | HIGH | CONFIRMED | FIXED (Phase 1) | Remittance/bank-rec use read-oriented wrapper | No | Staff |
| CH-SEC-008 | MEDIUM | CONFIRMED | FIXED | Announcement detail IDOR for approvers | Yes | Staff |
| CH-SEC-009 | MEDIUM | CONFIRMED | OPEN | Platform dashboard stats not denomination-scoped | Yes | Platform |
| CH-SEC-010 | MEDIUM | CONFIRMED | OPEN | Portal login account enumeration | N/A | No |
| CH-SEC-011 | MEDIUM | CONFIRMED | FIXED (Phase 3) | Welfare same-user approval | No | Staff |
| CH-SEC-012 | MEDIUM | CONFIRMED | FIXED (Phase 3) | Concurrent void can double-reverse | No | Staff |
| CH-SEC-013 | MEDIUM | CONFIRMED | FIXED (Phase 3) | Incomplete idempotency keys reusable | No | Staff |
| CH-SEC-014 | MEDIUM | CONFIRMED | OPEN | UserActivityLog deletable in admin | No | Break-glass |
| CH-SEC-015 | MEDIUM | CONFIRMED | OPEN | Email+DOB first-login credential | No | Public portal |
| CH-SEC-016 | MEDIUM | CONFIRMED | OPEN | Some financial CSVs unaudited | No | Staff |
| CH-SEC-017 | LOW | CONFIRMED | OPEN | GET logout CSRF | No | Victim session |
| CH-SEC-018 | LOW | CONFIRMED | OPEN | GET church switch | No | Staff |
| CH-SEC-019 | LOW | CONFIRMED | OPEN | Identifier lockout DoS | N/A | No |
| CH-SEC-020 | LOW | CONFIRMED | OPEN | Django pin drift 6.0 vs 5.1.15 | N/A | N/A |
| CH-SEC-021 | LOW | CONFIRMED | OPEN | Compose publishes DB/Redis + default passwords | Dev | N/A |
| CH-SEC-022 | LOW | CONFIRMED | OPEN | Django HSTS 1h vs Nginx 1y | N/A | N/A |
| CH-SEC-L1 | HIGH | LIKELY | OPEN | Unanchored SUPER_ADMIN is global | Yes | If user exists |
| CH-SEC-L2 | MEDIUM | LIKELY | OPEN | Upload validation is MIME/extension only | Maybe | Yes |
| CH-SEC-L3 | MEDIUM | LIKELY | FIXED (Phase 3) | Settlement/district remittance races | No | Staff |
| CH-SEC-L4 | LOW | LIKELY | OPEN | Password-reset paths skip trusted-device revoke | No | Yes |
| CH-SEC-P1 | LOW | POTENTIAL | OPEN | Health token compared without `compare_digest` | N/A | No |
| CH-SEC-P2 | INFO | POTENTIAL | OPEN | Nginx template hostnames vs `mychurch.zreta.com` | N/A | N/A |

---

## CH-SEC-001 — HIGH — CONFIRMED

1. **ID:** CH-SEC-001  
2. **Severity:** HIGH  
3. **Title:** Private media served to any authenticated user  
4. **Affected application:** ChurchHub media plane  
5. **Affected file:** `church_system/media_views.py`  
6. **Exact location:** `protected_media()` lines 46–64; encoded as intended in `church_system/tests_media_access.py` 77–82  
7. **Type:** Broken object-level authorization / IDOR / cross-tenant file access  
8. **Technical explanation:** After path normalization, non-branding files require `request.user.is_authenticated` only. No church, denomination, owner, or permission check. Nginx then honors `X-Accel-Redirect` to `/internal-media/`. Member photos (`members/profile_pictures/`), records, history, welfare files, meeting attachments, announcement images, and `exports/reports/` share this gate. Django `FileField` typically preserves original filenames, so `photo.jpg` / export titles are guessable.  
9. **Attack scenario:** Member or staff of Church A logs in, requests `/media/members/profile_pictures/<known-or-guessed-name>` or `/media/exports/reports/<export-filename>` belonging to Church B, receives the file.  
10. **Preconditions:** Valid session on any tenant; knowledge or guess of path.  
11. **Business impact:** Cross-tenant PII (including photos of congregants), welfare documents, financial export files.  
12. **Why existing protection is insufficient:** Authentication is not tenancy. Tests lock in the insecure behavior.  
13. **Remediation:** Authorize by mapping URL → owning model/church; deny if `get_manageable_churches` / owner does not match. Do not serve `exports/reports/` except to the export job owner. Prefer UUID filenames.  
14. **Regression test:** User in denomination A must receive 404/403 for denomination B member photo and for another user’s export file.  
15. **Auth required:** Yes  
16. **Crosses tenant boundaries:** Yes  
17. **Confidence:** High  

**Remediation (Phase 1):** `user_may_access_media` + `protected_media` 404 for unauthorized paths — **PARTIALLY FIXED**.  
**Still OPEN under CH-SEC-001:** direct S3/`FileField.url` bypass when storage is public (INV-MED-03). Phase 2 announcement images authorize via `Announcement.denomination`, not creator heuristic.

---

## CH-SEC-002 — HIGH — CONFIRMED

1. **ID:** CH-SEC-002  
2. **Severity:** HIGH  
3. **Title:** General announcements have no denomination owner  
4. **Affected application:** announcements  
5. **Affected file:** `announcements/selectors.py`, `announcements/services.py`, `announcements/models.py`  
6. **Exact location:** `announcements_for_church_ids()` 50–51 ORs `visibility="general"`; `visible_announcements()` 110–130  
7. **Type:** Broken tenant isolation  
8. **Technical explanation:** General announcements use `church=None` and have no denomination FK. Visibility queries include all general rows for every church-scoped user.  
9. **Attack scenario:** A top-level user in Tenant A publishes a general announcement; staff/members in Tenant B see title/body/audience metadata.  
10. **Preconditions:** Ability to create general announcements in one denomination; victims in another.  
11. **Business impact:** Cross-org internal communications leak.  
12. **Why insufficient:** Church-id IN lists do not constrain church-less rows.  
13. **Remediation:** Add `denomination` FK (or forbid church-less rows); filter general announcements by `get_user_denomination`.  
14. **Regression test:** User in denom B must not see general announcement created in denom A.  
15. **Auth required:** Yes  
16. **Crosses tenant boundaries:** Yes  
17. **Confidence:** High  

**Remediation (Phase 2):** **FIXED.** Explicit `Announcement.denomination` FK; selectors/services fail closed on NULL; `visible_announcements` / pending / pin limits are denomination-bound; `view_all_churches` no longer means all denominations. Migration `0005_announcement_denomination` backfills from church only and quarantines unresolvable generals (no creator guess). Tests: `announcements/tests_denomination_isolation.py`.

---

## CH-SEC-003 — HIGH — CONFIRMED

1. **ID:** CH-SEC-003  
2. **Severity:** HIGH  
3. **Title:** MFA verification has no failed-attempt throttle  
4. **Affected application:** accounts MFA  
5. **Affected file:** `accounts/mfa_views.py`, `sitecontrol/middleware.py`  
6. **Exact location:** `mfa_verify()` POST 155–172; limiter `LOGIN_PATHS` 165–169 excludes `/accounts/mfa`  
7. **Type:** Missing brute-force protection  
8. **Technical explanation:** After password success, 6-digit TOTP/email OTP (`accounts/mfa.py`) can be posted unlimited times. Email OTP lives 10 minutes.  
9. **Attack scenario:** Attacker with password (phish/reuse) scripts `/accounts/mfa/verify/` until the OTP hits.  
10. **Preconditions:** Correct password; MFA enabled; not on trusted device.  
11. **Business impact:** Privileged staff/platform account takeover.  
12. **Why insufficient:** Login limiter stops at password; MFA is the remaining factor.  
13. **Remediation:** Per-user/IP lockout on MFA verify and email OTP send; consider longer OTPs; `hmac.compare_digest` already used if present—keep it.  
14. **Regression test:** N+1 invalid MFA POSTs return 429/lockout; valid code after lockout fails until window expires.  
15. **Auth required:** Password step / pending MFA session  
16. **Crosses tenant boundaries:** No  
17. **Confidence:** High  

---

## CH-SEC-004 — HIGH — CONFIRMED

1. **ID:** CH-SEC-004  
2. **Severity:** HIGH  
3. **Title:** Tenant edit can move a church to another denomination’s district  
4. **Affected application:** sitecontrol tenants  
5. **Affected file:** `sitecontrol/views.py` `tenant_edit` 732–746; `sitecontrol/forms.py` `TenantChurchForm` 705–714; `sitecontrol/repositories.py` `save_model` 27–30; `organization/models.py` `Church.clean` 159–171  
6. **Type:** Broken access control / tenancy mutation  
7. **Technical explanation:** Form exposes unrestricted `district` FK. Access is checked on the **source** church only. Persist uses `Model.save()`, which does **not** run `Church.clean()` that would block cross-denomination moves. `SUPPORT`/`BILLING` have `manage_tenants`.  
8. **Attack scenario:** Scoped or global operator with manage_tenants reassigns Church A to a district under Denomination B, mixing org trees and subscriptions.  
9. **Preconditions:** Platform user with `CAP_MANAGE_TENANTS`.  
10. **Business impact:** Tenant relocation, billing/scope corruption, possible cross-org data adjacency.  
11. **Why insufficient:** Model validation is not invoked on this write path.  
12. **Remediation:** `full_clean()` before save; constrain district queryset to accessible denominations; re-check destination after change.  
13. **Regression test:** POST tenant_edit with other-denomination district_id is rejected; church.district unchanged.  
14. **Auth required:** Platform  
15. **Crosses tenant boundaries:** Yes  
16. **Confidence:** High  

**Remediation (Phase 3):** **FIXED.** `organization.repositories.save_church` / `sitecontrol.repositories.save_model|save_church` call `full_clean()`; `TenantChurchForm` scopes districts and validates same-denomination destination; `tenant_edit` re-checks. Tests: `transactions/tests_phase3_financial.py` Phase3TenantIntegrityTests.

---

## CH-SEC-005 — HIGH — CONFIRMED

1. **ID:** CH-SEC-005  
2. **Severity:** HIGH  
3. **Title:** Asset depreciation/disposal update the register while GL journals stay pending and skip working-day checks  
4. **Affected application:** assets  
5. **Affected file:** `assets/services.py` 373–417 (depreciation), 470–524 (disposal); contrast `transactions/services.py` 108–121  
6. **Type:** Financial integrity / incomplete posting  
7. **Technical explanation:** CAPITAL journals are created and balanced but not approved/locked. Asset `accumulated_depreciation` / `DISPOSED` updates immediately. Only period-open is asserted, not the open working day. Disposal is allowed for `manage_assets` without SoD.  
8. **Attack scenario:** User posts depreciation/disposal on a closed business day inside an unlocked month; books and asset register diverge until someone notices pending CAPITAL journals.  
9. **Preconditions:** Asset management permission; unlocked period.  
10. **Business impact:** Unreliable fixed-asset and GL reporting; audit failure.  
11. **Why insufficient:** Core posting rules were not reused.  
12. **Remediation:** Call the same approve/lock path as other module journals; `assert_working_day_allows_posting`; SoD on dispose.  
13. **Regression test:** Depreciation on a closed working day raises; after success, related Transaction is APPROVED and locked.  
14. **Auth required:** Yes  
15. **Crosses tenant boundaries:** No  
16. **Confidence:** High  

**Remediation (Phase 3):** **FIXED.** Depreciation/disposal/acquisition assert working day + period; CAPITIAL journals use `approve_module_journal`; register/DISPOSED only after APPROVED; Celery/`user=None` leaves PENDING without register mutation. Tests: Phase3AssetJournalTests + assets tests.

---

## CH-SEC-006 — HIGH — CONFIRMED

1. **ID:** CH-SEC-006  
2. **Severity:** HIGH  
3. **Title:** Member contribution recording is not idempotent  
4. **Affected application:** contributions  
5. **Affected file:** `contributions/services.py` `record_member_contribution` 160–201; `contributions/views.py` 216–237; `contributions/models.py` 162–168  
6. **Type:** Replay / duplicate posting  
7. **Technical explanation:** Each POST creates a new receipt + `MemberContribution`. No `FinancialIdempotencyKey`, no unique constraint on transaction. Imports repeat the same path.  
8. **Attack scenario:** Double-click or replayed POST doubles giving totals and GL receipts.  
9. **Preconditions:** Permission to record campaign contributions.  
10. **Business impact:** Inflated income, member statements wrong.  
11. **Why insufficient:** Receipts elsewhere claim idempotency; this path does not.  
12. **Remediation:** Claim idempotency key; unique (campaign, member, date, amount, nonce) or bind to client key.  
13. **Regression test:** Two identical POSTs yield one contribution and one receipt.  
14. **Auth required:** Yes  
15. **Crosses tenant boundaries:** No  
16. **Confidence:** High  

**Remediation (Phase 3):** **FIXED.** `record_member_contribution` claims `CONTRIBUTION` via `claim_financial_idempotency`; views/bulk/import pass keys; completed replay returns existing gift. Migration `0022` adds action choice. Tests: Phase3ContributionIdempotencyTests.

---

## CH-SEC-007 — HIGH — CONFIRMED

1. **ID:** CH-SEC-007  
2. **Severity:** HIGH  
3. **Title:** Remittance posting and bank-rec create/match authorized as “any finance view/record”  
4. **Affected application:** transactions  
5. **Affected file:** `transactions/views.py` `_finance_required` 83–94; `record_remittance_view` 429–449; recon create 748–766; match 769–790  
6. **Type:** Vertical privilege escalation  
7. **Technical explanation:** Wrapper ORs `can_manage_finances`, `can_view_transactions`, `can_manage_receipts`, `can_manage_expenses`. Default `manage_expenses` includes SECRETARY (`permissions/registry.py` `_ROLE_ALL_STAFF`). Those users can POST remittance journals and create/match reconciliations. Only finalize checks `can_finalize_reconciliation`.  
8. **Attack scenario:** Secretary records a district remittance or manipulates recon matches without treasury/leadership role.  
9. **Preconditions:** Staff role with any of the OR’d permissions.  
10. **Business impact:** Unauthorized cash movement / recon tampering.  
11. **Why insufficient:** View permission is treated as mutate permission.  
12. **Remediation:** Require `can_manage_finances` / dedicated remittance and `can_manage_reconciliation` on mutating views.  
13. **Regression test:** User with only `view_transactions` gets 403 on remittance POST and recon create.  
14. **Auth required:** Yes  
15. **Crosses tenant boundaries:** No (still church-scoped)  
16. **Confidence:** High  

---

## CH-SEC-008 — MEDIUM — CONFIRMED

**Announcement detail loads globally then allows any `can_approve_announcements` user to read pending/rejected content** (`announcements/views.py` 192–202). Approval mutation is later scoped, but confidentiality is already lost.  
**Remediation:** Load via scoped queryset; never use capability-alone for `can_see`.  
**Test:** Approver in church A cannot GET detail of pending announcement in church B.  
**Auth:** Yes. **Cross-tenant:** Yes. **Confidence:** High.

**Remediation (Phase 2):** **FIXED.** Detail/edit/approve/reject/archive load via `get_announcement_in_user_denomination_or_404`; `can_see` uses object-scoped `can_approve_announcement` (not capability-alone). Cross-denomination PKs return 404.

---

## CH-SEC-009 — MEDIUM — CONFIRMED

**`platform_stats()` and over-limit alerts are global** (`sitecontrol/views.py` dashboard; `sitecontrol/services.py` 692–770). `READONLY`/`SUPPORT` with `managed_denominations` still see platform-wide counts and up to five **other churches’ names**.  
**Remediation:** Filter stats/alerts with `filter_churches_for_operator`.  
**Test:** Operator limited to denom A must not see denom B church names or denom B counts.  
**Auth:** Platform. **Cross-tenant:** Yes. **Confidence:** High.

---

## CH-SEC-010 — MEDIUM — CONFIRMED

**Portal login returns distinct errors** for unknown email, duplicate email, DOB mismatch, and post-password state (`portal/services.py` 211–245; template shows non-field errors).  
**Remediation:** Generic “email or password incorrect”; log internally.  
**Test:** Unknown vs known email produce identical public error text.  
**Auth:** No. **Cross-tenant:** N/A. **Confidence:** High.

---

## CH-SEC-011 — MEDIUM — CONFIRMED

**`approve_welfare_case` does not compare creator vs approver** (`remittance/welfare_services.py` ~360–372). Users who hold both create and approve can self-approve. Core transactions block this.  
**Remediation:** Reject `case.created_by_id == user.id`.  
**Test:** Creator’s approve POST raises.  
**Auth:** Yes. **Cross-tenant:** No. **Confidence:** High.  

**Remediation (Phase 3):** **FIXED.** Creator cannot review/approve/reject; reviewer cannot final-approve; high-risk cases require UNDER_REVIEW first. Tests: Phase3MakerCheckerWelfareTests + updated welfare enterprise/disburse tests.

---

## CH-SEC-012 — MEDIUM — CONFIRMED

**`void_transaction` checks `is_voided` without `select_for_update`** (`transactions/services.py` 945–993). Two concurrent voids can each insert a reversal.  
**Remediation:** Lock the original row inside `atomic`; unique constraint on `reversal_of`.  
**Test:** Concurrent voids → one reversal, second raises.  
**Auth:** Yes. **Cross-tenant:** No. **Confidence:** High.  

**Remediation (Phase 3):** **FIXED.** `select_for_update` on void; partial unique `uniq_txn_one_reversal_per_original` after quarantine migration `0022`. Tests: Phase3VoidConcurrencyTests.

---

## CH-SEC-013 — MEDIUM — CONFIRMED

**`claim_financial_idempotency` returns existing incomplete keys** (`transactions/idempotency.py` 27–67) instead of locking/rejecting. Two in-flight posts can share a key.  
**Remediation:** `select_for_update` on the key row; reject if claimed and incomplete.  
**Test:** Parallel receipt POSTs with same key create one transaction.  
**Auth:** Yes. **Cross-tenant:** No. **Confidence:** High.  

**Remediation (Phase 3):** **FIXED.** Claim uses `select_for_update`; incomplete keys serialize under the row lock; completed keys raise `IdempotencyReplay`. Tests: Phase3IdempotencyTests.

---

## CH-SEC-014 — MEDIUM — CONFIRMED

**`UserActivityLogAdmin` disables add/change but not delete** (`accounts/admin.py` 63–75). Model has no immutable `delete`. Contrast `PlatformAuditLog`. Break-glass `/admin/` users can erase staff activity history.  
**Remediation:** `has_delete_permission = False`; override `delete()` to raise.  
**Test:** Admin delete of activity log is denied.  
**Auth:** Break-glass. **Cross-tenant:** No. **Confidence:** High.

---

## CH-SEC-015 — MEDIUM — CONFIRMED (takeover LIKELY without mailbox)

**Email + date of birth authenticates first portal login** (`portal/services.py` 55–86, 182–245). Device confirmation email is required on first/untrusted device (73–83 in `portal/views.py` / `portal_needs_device_confirmation`).  
**Impact:** Weak secret; takeover needs mailbox as well. Enumeration (CH-SEC-010) helps attackers find valid emails.  
**Remediation:** One-time invite/OTP instead of DOB; if DOB must remain, rate-limit and generic errors.  
**Test:** After password change, DOB login fails; untrusted device without confirm token cannot session-login.  
**Auth:** Public portal. **Confidence:** High for credential design; Medium for unaided takeover.

---

## CH-SEC-016 — MEDIUM — CONFIRMED

Asset register/activity CSV and contribution member-total export lack `audit_export` (`assets/views.py` 239–247, 417–439; `contributions/views.py` 179–196). Permission exists; forensic trail does not.  
**Remediation:** Write export audit like reports.  
**Auth:** Yes. **Cross-tenant:** No. **Confidence:** High.

---

## CH-SEC-017 — LOW — CONFIRMED

`dashboard.views.custom_logout` (191–200) has no `@require_POST`; portal navbar uses GET (`templates/includes/portal_navbar.html` 22). Third-party page can force logout.  
**Remediation:** POST + CSRF.  
**Auth:** Victim session. **Confidence:** High.

---

## CH-SEC-018 — LOW — CONFIRMED

`dashboard:switch_church` mutates session on GET (`dashboard/views.py` ~119–123).  
**Remediation:** POST + CSRF.  
**Confidence:** High.

---

## CH-SEC-019 — LOW — CONFIRMED

Failed logins lock by submitted identifier (`sitecontrol/middleware.py` 260–330). Attacker can lock a known username. Tradeoff of lockouts.  
**Remediation:** Prefer IP-primary limits; CAPTCHA after N; do not lock victim id from unauthenticated guesses alone.  
**Confidence:** High.

---

## CH-SEC-020 — LOW — CONFIRMED

`requirements.txt` line 5 `Django>=6.0.6` vs local install 5.1.15. Fresh CI/prod install may major-upgrade unexpectedly.  
**Remediation:** Pin `Django==5.1.15` (or actually upgrade and test 6.x).  
**Confidence:** High.

---

## CH-SEC-021 — LOW — CONFIRMED

`docker-compose.yml` publishes 5432/6379 and uses `churchhub`/`admin12345`-class secrets. Development only; dangerous if used as production topology.  
**Remediation:** Do not publish DB/Redis on host network in any prod overlay.  
**Confidence:** High.

---

## CH-SEC-022 — LOW — CONFIRMED

`production.py` `SECURE_HSTS_SECONDS = 3600` vs Nginx `max-age=31536000`. Browsers may see mixed policy depending on which header wins.  
**Remediation:** Align on one year if HTTPS-only is permanent.  
**Confidence:** High.

---

## LIKELY

**CH-SEC-L1 HIGH:** `get_manageable_churches` returns all churches when superadmin has no church/denomination (`permissions/scoping.py` 16–31). `User.clean()` would block; `save()` skips it.  
**CH-SEC-L2 MEDIUM:** `validate_upload` does not check magic bytes (`church_system/uploads.py` 100–138).  
**CH-SEC-L3 MEDIUM:** Settlement posting and district remittance duplicate checks are query-based without row locks.  

**Remediation (Phase 3):** **FIXED.** Settlement draft/post use `select_for_update`; partial unique `uniq_settlement_active_period_obligation` on `(from_unit_type, from_unit_id, offering_type, period_start, period_end)` for DRAFT|POSTED after quarantine (`0005`); `record_district_remittance` locks `MonthlyCutoff`. Tests: Phase3SettlementUniquenessTests.  
**CH-SEC-L4 LOW:** Staff profile password change and portal set-password do not always revoke trusted devices.

---

## POTENTIAL

**CH-SEC-P1:** Health token equality vs `hmac.compare_digest`.  
**CH-SEC-P2:** Repo Nginx `server_name` is `zreta.com`; live app is `mychurch.zreta.com` — verify live vhost.  
**CH-SEC-P3:** `|safe` in page header/table action slots — keep server-generated only.  
**CH-SEC-P4:** `CHURCHHUB_BACKUP_POST_HOOK` executes a configured binary (`backup_ops.py`).
