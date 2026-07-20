# ChurchHub — Cursor Architectural Audit Report

**Date:** 19 July 2026  
**Auditor role:** Lead Software Architect (read-only analysis)  
**Scope:** Requested AI/architecture docs, project Cursor rules, Django structure, tenancy, security, finance, and enterprise readiness  
**Constraint:** No application code was modified for this report

---

## 0. Documentation sources examined

### Requested files (status)

| Path | Status |
|------|--------|
| `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md` | **Empty stub** |
| `docs/AI_CONTEXT/BUSINESS_LOGIC.md` | **Empty stub** |
| `docs/AI_CONTEXT/CODING_GUIDE.md` | **Empty stub** |
| `docs/ARCHITECTURE/SYSTEM_ARCHITECTURE.md` | **Empty stub** |
| `docs/ARCHITECTURE/MULTI_TENANCY.md` | **Empty stub** |
| `docs/DATABASE/DATABASE_SCHEMA.md` | **Empty stub** |
| `docs/SECURITY/AUTHORIZATION.md` | **Empty stub** |
| `.cursor/rules/*` | **Absent** — no project Cursor rules directory content |

Additional nested-doc findings:

| Area | Status |
|------|--------|
| `docs/MODULE_SPECIFICATIONS/**` | **All empty stubs** (including members, finance, ledger, transactions, permissions) |
| `docs/ARCHITECTURE/**` | Empty (except empty filenames present) |
| `docs/SECURITY/**` | Empty |
| `docs/DATABASE/**` | Empty |
| `docs/AI_CONTEXT/DOCUMENT_INDEX.md` | Non-empty; points agents at the empty stubs above |
| Root enterprise docs (`AGENTS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `DATABASE_DESIGN.md`, `BUSINESS_RULES.md`, `CODING_STANDARDS.md`, `ROADMAP.md`) | **Authoritative and populated** |

`DOCUMENT_INDEX.md` currently directs AI agents into hollow files. Until those stubs are filled, agents must prefer **`AGENTS.md` + root enterprise docs + live models**.

### Authoritative sources used for this audit

1. **`AGENTS.md`** — enterprise constitution (architecture, domains, security, finance, AI workflow)
2. Root docs: `ARCHITECTURE.md`, `SECURITY.md`, `DATABASE_DESIGN.md`, `BUSINESS_RULES.md`, `CODING_STANDARDS.md`, `ROADMAP.md`
3. Live Django codebase: `church_system/settings.py`, `church_system/urls.py`, all app `models.py`, services, middleware, scoping helpers, tests

---

## 1. Current architecture assessment

### Verdict

ChurchHub is a **mature Django multi-tenant Church Management System** with a clear domain split, a real RBAC matrix, hierarchical org scoping, denomination SaaS isolation, and a financially serious transaction core (double-entry lines, approval lock, void/reversal, periods, working day, idempotency).

It is **closer to a production ChMS than a prototype**, but it is **not fully aligned** with the layered enterprise ideal in `AGENTS.md` / `ARCHITECTURE.md` (managers, repositories, selectors, soft delete, MFA, versioned API).

### Intended architecture (docs)

```
Browser → Bootstrap UI → Views/API → Permission checks → Services
       → Selectors / Managers / Repositories → Models → PostgreSQL
Background: Celery + Redis
```

### Actual architecture (code)

```
Browser → Bootstrap templates → Medium/fat FBVs → permissions.checks
       → flat services.py modules → Models → PostgreSQL (prod) / SQLite (local)
Background: Celery configured (partial / optional use)
Cross-cutting: church_scope + denomination_scope + org_scope + sitecontrol middleware
```

| Layer | Documented | Implemented | Gap |
|-------|------------|-------------|-----|
| Thin views | Required | Partial — finance better; members/org/sitecontrol heavier | High |
| Services | Required | Present in most domain apps | Low |
| Managers / Repositories / Selectors | Required | **Absent** (no `managers.py`, no `repositories/`, no `selectors/`) | High |
| RBAC | Required | Strong (registry + matrix + overrides + middleware) | Low–Medium |
| Multi-tenancy | Required | Strong (denomination + org subtree + church context) | Medium (polymorphic units) |
| Soft delete | Required | **Not implemented in models** (docs only) | High |
| Versioned REST API | Required | **Missing** (no DRF / `/api/v1/`) | High |
| MFA | Required | Stub field only (`User.mfa_enabled`) | High |

### Strengths

- Domain apps map cleanly to church administration concerns
- Org hierarchy + SaaS denomination wall is thoughtful and covered by isolation tests
- Finance path uses services, balance validation, maker-checker, period/working-day gates, void/reversal, idempotency keys
- Permission registry is large and template-wired via context processors
- Platform lane (`sitecontrol` / `/platform/`) separated from institution lane
- Custom `accounts.User` with explicit org scope fields and platform vs institution validation

### Weaknesses

- Nested `docs/` and module specs are empty — AI agents are directed to hollow files
- Layering stops at “services + views”; no repository/selector discipline
- Fat views and mega-services (SRP pressure)
- Dual remittance concepts; Budget ownership split across apps
- Soft-delete, MFA, visitors domain, inventory, procurement, and public versioned API still missing vs `AGENTS.md`

**Overall maturity:** Medium–Strong operational ChMS; Medium enterprise completeness vs written constitution.

---

## 2. Existing Django apps and responsibilities

Project package: **`church_system`**. Entry: `manage.py`. Auth user: **`accounts.User`**.

From `INSTALLED_APPS` in `church_system/settings.py`:

| App | Responsibility | Models (summary) | Services | Notes |
|-----|----------------|------------------|----------|-------|
| `admin_custom` | Django admin branding / permission helpers | None | — | Support only |
| `church_system` | Scope helpers, Celery, context processors, health, mail, tenant tests | — | Cross-cutting | Not a domain app |
| `accounts` | Auth user, invitations, activity | `User`, `UserInvitation`, `UserActivityLog` | Yes | Custom user + org scope + platform flags |
| `permissions` | RBAC catalog, matrix, overrides, audit | `Permission`, `RolePermission`, `PermissionOverride`, `PermissionAuditLog` | Yes | Cache + role enforcement middleware |
| `organization` | Hierarchy + Church tenant root | GC → Union → Conference → Zone → District → Church + audit | Yes | Concrete hierarchy tables (no generic Organization) |
| `members` | Membership, families, transfers, records, gifts, leadership | Member + related | Yes | Granular `members/access.py` |
| `transactions` | Chart of accounts, journals, budgets, periods, reconciliation | Account, Transaction, Lines, Budget, MonthlyCutoff, Periods, WorkingDay, etc. | Large | Books of record |
| `dashboard` | Home KPIs, notifications, church switch | `Notification` | Large | Aggregation-heavy |
| `announcements` | Church communications | Announcement (+ images/views/audit) | Yes | Parallel to platform announcements |
| `reports` | Report center, export jobs | Export job + access audit | Large | Celery-capable exports |
| `meetings` | Meetings + worship attendance | Meeting, attendance models | Yes | Includes visitor *headcount* only |
| `budgets` | Budget UI/reporting | **Empty models** | Yes | Uses `transactions.Budget` |
| `giving` | Giving statements | None | Thin | Reads approved transaction lines |
| `ledger` | Posting category templates | `LedgerCategory` | Large | Not a second general ledger |
| `remittance` | Remit policies, settlements, welfare | Policy, Settlement*, Welfare* | Yes | Polymorphic `unit_type`/`unit_id` |
| `payroll` | HR payroll → posts journals | Employee, runs, lines, tax tables | Very large | Encrypted PII helpers |
| `assets` | Fixed assets / depreciation | FixedAsset + policies/logs | Large | Church-scoped |
| `portal` | Member self-service | None | Imports others | Thin façade |
| `sitecontrol` | SaaS platform, denominations, subscriptions | SiteSettings, Denomination, plans, apps, audits | Large | `/platform/` + public `/apply/` |

### URL map (`church_system/urls.py`)

`/dashboard/`, `/members/`, `/organization/`, `/transactions/`, `/accounts/`, `/permissions/`, `/announcements/`, `/reports/`, `/meetings/`, `/budgets/`, `/giving/`, `/ledger/`, `/remittance/`, `/payroll/`, `/assets/`, `/portal/`, `/platform/`, plus `/health/`, `/apply/`, `/admin/`.

### Cross-cutting middleware stack

1. Security / WhiteNoise / Session / CSRF / Auth  
2. `PermissionCacheMiddleware`  
3. `RoleEnforcementMiddleware`  
4. `DenominationContextMiddleware`  
5. `UserScopeMiddleware` / `PlatformSessionMiddleware` / `MaintenanceModeMiddleware` / `LoginRateLimitMiddleware`  

### Structural pattern vs AGENTS.md

Almost every domain app has a flat `services.py`. **None** implement the documented `managers.py` / `repositories/` / `selectors/` / `api/` packages. Views are overwhelmingly function-based.

---

## 3. Duplicate or conflicting models

| Issue | Detail | Severity |
|-------|--------|----------|
| **Budget ownership split** | Model lives in `transactions.Budget`; UI app `budgets` has empty `models.py` | Medium — ownership confusion |
| **“Ledger” vs books** | `ledger.LedgerCategory` is a posting template; real GL is `Transaction` / `TransactionLine` | Medium — naming conflict with AGENTS “ledger” language |
| **`accounts` vs `Account`** | App = users; model `transactions.Account` = chart of accounts | Low — cognitive only |
| **Dual remittance paths** | `transactions.MonthlyCutoff` (and related flows) vs `remittance.SettlementBatch` | **High** — dual operational remittance concepts |
| **Welfare coupling** | Welfare fund account types + remittance welfare models + cross-app hooks | Medium |
| **Polymorphic org units** | Remittance `unit_type`/`unit_id`; payroll `paying_unit_type`/`paying_unit_id` without FK integrity | Medium |
| **Hierarchy naming drift** | AGENTS: Division→…→Church; code: `Denomination` (SaaS) + `GeneralConference`→…→`Church` | Medium — docs/code vocabulary mismatch |
| **Announcements dual track** | `announcements.Announcement` (church) vs `sitecontrol.PlatformAnnouncement` | Low — intentional if documented |
| **Attendance dual models** | `MeetingAttendance` vs `AttendanceEvent`/`AttendanceRecord` | Low–Medium |
| **Audit log fragmentation** | Many parallel audit tables by domain | Low — intentional split; no unified audit store |
| **No second Member/Church** | Single canonical models | Good |

No catastrophic duplicate `Member` or `Church` tables were found.

---

## 4. Security risks

### Multi-tenancy (generally strong)

- **Denomination wall:** `church_system/denomination_scope.py` + middleware  
- **Org subtree:** `permissions/org_scope.py` (`church_q_for_scope`, scope levels)  
- **Church context:** `church_system/church_scope.py` (session / `?church=` constrained to manageable churches)  
- **User manageability:** `permissions/scoping.py`  
- Isolation tests exist under `church_system/`

### Residual risks (prioritized)

| Risk | Why it matters | Priority |
|------|----------------|----------|
| **Post-fetch authorization** | Some paths can load by bare PK then authorize — IDOR / miss-check risk if inconsistent | P0–P1 |
| **Soft-delete absent** | Hard deletes possible on many business objects contrary to AGENTS / DATABASE_STANDARDS | P0 |
| **MFA stub** | `User.mfa_enabled` help text: “enforcement not yet implemented” | P0 |
| **No versioned public API** | Future mobile/integrations may invent insecure ad-hoc JSON | P1 |
| **Uneven Django admin scoping** | Quality varies by ModelAdmin; mitigated somewhat by admin lane restriction | P1 |
| **Polymorphic UUID FKs** | Cannot enforce tenant integrity at DB level | P1 |
| **Field-level privacy** | AGENTS requires masking phones/DOB/etc.; not systematically enforced | P1 |
| **DEBUG defaults True / insecure SECRET_KEY fallback** | Blocked when `DEBUG=False`, but local misconfig risk remains | P2 |
| **Default ALLOWED_HOSTS** includes public hostnames when env unset | Env-overridable; still a default exposure risk | P2 |
| **SMTP password storage** | Platform email settings historically risk plaintext storage | P2 |
| **RoleEnforcement exemptions** | `/admin/`, `/platform/`, `/permissions/` skip church-assignment gate (other gates apply) | P2 |
| **File upload hardening** | Partial; no virus-scan integration | P2 |
| **Impersonation / platform break-glass** | Powerful; must stay audited via `PlatformAuditLog` | P2 (control, not defect) |

### Positive security controls already present

- CSRF middleware globally enabled; `X_FRAME_OPTIONS = DENY`  
- Login rate limiting + session age configuration  
- Maker-checker on financial approval (`approval_status`, `locked`, void/reversal)  
- Permission overrides + permission audit log  
- Payroll field encryption helpers  
- Platform vs institution URL isolation middleware  
- Production hardening when `DEBUG=False` (SSL redirect, secure cookies, HSTS)  
- Password validators include platform-specific length/uppercase rules  

---

## 5. Database improvement opportunities

| Opportunity | Recommendation |
|-------------|----------------|
| **Empty nested schema docs** | Populate `docs/DATABASE/DATABASE_SCHEMA.md` from live models; keep generated + curated hybrid |
| **PK consistency** | Most domain models use UUID; some legacy integer PKs remain — migrate long-term or document exceptions |
| **Soft-delete columns** | Standardize `is_deleted`, `deleted_at`, `deleted_by`, reason on business tables |
| **Balance integrity** | Posted transaction balance is app-enforced; consider DB-level guardrails for posted journals |
| **Polymorphic FKs** | Prefer concrete FKs or constrained content-type pattern with validation services |
| **Remittance unification** | Collapse cutoff vs settlement into one audited lifecycle |
| **Budget uniqueness / hard limits** | Soft warnings exist; hard limits and fund balance rules incomplete vs AGENTS |
| **Indexes** | Member/txn/user indexes are good; review search and report hot paths periodically |
| **SQLite vs PostgreSQL** | Local SQLite OK; ensure CI exercises PostgreSQL features used in production |
| **Common audit fields** | Align `created_by` / `updated_by` / `updated_at` consistency across modules |

---

## 6. Code quality issues

| Issue | Evidence | Impact |
|-------|----------|--------|
| Fat views | Large FBV modules in sitecontrol, members, organization, transactions, payroll | Maintainability, review cost |
| Mega-services | Large `services.py` in payroll, transactions, dashboard, ledger | SRP / testability |
| Missing managers/repos/selectors | AGENTS mandates them; none found | Query logic leaks into views/services |
| View-only apps without schema | `budgets`, `giving`, `portal` (partly intentional) | Onboarding confusion |
| Documentation scaffold hollow | Nearly all nested `docs/**` stubs empty | AI/human drift |
| No `.cursor/rules` | Requested rules directory empty | Cursor cannot load project-local rules from that path |
| Test layout | Many `tests.py` files; coverage uneven outside finance/permissions/isolation | Regression risk |
| Naming collisions | `accounts` app vs GL `Account`; `ledger` app vs GL language | Cognitive load |
| Template/business coupling risk | Permission flags in context are good; business rules must stay out of templates | Ongoing discipline |

Recent positive patterns already in codebase: org subtree scoping, granular member permission gates, denomination isolation, financial period/working-day controls.

---

## 7. Missing enterprise features (vs AGENTS.md)

| Feature | Status |
|---------|--------|
| Soft delete standard | Missing |
| MFA / TOTP / recovery codes | Stub only |
| Versioned REST API + OpenAPI | Missing |
| Visitors domain (records, follow-up, conversion) | Missing (only attendance headcount) |
| Inventory / stock movements | Missing |
| Procurement / three-way match | Missing |
| Petty cash | Missing |
| Full fund accounting entity model | Partial (fund concepts on lines / accounts) |
| Multi-currency | Missing / future |
| Managers + Repositories + Selectors | Missing |
| Field-level PII masking framework | Missing (payroll encryption only) |
| Celery Beat scheduled enterprise suite | Partial Celery; not full Beat suite |
| Hard budget limits everywhere | Partial / soft |
| Universal immutable audit on all modules | Partial (strong in finance/permissions/platform) |
| Populated AI_CONTEXT / module specs | Missing (scaffold only) |
| Project `.cursor/rules` | Missing |

---

## 8. Recommended upgrade roadmap

### Phase 0 — Documentation truth (1–2 weeks)

1. Fill `docs/AI_CONTEXT/{SYSTEM_OVERVIEW,BUSINESS_LOGIC,CODING_GUIDE,DATABASE_MAP}.md` from root AGENTS + live apps (**no inventing fields**).  
2. Fill `docs/ARCHITECTURE/{SYSTEM_ARCHITECTURE,MULTI_TENANCY}.md` and `docs/SECURITY/AUTHORIZATION.md` from code.  
3. Either populate module specs or change `DOCUMENT_INDEX.md` to point only at root docs until specs exist.  
4. Add `.cursor/rules/` pointers to `AGENTS.md` + AI context so Cursor sessions load the same constitution.

### Phase 1 — Security hardening (2–4 weeks) — P0

1. Scoped querysets at fetch for remaining IDOR-ish paths (announcements, remittance, similar).  
2. Soft-delete mixin + policy for Members and other business objects (finance already uses void/reversal).  
3. MFA for SUPER_ADMIN / platform / high-privilege finance roles.  
4. Admin `ModelAdmin.get_queryset` audit for every registered model.  
5. Privacy helpers for phone/DOB/address in templates and any JSON search endpoints.

### Phase 2 — Domain consolidation (3–6 weeks) — P1

1. Unify remittance: one settlement lifecycle; deprecate or wrap `MonthlyCutoff` clearly.  
2. Clarify Budget ownership (`transactions` as store, `budgets` as presentation) in docs and imports.  
3. Rename or document `ledger` as “posting templates” to avoid GL confusion.  
4. Align hierarchy vocabulary (Denomination SaaS vs General Conference / Division) in AGENTS/docs.  
5. Extract managers for Member, Transaction, Church querysets.

### Phase 3 — Architecture fitness (ongoing) — P1/P2

1. Split mega-services (payroll, transactions, dashboard).  
2. Thin fat views behind service/orchestrator modules.  
3. Introduce selectors for read models (dashboards, reports).  
4. Expand tests: permission deny overrides, GC scoping, export gating, remittance isolation.

### Phase 4 — Enterprise expansion (roadmap) — P2

1. `/api/v1/` with authentication, tenancy middleware, OpenAPI.  
2. Visitors, inventory, petty cash, procurement per AGENTS.  
3. Celery Beat for backups, reminders, depreciation, audit maintenance.  
4. Hard budget controls and fund balance policies as first-class rules.

---

## 9. Scorecard

| Area | Rating | Comment |
|------|--------|---------|
| Multi-tenancy | **Strong** | Denomination + org scope + church context |
| Permissions / RBAC | **Strong** | Registry/matrix/overrides; some post-fetch checks remain |
| Financial integrity | **Strong** | Double-entry, lock, void, periods, idempotency |
| Layered architecture | **Medium** | Services yes; managers/repos no; fat views |
| Security posture | **Medium–Strong** | CSRF/lanes good; soft-delete/MFA/API weak |
| Documentation system | **Weak** | Root AGENTS strong; nested `docs/` mostly empty |
| AGENTS completeness | **Medium** | Core ChMS present; visitors/inventory/API/MFA missing |
| Schema hygiene | **Medium–Strong** | UUID-heavy; polymorphic units; dual remittance |

---

## 10. Immediate conclusions for Cursor / AI work

1. **Do not treat empty nested `docs/` stubs as requirements** until populated — prefer `AGENTS.md` + root enterprise docs + live models.  
2. **Protect finance and tenancy first** — never invent journal fields; never bypass `church_q_for_scope` / `filter_by_church`.  
3. **Prefer extending services** over growing views further.  
4. **Next high-value engineering work** after this audit: Phase 0 docs + Phase 1 security (soft-delete, MFA, scoped fetch), then remittance unification.  
5. **No code changes were made** as part of this analysis — report only.

---

## Appendix A — Middleware & tenancy map

```
Request
  → PermissionCacheMiddleware
  → RoleEnforcementMiddleware          (church assignment for institution roles)
  → DenominationContextMiddleware      (SaaS denomination)
  → UserScopeMiddleware                (platform vs institution)
  → PlatformSession / Maintenance / LoginRateLimit
Views/Services
  → permissions.checks / org_scope / scoping
  → church_system.church_scope.filter_by_church | require_church
  → organization.access.scoped_*
```

Operational tenant: **Church** (with session `current_church_id` for hierarchy users).  
SaaS isolation boundary: **Denomination**.  
Platform operators: `is_platform_user` + `/platform/` lane.

---

## Appendix B — Financial control map

```
Draft Transaction + Lines (must balance)
  → Approve (not by creator) → locked
  → Void → reversal Transaction (reversal_of)
Periods / WorkingDay gate posting
FinancialIdempotencyKey for retries
FinancialAuditLog for mutations
Payroll / Assets / Remittance post into transactions services
```

---

## Appendix C — Live model inventory (by app)

| App | Models |
|-----|--------|
| `accounts` | User, UserActivityLog, UserInvitation |
| `permissions` | Permission, RolePermission, PermissionOverride, PermissionAuditLog |
| `organization` | GeneralConference, Union, Conference, Zone, District, Church, OrganizationAuditLog |
| `members` | Department, Family, Occupation, Member, MemberTransfer, Record, RecordImage, History, HistoryImage, SpiritualGift, MemberSpiritualGift, LeadershipRole, MemberAuditLog |
| `transactions` | Account, Transaction, TransactionLine, MonthlyCutoff, OfferingCategory, Budget, FinancialAuditLog, BankReconciliation, BankReconciliationItem, FinancialPeriod, WorkingDay, FinancialIdempotencyKey |
| `ledger` | LedgerCategory |
| `budgets` | *(none — uses transactions.Budget)* |
| `giving` | *(none)* |
| `remittance` | RemittancePolicy, RemittancePolicyAuditLog, SettlementBatch, SettlementLine, WelfareContribution, WelfareAssistanceCase, WelfareCaseAttachment, WelfareMemberLedger |
| `payroll` | PayComponentType, DeductionType, PayrollTaxTable, PayrollTaxBand, StatutoryContributionRule, Employee, EmployeeCompensation, EmployeeCompensationLine, EmployeeLoan, PayrollRun, PayrollLine, PayrollLineItem, PayrollRunAuditLog |
| `assets` | AssetCategoryTemplate, AssetCategory, DepreciationPolicy, FixedAsset, AssetDepreciationEntry, AssetMaintenanceLog, AssetAuditLog, AssetPolicyAuditLog |
| `meetings` | Meeting, MeetingAttendance, MeetingAttachment, MeetingActionItem, MeetingDecision, AttendanceEvent, AttendanceRecord |
| `announcements` | Announcement, AnnouncementImage, AnnouncementView, AnnouncementAuditLog |
| `reports` | ReportExportJob, ReportAccessAuditLog |
| `dashboard` | Notification |
| `portal` | *(none)* |
| `sitecontrol` | SiteSettings, SubscriptionPlan, PlatformPaymentMethod, TenantSubscription, PlatformAuditLog, PlatformAnnouncement, TenantApplication, Denomination |

---

## Appendix D — Hierarchy: docs vs code

| AGENTS.md vocabulary | Code reality |
|----------------------|--------------|
| Division | Closest SaaS concept: `sitecontrol.Denomination`; org top: `GeneralConference` |
| Union | `organization.Union` |
| Conference | `organization.Conference` (+ denomination FK) |
| Zone | `organization.Zone` |
| District | `organization.District` |
| Local Church | `organization.Church` (operational tenant) |

Treat Denomination as the **multi-tenant SaaS wall**, not a drop-in rename of Division, until documentation is reconciled.

---

*End of audit report. No application code was modified as part of this analysis.*
