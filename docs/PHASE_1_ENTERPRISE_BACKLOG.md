# ChurchHub — Phase 1 Enterprise Hardening Backlog

**Type:** Read-only audit  
**Date:** 20 July 2026  
**Constraint:** No application code was modified for this document  
**Sources:** Live Django apps, tests, settings, middleware; Phase 0 `docs/`; root `AGENTS.md`  
**Companions:** `docs/AI_CONTEXT/CURSOR_AUDIT_REPORT.md`, `docs/AI_CONTEXT/DOCUMENT_INDEX.md`, `docs/SECURITY/*`, module specs

| Label | Meaning |
|-------|---------|
| **Current** | Observed in code today |
| **Planned** | `AGENTS.md` aspirations |
| **Recommended** | This backlog’s suggested remediations |

Effort: **S** ≤ ~1 day · **M** ~2–5 days · **L** > 1 week (or multi-PR)

---

## Executive summary

ChurchHub is a strong multi-tenant ChMS with real RBAC, denomination isolation, and a serious double-entry finance core. Phase 1 should harden **authorization consistency**, **remittance integrity**, **auth abuse surfaces**, **admin blast radius**, **export audit completeness**, and **mega-module maintainability** — without inventing a parallel GL or premature `/api/v1/`.

Suggested implementation waves:

1. **Wave A (P0):** Permission gate alignment (transactions/assets), remittance settlement SoR, MFA for privileged roles, export audit coverage, unsafe admin registrations.  
2. **Wave B (P1):** Remittance dual-path cleanup, service splits, giving/report performance, CI coverage raise for finance/tenancy.  
3. **Wave C (P2):** Soft-delete design (Planned), UI/naming, docs polish, selectors where beneficial.

---

## P0 — Critical

### Verification status (Sprint 1)

| Item | Status | Notes |
|------|--------|-------|
| P0-1 | **VERIFIED** | Granular POST gates + `TransactionPostPermissionTests` green |
| P0-2 | **VERIFIED** | `can_view_assets` in read RBAC; board view-only tests green |
| P0-3 | **VERIFIED** | District+ post refused; church settlement posts with lock-after-lines |
| P0-4 | **VERIFIED** | Cross-path hard-gate via `remittance.cross_path` |
| P0-5 | **VERIFIED** | TOTP MFA enforced for privileged roles |
| P0-6 | **VERIFIED** | Rate limit covers portal login + password reset |
| P0-7 | **VERIFIED** | DEBUG safe defaults + prod refuse + health check |
| P0-8 | **VERIFIED** | Admin tenancy: OWNER global; others via `managed_denominations` |
| P0-9 | **VERIFIED** | `audit_export` + domain export paths write ReportAccessAuditLog |
| P0-10 | **VERIFIED** | Guarded deletes + attendance sync + draft payroll line purge |
| P0-11 | **VERIFIED** | Module posters create PENDING journals; `approve_module_journal` enforces maker-checker |
| P0-12 | **VERIFIED** | `get_unit_choices` uses manageable/platform scope; never global |
| P0-W1 | **VERIFIED** | Welfare disburse: case lock → lines → approve; no lock-before-lines |

**Welfare disbursement lock discipline (P0-W1) ✅ VERIFIED**

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — `select_for_update` on case; journal created unlocked; lines posted; then `approve_module_journal`; duplicates audited outside atomic rollback |
| **Location** | `remittance/welfare_services.disburse_welfare_case` |
| **Description** | Previously created `Transaction(locked=True)` then inserted lines → `ValidationError`. |
| **Fix** | Case row lock first; PENDING journal + lines; maker-checker approve; idempotency key `welfare-disburse-{case_id}`; regression tests in `remittance/tests_welfare_disburse.py`. |
| **Order** | Follow-up after P0-12 |

---

### P0-1 · Transactions POST gates overuse `can_approve_transactions` ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — POST handlers use `can_void_transactions`, `can_manage_working_day`, `can_lock_periods`, `can_unlock_periods` |
| **Location** | `transactions/views.py` — `void_transaction_view`, `working_day_open`, `working_day_close`, `period_lock`, `period_unlock` (and related POST handlers) |
| **Description** | Registry defines finer codes (`void_transactions`, `manage_working_day`, `lock_periods`, `unlock_periods`). Several mutating POSTs require only `can_approve_transactions`, while templates may show finer flags. |
| **Risk** | Privilege escalation within finance: approvers can void/lock periods/open working days without intended separation of duties. |
| **Recommended solution** | Gate each POST with the matching `can_*` helper; keep `manage_finances` only as explicit override if product requires. Add regression tests per action. |
| **Effort** | S |
| **Dependencies** | Permission matrix defaults review; template button consistency |
| **Order** | 1 |

---

### P0-2 · Assets `view_assets` unused in read RBAC ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — `user_may_view_assets` includes `can_view_assets`; asset list uses read access |
| **Location** | `assets/rbac.py` — `user_may_view_assets`; registry `view_assets` in `permissions/registry.py` |
| **Description** | Read access helper allows manage/approve/policy only — **not** `view_assets`. Read-only asset viewers granted `view_assets` may be denied. |
| **Risk** | Broken least-privilege (over-grant manage to enable read) or blocked legitimate viewers. |
| **Recommended solution** | Include `can_view_assets` in `user_may_view_assets`; verify all list/detail/export views; add tests. |
| **Effort** | S |
| **Dependencies** | Role matrix defaults for `view_assets` |
| **Order** | 2 |

---

### P0-3 · Remittance district+ settlement posts as no-op then marks POSTED ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — non-CHURCH posts raise `RemittancePolicyError`; batch stays DRAFT (no POSTED without journal) |
| **Location** | `remittance/services.py` — `post_settlement_batch` (`else: pass` for non-CHURCH units) |
| **Description** | Church-level settlements create auto-APPROVED locked TRANSFER journals. For district+ batches with `gross_received > 0`, ledger posting is stubbed (`pass`), yet batch status is still set to **POSTED**. |
| **Risk** | **Financial integrity:** books and settlement status diverge; remittance “posted” without GL movement. |
| **Recommended solution** | Either implement higher-unit GL posting via `transactions` services, or refuse POST with clear error until implemented. Never mark POSTED without journal (or explicit non-ledger mode flag). Add tests for district batch refusal/completion. |
| **Effort** | S (refusal path); M–L for full higher-unit GL |
| **Dependencies** | Remittance SoR decision (P1-1); CoA/clearing accounts for higher units |
| **Order** | 3 |

---

### P0-4 · Dual remittance operational paths (cutoff vs settlement) ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — mutual hard-gate via `remittance.cross_path`; both UIs remain; full SoR/UI consolidation is Planned |
| **Location** | `transactions` — `MonthlyCutoff`, `record_district_remittance`, `dashboard.views.cutoff`; `remittance` — `SettlementBatch`, policies, `post_settlement_batch` |
| **Description** | Two parallel remittance stories documented in Phase 0 specs. Operators can remit via treasury cutoff UI and/or settlement batches. |
| **Risk** | Double remittance, incomplete audit narrative, conflicting payable balances. |
| **Recommended solution** | Product decision: pick **one** system of record for church→district remittance; deprecate or hard-gate the other; single runbook + UI entry point. |
| **Implemented** | Hard-gate: refuse bank remit when POSTED church TITHE/COMBINED settlement overlaps month; refuse settlement draft/post when cutoff bank remit already active for overlapping month. |
| **Effort** | L (full SoR); S–M (hard-gate done) |
| **Dependencies** | P0-3; finance ops sign-off for UI consolidation |
| **Order** | 4 (design with P0-3) |

---

### P0-5 · MFA stub — privileged roles lack second factor ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — TOTP + recovery codes; login challenge; `MfaEnforcementMiddleware`; SiteSettings toggle |
| **Location** | `accounts.User.mfa_enabled` (stub); login `ChurchHubLoginView` / portal login; docs `SECURITY/AUTHENTICATION.md` |
| **Description** | MFA field exists; **enforcement not implemented**. Platform OWNER/SECURITY, SUPER_ADMIN, treasury can act with password only. |
| **Risk** | Account takeover → full platform or financial compromise. |
| **Recommended solution** | Implement TOTP (+ recovery codes) for platform OWNER/SECURITY and institution SUPER_ADMIN / high finance roles; challenge at login; do not claim MFA until enforced. |
| **Implemented** | `accounts.mfa` + enroll/verify views; encrypted secret; recovery hashes; enforce for OWNER/SECURITY/SUPER_ADMIN/TREASURY/superuser when `mfa_required_for_privileged`. |
| **Effort** | L |
| **Dependencies** | Session design; SiteSettings toggles; operator UX |
| **Order** | 5 |

---

### P0-6 · Login rate limit only on `/accounts/login` ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — portal login + password-reset POSTs throttled; MFA-pending counted as login success |
| **Location** | `sitecontrol.middleware.LoginRateLimitMiddleware` — matches `POST` path `/accounts/login` only; portal at `/portal/login/` |
| **Description** | Portal login and password-reset endpoints are not covered by the same throttle. |
| **Risk** | Credential stuffing / reset abuse bypasses primary login lockout. |
| **Recommended solution** | Extend middleware (or dedicated middleware) to portal login + password reset POSTs; prefer Redis in production for shared locks. |
| **Implemented** | Shared login paths (`/accounts/login`, `/portal/login`); reset keys for `/accounts/password_reset` and confirm; MFA pending clears fail counters. |
| **Effort** | S–M |
| **Dependencies** | Redis in prod (recommended); cache key design |
| **Order** | 6 |

---

### P0-7 · `DEBUG` defaults to True if `DJANGO_DEBUG` unset ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — unset defaults False under production markers; explicit True on prod-like hosts raises; health check fails if DEBUG in prod |
| **Location** | `church_system/settings.py` — `DEBUG = os.environ.get("DJANGO_DEBUG", "True")...` |
| **Description** | Misconfigured production without env var runs DEBUG. Insecure secret is blocked only when DEBUG is False. |
| **Risk** | Stack traces, debug tooling, weaker cookie flags if deploy forgets env. |
| **Recommended solution** | Default DEBUG to False when `DATABASE_URL`/production markers present; fail CI/deploy health if DEBUG True in prod; document in SETUP/DEPLOYMENT. |
| **Implemented** | `church_system.debug_config.resolve_debug`; health `debug` probe; docs/.env.example updated. |
| **Effort** | S |
| **Dependencies** | Deploy env checklist |
| **Order** | 7 |

---

### P0-8 · Unscoped / weakly scoped Django admin registrations ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — `admin_custom.tenancy` scopes assets/remittance/meetings/announcements admin querysets; platform OWNER remains global; other platform admin operators limited to `managed_denominations` (even when `is_superuser`) |
| **Location** | `admin_custom/tenancy.py`; `assets/admin.py`; `remittance/admin.py`; `meetings/admin.py`; `announcements/admin.py` |
| **Description** | Previously, ModelAdmin registrations lacked church/unit `get_queryset` filters. `/admin/` still requires `can_access_django_admin`, but every platform superuser previously saw all tenants because `operator_has_global_access` treats all platform superusers as global. |
| **Risk** | Cross-tenant data exposure via admin if a non-OWNER operator account is compromised or over-granted. |
| **Recommended solution** | Apply denomination/church queryset filters; keep audit models read-only; reduce registered editable models. |
| **Effort** | M |
| **Dependencies** | Platform operator SoD; admin UX |
| **Order** | 8 |

---

### P0-9 · Export paths without consistent access audit ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — `reports.services.audit_export` writes `ReportAccessAuditLog`; wired into giving, ledger, transactions (list + financial statement), members (directory + baptism), announcements, organization hierarchy, budgets, remittance welfare statement |
| **Location** | `reports/services.py` (`audit_export`); callers in domain `views.py` listed above |
| **Description** | Sensitive CSV/Excel/PDF exports often lacked ReportAccessAuditLog or domain EXPORT audit. |
| **Risk** | Compliance gap — cannot reconstruct who exported giving/member/finance data. |
| **Recommended solution** | Central helper `audit_export(...)` called from all export branches; or route exports through reports catalog. Tests that assert audit row created. |
| **Effort** | M |
| **Dependencies** | Audit schema choice (ReportAccess vs domain) |
| **Order** | 9 |

---

### P0-10 · Hard deletes of business-adjacent records ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** (Sprint 1) — dependency-guarded deletes with audit; attendance sync; draft-only payroll line purge |
| **Location** | `members/services.py` (`delete_department`, `unassign_spiritual_gift`); `budgets/services.py` (`delete_budget`); `meetings/services.py` (attendance sync); `payroll/services.py` (`_clear_draft_payroll_lines`); `permissions/views.py` (override delete — audit already present) |
| **Description** | Soft-delete is **not** implemented (Planned). Some UI/service paths hard-deleted business-adjacent rows without guards or audit. |
| **Risk** | Irreversible loss of history; audit incompleteness. |
| **Recommended solution** | Short term: block hard delete of departments with members; archive statuses. Medium: soft-delete design (Planned — do not fake as Current). Always audit before delete. |
| **Effort** | M–L |
| **Dependencies** | Product soft-delete design; migrations approval |
| **Order** | 10 |

---

### P0-11 · Settlement / payroll / assets auto-APPROVE journals bypass txn approval queue ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — module posters create PENDING journals and call `approve_module_journal` / `approve_transaction` with a checker distinct from `created_by` |
| **Location** | `remittance/services.post_settlement_batch`; `payroll/services` post/pay; `assets/services` acquisition (depreciation/disposal remain PENDING until manual approve) |
| **Description** | Ledger UI posts PENDING; some module posters created already APPROVED journals and bypassed self-approve rules at the txn layer. |
| **Risk** | Inconsistent financial control narrative; weaker review if module SoD is incomplete. |
| **Fix** | `transactions.services.approve_module_journal` + `resolve_journal_checker`; regression tests in `transactions/tests_auto_approve.py`. |
| **Effort** | M |
| **Dependencies** | Product control policy; P0-1 |
| **Order** | 11 |

---

### P0-12 · Remittance unit pickers can list unscoped org units ✅ VERIFIED

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — `get_unit_choices` requires a user and returns only manageable (or platform-scoped) units; save/edit paths reject and audit out-of-scope `unit_id` |
| **Location** | `remittance/services.get_unit_choices`; forms/views pass `user`; `save_remittance_policy` / `user_can_edit_remittance_policy` / `policy_index` |
| **Description** | If any view called without church/denomination filter, operators could see cross-tenant labels (IDs) via global `.objects.all()[:200]`. |
| **Risk** | Information disclosure / wrong-unit policy attachment across denomination wall. |
| **Fix** | Reuse `permissions.org_scope.manageable_scope_units` + platform denomination helpers; `SCOPE_VIOLATION` audit; regression tests in `remittance/tests_unit_scope.py`. |
| **Effort** | S–M |
| **Dependencies** | Call-site audit of `get_unit_choices` |
| **Order** | 12 |

---

## P1 — High

### P1-1 · Remittance dual-path cleanup (execution of P0-4)

| Field | Detail |
|-------|--------|
| **Location** | Same as P0-4 |
| **Description** | After SoR decision, remove or feature-flag dead path; migrate data; update docs. |
| **Risk** | Ongoing ops errors if both remain. |
| **Recommended solution** | Deprecation PR + redirect UI + tests. |
| **Effort** | L |
| **Dependencies** | P0-3, P0-4 |
| **Order** | 13 |

---

### P1-2 · Mega services / fat views (SRP)

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — P1-2 layered slices complete for: `transactions`, `members`, `remittance`, `payroll`, `assets`, `organization`, `reports`, `dashboard`, `permissions`, `accounts`, `sitecontrol`, `meetings`, `announcements`, `ledger`, `giving`, `budgets` (each has `selectors.py` + `repositories.py`; giving repos empty/read-only; budgets repos wrap `transactions.Budget` + audit) |
| **Location** | Large modules include `transactions/services.py`, `payroll/services.py`, `sitecontrol/views.py` / `services.py`, `members/views.py`, `reports/services.py`, `remittance/welfare_services.py` (exact line counts vary; all are maintenance hotspots) |
| **Description** | Business logic concentrated in very large modules; harder review/test. |
| **Risk** | Regression risk; slower delivery; accidental tenancy bugs. |
| **Recommended solution** | Split by concern (posting / approval / period / recon; payroll calc vs GL; welfare vs policy) without behavior change; add characterization tests first. |
| **Effort** | L |
| **Dependencies** | Test coverage on extracted paths |
| **Order** | 14 |
| **Transactions done** | Selectors for list/detail/pending/audit/recon/dashboard reads; repositories for create/save txn, lines, audit, working day, cutoff mark; `tests_layers.py` |
| **Members done** | Selectors for directory/search/detail/records/families/transfers/leadership/gifts; repositories for member/transfer/record/audit/dept/family/gift/leadership writes; `tests_layers.py`; services wired through selectors/repos |
| **Remittance done** | Selectors for policies/settlements/welfare/unit lookups/fund aggregates; repositories for policy/settlement/welfare/audit/ledger/attachment; views + `services`/`welfare_services`/`cross_path` wired; GL posts via `transactions.repositories`; `tests_layers.py` |
| **Payroll done** | Selectors for employees/runs/lines/tax/statutory/budget; repositories for run lifecycle persistence, defaults seed, compensation/loan/policy; post/pay via `transactions.repositories`; `tests_layers.py` |
| **Assets done** | Selectors for register/list/detail/categories/depreciation/audit/rollups; repositories for audit/policy/templates/asset/depreciation/maintenance; acquisition/depreciation/disposal journals via `transactions.repositories` + `_post_line`; `tests_layers.py` |
| **Organization done** | Selectors for scoped hierarchy/directory/detail/export/reconcile/form dropdowns; repositories for audit + GC/Union/Conference/Zone/District/Church persistence; ModelForm CRUD via `commit=False` + repos; forms querysets via selectors; `access.py` authz wrappers; services wired through selectors/repos; `tests_layers.py` |
| **Reports done** | Selectors for church/hierarchy scope, GL/member/welfare/attendance reads, account balances, export-job ownership; repositories for access audit + export-job lifecycle; builders/formatting stay in services; `audit_export` unchanged public API; `tests_layers.py` |
| **Dashboard done** | Selectors for church switch, notifications, financial/member/admin/hierarchy/executive reads; repositories for notification create/mark-read/purge; KPI/role rules stay in services; templates/Chart.js unchanged; `tests_layers.py` |
| **Permissions done** | Selectors for matrix/override/audit/catalog reads + church/user scope querysets; repositories for permission/matrix/override/audit writes; services keep resolution/cache/conflict rules; views/forms/scoping/`org_scope`/`scoping_checks` wired through layers; middleware/decorators/tags unchanged; `tests_layers.py` |
| **Accounts done** | Selectors for users/invitations/activity/directory filters + form org/member lookups; repositories for user/invitation/activity/MFA field persistence; services keep invite/profile/role rules; views/forms/MFA wired through layers; auth/session/middleware preserved; `tests_layers.py` |
| **Site Control done** | Selectors for denominations/plans/subscriptions/applications/audit/announcements/operators/hierarchy reads; repositories for audit/settings/plan/subscription/application/denomination/payment writes; services keep SaaS entitlement + lifecycle + approval rules; views/forms/`platform_access` wired through layers; platform vs institution lanes + maintenance + middleware + `/apply/` preserved; `tests_layers.py` |
| **Meetings done** | Selectors for church-scoped meetings/attendance/filters/form querysets/attachment lookups; repositories for meeting/attachment/action/decision/attendance persistence + roll sync; services keep attendance validation; workflow keeps minutes maker-checker; views/forms wired through layers; church scope + URLs/templates preserved; `tests_layers.py` |
| **Announcements done** | Selectors for pending/visible/list/detail/view-tracking/calendar reads; repositories for announcement/audit/view/image-formset writes; services keep publish/visibility/pin/approval rules; views/calendar wired through layers; church scope + audit preserved; `tests_layers.py` |
| **Ledger done** | Selectors for categories/accounts/ledger-sourced entries/summary/budget lookup; repositories for LedgerCategory seed/CRUD + Account/Transaction writes via `transactions.repositories`; services keep draft/post/seed/validation rules; views/forms wired through layers; **not a second GL** — books of record stay in `transactions`; `tests_layers.py` |
| **Giving done** | Selectors for approved member/church giving lines, scoped member lookup, type aggregates; repositories empty (read-only portal); services keep authz, abs totals, leaders ranking, export row prep; views wired through layers; **reporting/statement layer only** — `transactions` remains SoR; `tests_layers.py` |
| **Budgets done** | Selectors for scoped budget lists/detail/actuals/duplicate/form querysets; repositories for Budget save/delete + FinancialAuditLog via `transactions.repositories`; services keep variance/KPI/scope/validation/delete-with-actuals rules; views/forms wired through layers; **UI/workflow over `transactions.Budget`** (no local model); `tests_layers.py` |
| **Remaining in transactions** | Further split `services.py` into posting/approval/period/recon modules; migrate remaining ORM in cutoff/recon/budget helpers to repositories |
| **Remaining in members** | Split mega `views.py` into focused modules; move remaining ModelForm `save()` paths through repositories |
| **Remaining in remittance** | Split policy vs settlement vs welfare service modules; keep MonthlyCutoff vs SettlementBatch separate until an explicit merge decision; migrate remaining platform unit-picker helpers further if duplicated |
| **Remaining in payroll** | Split calc vs posting vs reporting concerns in `services.py`; route remaining ModelForm `save()` edit paths through repositories; leave `reports.py` until a dedicated report-layer task |
| **Remaining in assets** | Split lifecycle vs depreciation vs reporting in `services.py`; route remaining ModelForm `save()` edit paths through repositories; leave `rbac.py` hierarchy queries until a shared org-selector task |
| **Remaining in organization** | Optionally split onboard vs transfer vs provision concerns in `services.py`; leave forms/URL surface unchanged |
| **Remaining in reports** | Optionally split catalog builders into domain modules (finance/members/assets); push asset/payroll/budget builder ORM further into those apps' selectors; async job worker remains sync Celery task (no redesign) |
| **Remaining in dashboard** | Optionally split finance vs executive vs notification service modules; leave calendar/treasury console calls to their owning apps |
| **Remaining in permissions** | Optionally split resolution vs matrix-admin vs override services; leave `registry.py` / `roles.py` / middleware / template tags as public surfaces |
| **Remaining in accounts** | Optionally split invite vs profile vs MFA service modules; route `setup_churchhub` management command user writes through repositories; leave Django admin as break-glass |
| **Remaining in sitecontrol** | Optionally split settings vs subscription vs registration service modules; route management-command / admin ORM through repositories; leave model `save()` uniqueness hooks and middleware as public surfaces |
| **Remaining in meetings** | Optionally split workflow vs attendance service modules; leave admin church-scoped querysets and model properties as public surfaces |
| **Remaining in announcements** | Optionally split approval vs calendar service modules; leave admin church-scoped querysets and model `save()` hooks as public surfaces |
| **Remaining in ledger** | Optionally split seed vs posting vs CoA service modules; leave admin church-scoped querysets and `seed_ledger` management command church iteration as public surfaces |
| **Remaining in giving** | Optionally ORM-annotate leaders instead of Python aggregation; align `manage_giving` with index gates; leave `portal` consumer on public service APIs |
| **Remaining in budgets** | Optionally implement Planned approve/lock status machine when product requires it; leave `transactions.Budget` admin registration and `approve_budgets`/`lock_budgets` unused codes until wired |

---

### P1-3 · Duplicate permission / finance helpers

| Field | Detail |
|-------|--------|
| **Location** | `accounts.permissions` re-exports / legacy imports (e.g. dashboard pending announcements uses `accounts.permissions.can_approve_announcements`); `remittance` welfare paths historically mixed `accounts.permissions` vs `permissions.checks`; thin wrappers in `remittance/services.py` over `welfare_services.py` |
| **Description** | Dual import paths and wrappers confuse agents and reviewers. |
| **Risk** | Drift between wrappers; wrong permission semantics. |
| **Recommended solution** | Single canonical import `permissions.checks`; delete or deprecate `accounts.permissions` shims; one welfare entry module. |
| **Effort** | M |
| **Dependencies** | Grep-driven call-site migration |
| **Order** | 15 |

---

### P1-4 · Budgets `approve_budgets` / `lock_budgets` unused

| Field | Detail |
|-------|--------|
| **Location** | `permissions/registry.py`; `budgets/views.py` only uses view/manage/finances |
| **Description** | Registry codes exist without workflow states on `transactions.Budget`. |
| **Risk** | False sense of control; or dead permissions. |
| **Recommended solution** | Implement draft→approved→locked **or** remove from registry/docs until product needs them. |
| **Effort** | M |
| **Dependencies** | Product decision |
| **Order** | 16 |

---

### P1-5 · Giving leaders / report aggregations — Python loops

| Field | Detail |
|-------|--------|
| **Location** | `giving/services.py` — `church_giving_leaders`; similar patterns possible in reports builders |
| **Description** | Loads lines and aggregates in Python rather than ORM `annotate`/`Sum`. |
| **Risk** | Slow church dashboards / timeouts at scale. |
| **Recommended solution** | Replace with annotated aggregates; add index-aware queries; benchmark with large fixtures. |
| **Effort** | M |
| **Dependencies** | Indexes (P1-7) |
| **Order** | 17 |

---

### P1-6 · Enterprise architecture verification ✅ VERIFIED (read-only audit)

| Field | Detail |
|-------|--------|
| **Status** | **VERIFIED** — 21 Jul 2026 read-only audit after P1-2 layered migration |
| **Scope** | All 19 `INSTALLED_APPS`; 16 domain apps with `selectors.py` + `repositories.py` + `tests_layers.py` |
| **Overall score** | **8.0 / 10** — layering adopted broadly; residual ORM in `transactions/services.py`, partial view refinement, test-harness gaps |
| **View ORM** | **No** `Model.objects` or `get_object_or_404` in any `views.py`. Residual queryset refinement in `sitecontrol`, `members`, `payroll`, `assets`, `organization`, `dashboard`, `meetings` (see debt below). |
| **Selector purity** | **Pass** — no writes (`.create`, `.save`, `.delete`, etc.) in any `selectors.py` |
| **Repository purity** | **Pass** — no `can_*` / `ValidationError` business rules in any `repositories.py` |
| **Service ORM** | **15/16** layered apps clean; **`transactions/services.py`** still has ~19 direct `.objects` / `.save` calls (period lock, default account seed, monthly cutoff, bank recon, audit filter). One `expense_line.save()` in `payroll/services.py` (`_balance_journal`). |
| **Scoping** | **Preserved** — `filter_by_church` centralized in `church_system/church_scope.py`; denomination wall via org chain + `sitecontrol` / `permissions.org_scope` |
| **Permissions** | **Preserved** — views use `permissions.checks` / domain `can_*`; templates use context flags only (no `user_has_permission` in templates) |
| **Financial integrity** | **Unchanged** — `transactions` remains SoR; ledger/giving/budgets are UI/report layers; P0 finance items remain VERIFIED |
| **Circular imports** | **None observed** at import time across layered apps; lazy imports at finance boundaries mitigate hub risk |
| **Full test suite** | `python manage.py test --keepdb` — **599** tests, **564** passed, **12** failures, **23** errors (~93 min). Failures/errors are **test-harness** issues (MFA redirect 302 without `mfa_required_for_privileged=False`; Python 3.14 `Context.__copy__` in `store_rendered_templates`), not layering regressions. **2** explicit `skipTest` paths. No `DeprecationWarning` in output. |
| **Production blockers from audit** | **None from layering alone**; CI red on Py3.14 until view-test harness aligned (shared `TestCase` mixin for MFA + template-store patch). |

#### Per-app architecture scores (/10)

| App | Score | Layering | Notes |
|-----|-------|----------|-------|
| `transactions` | 7.5 | ✅ | Repos/selectors present; **services still own period/recon/cutoff ORM** |
| `members` | 8.0 | ✅ | View `.records.all()` / `.history.all()` on loaded instance |
| `remittance` | 9.0 | ✅ | Clean; welfare via selectors/repos |
| `payroll` | 8.5 | ✅ | One `.save()` in `_balance_journal`; view `run.lines.exists/count` |
| `assets` | 8.5 | ✅ | Hierarchy view filters `zones`/`districts` querysets |
| `organization` | 9.0 | ✅ | Stats `.count()` in view; otherwise layered |
| `reports` | 9.0 | ✅ | Builders in services; reads in selectors |
| `dashboard` | 8.5 | ✅ | `pending_for_user().count()` in view |
| `permissions` | 9.0 | ✅ | Resolution in services; matrix reads in selectors |
| `accounts` | 9.0 | ✅ | MFA views thin; repos for persistence |
| `sitecontrol` | 7.5 | ✅ | Fat views; `SiteSettings.load()` + inline `qs.filter`; stale `get_object_or_404` import |
| `meetings` | 8.5 | ✅ | `pending_minutes_for_user().count()` in view |
| `announcements` | 9.0 | ✅ | Calendar + approval layered |
| `ledger` | 9.0 | ✅ | Not a second GL; budget lookup selector shared with budgets domain |
| `giving` | 9.0 | ✅ | Read-only repos; reporting over `transactions` |
| `budgets` | 9.0 | ✅ | UI over `transactions.Budget`; views call services (selectors indirect) |
| `portal` | 6.0 | ❌ | Thin consumer; no selectors/repos; chains `visible_announcements().order_by` |
| `admin_custom` | 7.0 | partial | Tenancy scoping only (`tenancy.py` + `tests_tenancy.py`) |
| `church_system` | N/A | core | Settings, scope, health, MFA middleware — not a domain layer target |

#### Remaining architectural debt

1. **`transactions/services.py`** — migrate period lock/unlock, default account/offering seed, `MonthlyCutoff`, bank reconciliation, and audit filters to `transactions/repositories.py` (selectors already cover most reads).
2. **View-layer queryset refinement** — move inline `.filter`/`.count`/related-manager reads in `sitecontrol`, `members`, `payroll`, `assets`, `organization`, `dashboard`, `meetings` into selectors or service helpers.
3. **`portal`** — add `selectors.py` (home feed reads) or document as intentional thin shell over `announcements`/`giving` services.
4. **`sitecontrol/views.py`** — replace direct `SiteSettings.load()` with `get_site_settings()` service helper everywhere; remove unused `get_object_or_404` import.
5. **Forms ORM** — acceptable for `ModelChoiceField` querysets (`members`, `transactions`, `ledger`, `payroll`, `assets`, `remittance`, `reports` forms); optionally route through selectors for consistency.
6. **Service splits (P1-2 follow-through)** — `payroll` (~1100 LOC), `transactions` (~1000 LOC), `ledger` (~800 LOC), `dashboard` (~800 LOC), `remittance`+`welfare` (~1300 LOC combined).

#### Remaining technical debt

| Item | Location | Priority |
|------|----------|----------|
| Test harness: Py3.14 template context copy | `members/tests.py`, `portal/tests.py`, `transactions/tests.py`, `church_system/tests_tenant_isolation.py`, `church_system/tests_denomination_isolation.py` | **P0 CI** |
| Test harness: MFA redirect (302) | Same + tenant isolation suites — need `SiteSettings.mfa_required_for_privileged=False` in `setUpTestData` | **P0 CI** |
| Duplicate budget selector | `ledger/selectors.church_budget_for_account_year` vs `budgets/selectors` — cross-app read helper | P2 |
| Canonical permission imports | `accounts.permissions` shims vs `permissions.checks` (P1-3) | P1 |
| Budget approve/lock unused codes | `permissions/registry.py` vs `transactions.Budget` status machine (P1-4) | P1 |
| Giving leaders Python aggregation | `giving/services.church_giving_leaders` (P1-5) | P1 |
| FinancialAuditLog mutability | Model-level guards (P1-9) | P1 |
| Template related-manager iteration | `templates/meetings/detail.html`, org hierarchy partials — presentation-only, N+1 risk at scale | P2 |

#### Remaining code smells

- **Fat services** — see P1-2 “Remaining in …” bullets; no behavior change needed before split.
- **Stale import** — `sitecontrol/views.py` imports `get_object_or_404` unused.
- **Portal lazy import in view** — `giving.services` imported inside `home()` (acceptable; could move to service facade).
- **Organization hierarchy templates** — deep `.all()` chains in templates (org tree); consider annotated prefetch in selectors for large hierarchies.
- **No dead selectors/repos detected** — all 16 layered modules referenced from services, views, or `tests_layers.py`.

#### Recommended Phase 2 priorities

1. **P2-A · Finance layer completion** — finish `transactions` repository migration; route `payroll` `_balance_journal` line save through `transactions.repositories`.
2. **P2-B · CI green on Python 3.14** — shared test `Mixin` (`mfa_required_for_privileged=False` + `store_rendered_templates` patch) for all view/integration tests.
3. **P2-C · Service decomposition** — split `transactions` (posting/period/recon), `payroll` (calc/post), `remittance` (policy/settlement/welfare) without behavior change.
4. **P2-D · Portal + view cleanup** — portal selectors; sitecontrol view thinning; members detail records via selector.
5. **P2-E · Performance** — giving leaders ORM aggregates (P1-5); index review (P1-7); template prefetch for hierarchy/meeting detail.
6. **P2-F · Permission hygiene** — P1-3 canonical imports; P1-4 budget workflow or registry cleanup.
7. **P2-G · Remittance SoR** — execute P1-1 dual-path consolidation after ops sign-off.

---

### P1-7 · Index review for hot filters

| Field | Detail |
|-------|--------|
| **Location** | `transactions.models` already has several indexes; remittance policies indexed by unit; spot-check `dashboard.Notification`, report/export job tables, welfare case filters |
| **Description** | Some high-churn filters may lack composite indexes (church+date+status patterns). |
| **Risk** | Slow pages under load. |
| **Recommended solution** | EXPLAIN ANALYZE on top 10 slow queries from staging; additive indexes only with migrations. |
| **Effort** | M |
| **Dependencies** | Prod-like data; migration approval |
| **Order** | 19 |

---

### P1-8 · Test coverage gaps vs AGENTS / CI

| Field | Detail |
|-------|--------|
| **Location** | CI `.github/workflows/ci.yml` — `coverage report --fail-under=50`; AGENTS targets 80%+ (higher for finance). Many apps have tests, but isolation/permission POST-gate tests uneven (void/period gates, remittance district POST, assets view_assets, export audit). |
| **Description** | Gate is 50%; critical paths may lack regression tests for P0 fixes. |
| **Risk** | Regressions in tenancy/finance. |
| **Recommended solution** | For each P0 fix, add isolation + permission tests first; raise fail-under gradually (55→60→…). |
| **Effort** | M ongoing |
| **Dependencies** | P0 workstreams |
| **Order** | Parallel with P0 |

---

### P1-9 · FinancialAuditLog / domain audits not model-immutable

| Field | Detail |
|-------|--------|
| **Location** | `PlatformAuditLog` enforces immutability; `FinancialAuditLog` and most others rely on admin discipline (`ReadOnlyAuditModelAdmin`) |
| **Description** | Superuser/admin could alter financial audit rows if registered writable. |
| **Risk** | Audit tampering. |
| **Recommended solution** | Model-level save/delete guards like PlatformAuditLog; DB role restrictions in prod. |
| **Effort** | M |
| **Dependencies** | Admin registration audit |
| **Order** | 20 |

---

### P1-10 · Payroll `_payroll_access` requires manage for many reads

| Field | Detail |
|-------|--------|
| **Location** | `payroll/views.py` — `_payroll_access`; hierarchy/read paths |
| **Description** | Broad manage gate for routes that could use `view_payroll` / overseer scope. |
| **Risk** | Over-privilege or blocked read-only payroll officers. |
| **Recommended solution** | Split read vs write decorators; align with registry. |
| **Effort** | S–M |
| **Dependencies** | Role matrix |
| **Order** | 21 |

---

## P2 — Medium

### P2-1 · UI consistency (Bootstrap patterns)

| Field | Detail |
|-------|--------|
| **Location** | `templates/` across apps |
| **Description** | Mixed density of cards, flash patterns, breadcrumb styles. |
| **Risk** | UX friction — not security. |
| **Recommended solution** | Shared partials for page headers, empty states, permission-denied flashes. |
| **Effort** | M |
| **Dependencies** | Design system notes in UI guidelines |
| **Order** | After P0/P1 |

---

### P2-2 · Naming inconsistencies (spec vs app)

| Field | Detail |
|-------|--------|
| **Location** | EVENTS→`meetings`, COMMUNICATIONS→`announcements`, FINANCE umbrella, budgets model in transactions |
| **Description** | Documented in Phase 0; still confuses contributors. |
| **Risk** | Wrong app edits by agents. |
| **Recommended solution** | Keep docs mapping; optional nav labels only — **do not rename apps** without approval. |
| **Effort** | S (docs) / L (rename — avoid) |
| **Dependencies** | DOCUMENT_INDEX |
| **Order** | Ongoing docs |

---

### P2-3 · Documentation improvements

| Field | Detail |
|-------|--------|
| **Location** | Root whitepapers vs `docs/`; outdated CURSOR_AUDIT_REPORT stubs section |
| **Description** | Phase 0 filled `docs/`; older audit report still describes empty stubs. |
| **Risk** | Agents trust stale audit status. |
| **Recommended solution** | Add banner to `CURSOR_AUDIT_REPORT.md` pointing to DOCUMENT_INDEX + this backlog; avoid parallel docs. |
| **Effort** | S |
| **Dependencies** | None |
| **Order** | Anytime |

---

### P2-4 · Technical debt — Budget ownership split

| Field | Detail |
|-------|--------|
| **Location** | `transactions.Budget` + `budgets` app UI |
| **Description** | Model/admin in transactions; UI in budgets. |
| **Risk** | Confusion; not immediate integrity risk. |
| **Recommended solution** | Keep Current; document clearly; optional move admin to budgets app later. |
| **Effort** | S–M |
| **Dependencies** | None |
| **Order** | Low |

---

### P2-5 · Future enterprise enhancements (Planned — not Current)

| Field | Detail |
|-------|--------|
| **Location** | AGENTS § soft-delete, visitors domain, inventory, procurement, multi-currency, `/api/v1/`, Celery everywhere |
| **Description** | Valuable but out of Phase 1 hardening unless product prioritizes. |
| **Risk** | Scope creep if mixed with P0. |
| **Recommended solution** | Separate Phase 2+ epics after P0/P1; API must reuse services + RBAC + tenancy + audit. |
| **Effort** | L each |
| **Dependencies** | Product roadmap |
| **Order** | After Wave B |

---

### P2-6 · Announcement status dual fields

| Field | Detail |
|-------|--------|
| **Location** | `announcements.models.Announcement` — `status` + boolean `is_approved` / `is_rejected` / `is_archived` |
| **Description** | Dual representation debt. |
| **Risk** | Inconsistent filters. |
| **Recommended solution** | Single status source of truth; migrate carefully. |
| **Effort** | M |
| **Dependencies** | Data migration approval |
| **Order** | Low |

---

### P2-7 · Session absolute timeout / logout-all

| Field | Detail |
|-------|--------|
| **Location** | `PlatformSessionMiddleware` idle timeout; AGENTS Planned absolute + devices |
| **Description** | Idle timeout Current; absolute/logout-all absent. |
| **Risk** | Stolen session longevity. |
| **Recommended solution** | Absolute max session age; logout-all on password change for privileged roles. |
| **Effort** | M |
| **Dependencies** | MFA (P0-5) sequencing |
| **Order** | After MFA or parallel |

---

## Suggested implementation order (consolidated)

| Step | ID | Wave |
|------|-----|------|
| 1 | P0-1 Permission POST gates (transactions) | A |
| 2 | P0-2 Assets `view_assets` | A |
| 3 | P0-12 Remittance unit scope | A |
| 4 | P0-6 Login/portal/reset rate limits | A |
| 5 | P0-7 DEBUG production defaults | A |
| 6 | P0-9 Export audit coverage | A |
| 7 | P0-8 Admin queryset hardening | A |
| 8 | P0-3 + P0-4 Remittance integrity + SoR design | A→B |
| 9 | P0-11 Document or align auto-APPROVE posters | A |
| 10 | P0-5 MFA privileged roles | A |
| 11 | P0-10 Unsafe delete policy | A/B |
| 12 | P1-8 Tests with each fix | Parallel |
| 13 | P1-1 Remittance cleanup execution | B |
| 14 | P1-3 Canonical permission imports | B |
| 15 | P1-5 Giving/report performance | B |
| 16 | P1-2 Service splits | B |
| 17 | P1-4/7/9/10 Remaining high items | B |
| 18 | P2-* | C |

---

## Out of scope for this audit

- Implementing any of the above  
- Creating `/api/v1/`  
- Renaming apps/models  
- Soft-delete schema delivery (design only under P0-10 / P2-5)

---

## Related reading

- `AGENTS.md` — constitution  
- `docs/AI_CONTEXT/DOCUMENT_INDEX.md` — doc map  
- `docs/SECURITY/AUTHENTICATION.md`, `AUTHORIZATION.md`, `AUDIT_COMPLIANCE.md`  
- `docs/MODULE_SPECIFICATIONS/FINANCE/`, `TRANSACTIONS/`, `REMITTANCE/`, `ASSETS/`, `PAYROLL/`  
- `docs/API/API_CONVENTIONS.md` — no public REST today  
