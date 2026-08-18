# ChurchHub — System Overview

**Audience:** AI agents and engineers before any code change  
**Source of truth:** Live Django codebase  
**Companion docs:** `AGENTS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `CODING_GUIDE.md`, `BUSINESS_LOGIC.md`, `DATABASE_MAP.md`, `CURSOR_AUDIT_REPORT.md`

---

## 1. What ChurchHub is

ChurchHub is a **server-rendered Django monolith** for hierarchical church administration and finance. It supports:

- Local church operations (members, attendance, announcements, meetings)
- Multi-level organizational hierarchy (General Conference → Union → Conference → Zone → District → Church)
- SaaS multi-tenancy via **Denomination** isolation
- Double-entry financial books with approval, void/reversal, periods, and working days
- Remittance / settlement, welfare, payroll, fixed assets, budgets, giving statements, reports
- A separate **platform** control plane (`/platform/`) for operators, subscriptions, and tenant applications

It is **not** a SPA and **does not** currently expose a Django REST Framework `/api/v1/` layer.

---

## 2. Technology stack (as implemented)

| Layer | Technology |
|-------|------------|
| Framework | Django (project package `church_system`) |
| Language | Python (see `CODING_STANDARDS.md` / `requirements.txt`) |
| Auth user | `accounts.User` (`AUTH_USER_MODEL`) |
| Database | PostgreSQL via `DATABASE_URL` (production); SQLite locally by default |
| Cache | Redis when `REDIS_URL` set; else LocMem |
| Background | Celery (`church_system/celery.py`) when broker configured; eager in tests |
| UI | Django templates + Bootstrap 5 (project `templates/`, `static/`) |
| Static | WhiteNoise |
| Monitoring | Optional Sentry via `SENTRY_DSN` |

---

## 3. High-level architecture

```
Browser
  → Bootstrap templates
  → Django views (mostly function-based)
  → permissions.checks / scoping helpers
  → <app>/services.py (business logic)
  → Django models / ORM
  → PostgreSQL or SQLite

Cross-cutting middleware:
  PermissionCache → RoleEnforcement → DenominationContext
  → UserScope → PlatformSession → Maintenance → LoginRateLimit
```

**Documented ideal** (`AGENTS.md` / `ARCHITECTURE.md`): Views → Services → Selectors / Managers / Repositories → Models.

**Actual code:** Views + flat `services.py` modules + models. There are **no** project-wide `managers.py`, `repositories/`, or `selectors/` packages. Prefer extending services rather than inventing those layers unless a change explicitly introduces them.

---

## 4. Installed Django apps

From `church_system/settings.py` `INSTALLED_APPS`:

| App | Role |
|-----|------|
| `admin_custom` | Django admin branding / helpers |
| `church_system` | Project core: scoping, Celery, context processors, health, mail |
| `accounts` | Custom user, invitations, activity logs |
| `permissions` | Permission registry, role matrix, overrides, audit, middleware |
| `organization` | Org hierarchy + Church (operational tenant) |
| `members` | Membership, families, transfers, records, gifts, leadership |
| `transactions` | Chart of accounts, journals, budgets, cutoffs, periods, reconciliation |
| `dashboard` | Home dashboard, notifications, church context switch |
| `announcements` | Church-level announcements |
| `reports` | Report center and export jobs |
| `meetings` | Meetings, minutes workflow, worship attendance |
| `budgets` | Budget UI/services over `transactions.Budget` (no local models) |
| `giving` | Giving statements derived from transactions (no local models) |
| `ledger` | Ledger category templates (`LedgerCategory`) — not a second GL |
| `remittance` | Remittance policies, settlement batches, welfare |
| `payroll` | Employees, payroll runs, statutory rules → posts journals |
| `assets` | Fixed assets, depreciation, maintenance |
| `portal` | Member-linked self-service views |
| `sitecontrol` | Platform SaaS: denominations, subscriptions, applications, owner marketing, settings |

---

## 5. URL map

Defined in `church_system/urls.py`:

| Prefix | App |
|--------|-----|
| `/health/` | Health check |
| `/apply/` | Public tenant application |
| `/contact/` | Public marketing inquiry |
| `/admin/` | Django admin |
| `/dashboard/` | `dashboard` |
| `/members/` | `members` |
| `/organization/` | `organization` |
| `/transactions/` | `transactions` |
| `/accounts/` | `accounts` (+ Django auth URLs) |
| `/permissions/` | `permissions` |
| `/announcements/` | `announcements` |
| `/reports/` | `reports` |
| `/meetings/` | `meetings` |
| `/budgets/` | `budgets` |
| `/giving/` | `giving` |
| `/ledger/` | `ledger` |
| `/remittance/` | `remittance` |
| `/payroll/` | `payroll` |
| `/assets/` | `assets` |
| `/portal/` | `portal` |
| `/platform/` | `sitecontrol` (platform operators) |
| `/` | Public landing (`church_system.views.public_home`); signed-in users are sent to dashboard, portal, or `/platform/` |

Login: `/accounts/login/` (`ChurchHubLoginView`). The site root is a public landing page with links to staff sign-in and the member portal.

---

## 6. Multi-tenancy model (two layers)

### 6.1 SaaS boundary — Denomination

- Model: `sitecontrol.Denomination`
- Conferences link via `organization.Conference.denomination`
- Church denomination is derived: `church.denomination` → conference denomination
- Helpers: `church_system/denomination_scope.py`
- Middleware: `DenominationContextMiddleware`

Denomination isolates branding, seeds, feature flags, and org trees for different church bodies on the same deployment.

### 6.2 Operational tenant — Church

- Model: `organization.Church`
- Most business records FK to Church (members, accounts, transactions, announcements, etc.)
- Active church context: session / query constrained by manageable churches
- Helpers: `church_system/church_scope.py` (`get_active_church`, `filter_by_church`, `require_church`, …)
- Org subtree access: `permissions/org_scope.py` (`church_q_for_scope`, scope levels)
- Manageable sets: `permissions/scoping.py` (`get_manageable_churches`, …)

### 6.3 Platform lane

- Users with `is_platform_user=True` operate `/platform/` only (not institution dashboard)
- Enforced via `UserScopeMiddleware` and related sitecontrol RBAC
- Subscriptions: `TenantSubscription` (OneToOne to Church)
- Applications: `TenantApplication` → approval provisions church / hierarchy

**Never** trust client-side filtering alone. Always apply server-side church / denomination / scope checks.

---

## 7. Organization hierarchy (code)

```
GeneralConference
  → Union
    → Conference  (+ optional Denomination FK)
      → Zone
        → District
          → Church   ← operational tenant
```

There is **no** `Division` model and **no** generic `Organization` model.  
`AGENTS.md` sometimes says “Division”; in code the SaaS top concept is **Denomination**, and the org-tree top is **GeneralConference**. See `DATABASE_MAP.md`.

---

## 8. Identity, roles, and permissions

- Custom user: `accounts.User` (UUID PK, role, scope_level, church + hierarchy scope FKs, platform flags, optional `member` OneToOne)
- Roles: defined in `permissions/roles.py` (`UserRole`)
- Org scope levels: `permissions/org_scope.py` (`OrgScopeLevel`)
- Permission matrix: `permissions` models + `permissions/registry.py` + `permissions/services.user_has_permission`
- View guards: `permissions.checks` (`permission_required`, `any_permission_required`, `can_*` helpers)
- MFA: `User.mfa_enabled` exists as a **stub** — enforcement is not implemented

See `BUSINESS_LOGIC.md` § Permissions and `ADMINISTRATION_AND_PERMISSIONS.md` / `SECURITY.md` for policy intent.

---

## 9. Financial core

Books of record live in **`transactions`**:

- `Account` — per-church chart of accounts (typed)
- `Transaction` + `TransactionLine` — double-entry style amounts that must sum to zero
- Approval statuses: PENDING → APPROVED / REJECTED; approved can lock; void creates reversal
- Gates: `WorkingDay`, `FinancialPeriod`
- Related: `Budget`, `MonthlyCutoff`, `OfferingCategory`, bank reconciliation, `FinancialAuditLog`, `FinancialIdempotencyKey`

Other apps **post into** or **read from** this core:

| App | Relationship |
|-----|----------------|
| `ledger` | Category templates guiding journal entry |
| `budgets` | UI/services over `transactions.Budget` |
| `giving` | Reads approved lines for statements |
| `remittance` | Policies/settlements/welfare; interacts with remit accounts / cutoffs |
| `payroll` | Creates PAYROLL (and payment) transactions |
| `assets` | Capitalization / depreciation into accounts |

Details: `BUSINESS_LOGIC.md` § Finance and `FINANCE.md`.

---

## 10. Cross-cutting concerns

| Concern | Where |
|---------|--------|
| Permission cache / role enforcement | `permissions/middleware.py` |
| Church / denomination context in templates | `church_system/context_processors.py` |
| Navigation / permission flags | Same context processors |
| Working day banner | `working_day_context` |
| Maintenance / login rate limit | `sitecontrol/middleware.py` |
| Health | `/health/` |
| Logging | `church_system/logging_config.py` |

---

## 11. What exists vs what AGENTS.md aspires to

| Topic | Live code | AGENTS / root docs aspiration |
|-------|-----------|-------------------------------|
| Soft delete (`is_deleted`) | Not on models | Required |
| MFA enforcement | Stub field only | Required for privileged roles |
| REST API `/api/v1/` | Not present | Documented as future standard |
| Visitors domain | Attendance headcount only | Full visitor CRM |
| Inventory / procurement / petty cash | Not present | Documented domains |
| Managers / repositories / selectors | Not present | Documented layers |

**Rule for agents:** implement against **code**. Treat AGENTS.md aspirations as roadmap, not as existing schema. Do not invent models or fields to match aspirational docs.

---

## 12. Documentation map for agents

| Need | Read first |
|------|------------|
| Constitution / never-do list | `AGENTS.md` |
| This overview | `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md` |
| How to write code here | `docs/AI_CONTEXT/CODING_GUIDE.md` |
| Business rules as coded | `docs/AI_CONTEXT/BUSINESS_LOGIC.md` |
| Models and relationships | `docs/AI_CONTEXT/DATABASE_MAP.md` |
| Prior audit findings | `docs/AI_CONTEXT/CURSOR_AUDIT_REPORT.md` |
| Root policy depth | `ARCHITECTURE.md`, `SECURITY.md`, `DATABASE_DESIGN.md`, `BUSINESS_RULES.md`, `CODING_STANDARDS.md` |

Nested stubs under `docs/ARCHITECTURE/`, `docs/SECURITY/`, `docs/DATABASE/`, and `docs/MODULE_SPECIFICATIONS/` may still be empty. Prefer this AI_CONTEXT set + root docs + code until those are filled.

---

## 13. Definition of a safe change

A safe ChurchHub change:

1. Preserves tenant isolation (church + denomination + org scope)
2. Preserves permission checks on every mutating path
3. Does not silently alter posted financial history (use void/reversal patterns)
4. Extends existing services rather than duplicating rules in views/templates
5. Adds or updates tests for tenancy, permissions, or finance when those areas are touched
6. Does not invent schema that is not approved / migrated

When uncertain: stop, explain, ask — do not guess.
