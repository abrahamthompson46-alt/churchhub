# ChurchHub — Coding Guide for AI Agents

**Audience:** AI agents and contributors implementing changes  
**Source of truth:** Live Django project layout and conventions  
**Companions:** `SYSTEM_OVERVIEW.md`, `BUSINESS_LOGIC.md`, `DATABASE_MAP.md`, root `CODING_STANDARDS.md`, `AGENTS.md`, `DEVELOPMENT_WORKFLOW.md`

This guide describes **how code is actually written in this repository**. Where `AGENTS.md` describes aspirational layers not present in the tree, this guide takes precedence for day-to-day implementation.

---

## 1. Before you change anything

1. Read `SYSTEM_OVERVIEW.md` and the relevant section of `BUSINESS_LOGIC.md`.  
2. Locate the existing app, models, services, views, forms, urls, and tests.  
3. Search for reusable helpers (`permissions.checks`, `church_scope`, existing services).  
4. Explain the approach for non-trivial changes; wait for approval on schema / finance / tenancy changes.  
5. Implement incrementally and add tests for tenancy, permissions, or finance when touched.

**Never invent** models, fields, APIs, roles, statuses, or workflows that are not in the codebase or an approved migration plan.

---

## 2. Project layout (actual)

```
ChurchHub/
  manage.py
  requirements.txt
  church_system/          # project package (settings, urls, celery, scoping)
  accounts/
  permissions/
  organization/
  members/
  transactions/
  dashboard/
  announcements/
  reports/
  meetings/
  budgets/                # UI over transactions.Budget
  giving/                 # reads transactions
  ledger/                 # LedgerCategory templates
  remittance/
  payroll/
  assets/
  portal/
  sitecontrol/            # /platform/
  admin_custom/
  templates/              # project-level templates
  static/
  docs/
  *.md                    # root enterprise documentation
```

### Typical domain app contents

Present in most apps:

- `models.py`, `views.py`, `urls.py`, `forms.py`, `services.py`, `admin.py`, `apps.py`
- `migrations/`, `tests.py` and/or `tests_*.py`
- Occasional: `access.py`, `signals.py`, `management/commands/`, sibling service modules

**Not present project-wide (except first slice):**

- `managers.py`
- `repositories/` packages
- `selectors/` packages  
- `api/` packages
- `services/` package directories (use flat `services.py` or a named sibling like `welfare_services.py`)

**Current exception:** `transactions`, `members`, `remittance`, `payroll`, `assets`, `organization`, `reports`, `dashboard`, `permissions`, `accounts`, `sitecontrol`, `meetings`, `announcements`, `ledger`, `giving`, and `budgets` each have `selectors.py` / `repositories.py` as the P1-2 architecture slices. Those modules are complete for this pattern (views/forms/services route through selectors/repos; ModelForm CRUD uses `commit=False` + repositories). Ledger remains posting templates/categories + CoA UI only — `transactions` owns Accounts/journals. Giving is a read-only reporting/statement layer (empty repositories). Budgets is the planning UI/workflow layer over `transactions.Budget` (no local Budget model). Do not invent parallel patterns in other apps without an explicit architectural task.

---

## 3. Architectural rules (practical)

| Layer | Responsibility | Convention |
|-------|----------------|------------|
| Templates | Presentation only | Bootstrap 5 patterns; no business rules |
| Views | HTTP, forms, auth redirects, call services | Prefer thin; many existing views are still fat — do not make them fatter |
| Services | Business rules, workflows, validation orchestration | Public functions named `create_*`, `approve_*`, `void_*`, … |
| Models | Fields, constraints, light `clean`/`save` | No large workflows |
| Permissions | Server-side authorization | Decorators + `user_has_permission` |
| Scoping | Tenant / org isolation | Always filter querysets |

### Documented but not implemented layers

Do **not** create managers/repositories/selectors solely because `AGENTS.md` mentions them, unless the task explicitly asks to introduce that pattern. Prefer improving `services.py` and shared scoping helpers.

---

## 4. Permissions — required patterns

**Import from:**

```python
from permissions.checks import (
    permission_required,
    any_permission_required,
    user_has_permission,
    can_view_members,  # example can_* helper
)
```

Common decorators:

- `@permission_required("codename")`
- `@any_permission_required("a", "b")`
- `@login_required` (Django) plus permission checks for app views

Engine: `permissions.services.user_has_permission`  
Object / church scope: `permissions.scoping_checks` (`can_act_on_church`, `filter_queryset_for_church_scope`, …)  
Roles: `permissions.roles.UserRole`  
Compat re-export: `accounts.permissions` (prefer `permissions.checks` for new code)

**Templates:** `{% load permission_tags %}` — `can`, `can_any`, etc. UI hiding is **not** security.

---

## 5. Tenant scoping — required patterns

### Church (operational tenant)

```python
from church_system.church_scope import (
    get_active_church,
    filter_by_church,
    require_church,
    get_available_churches,
)
```

### Denomination (SaaS wall)

```python
from church_system.denomination_scope import (
    get_active_denomination,
    filter_by_denomination,
    assert_same_denomination,
    assert_church_in_active_denomination,
)
```

### Org subtree

```python
from permissions.org_scope import church_q_for_scope, OrgScopeLevel
from permissions.scoping import get_manageable_churches, user_may_manage_target
```

**Rules:**

- Every new queryset on church-owned data must be scoped.
- Do not trust `?church=` without verifying manageability.
- Platform vs institution lanes are separated by middleware — do not mix responsibilities.

---

## 6. Service layer conventions

### Organization

- Default: `<app>/services.py`
- Split when large: e.g. `remittance/welfare_services.py`, `sitecontrol/registration_services.py`, `sitecontrol/provisioning_services.py`, `announcements/calendar_services.py`
- Adjacent modules: `transactions/treasury.py`, `transactions/idempotency.py`, `meetings/workflow.py`, `assets/rbac.py`

### Naming

- Public: verb phrases — `create_member`, `approve_transaction`, `void_transaction`, `post_payroll_run`
- Private: `_leading_underscore`
- Domain errors: exception classes in the service module (e.g. `UnbalancedTransactionError`)

### Examples of correct call sites

- Members: `members.services.create_member`, `request_transfer`, `complete_transfer`
- Finance: `transactions.services.record_receipt`, `approve_transaction`, `void_transaction`
- Accounts: `accounts.services.create_invitation`, `update_user_role`

Views should call services; they should not re-implement balance checks, transfer rules, or remittance math.

---

## 7. Models and migrations

- Prefer UUID primary keys for domain entities (already common).
- Put uniqueness and church integrity in DB constraints when possible.
- Keep `clean()` / `save()` light; workflows belong in services.
- **Never** invent fields. Schema changes require explanation, approval for destructive ops, and real migrations.
- Soft-delete fields from `AGENTS.md` / `DATABASE_STANDARDS.md` are **not** on models today — do not write code that assumes `is_deleted` exists.
- Finance: preserve void/reversal; do not “fix” posted journals in place.
- Do not delete or rewrite historical migrations.

---

## 8. Views, URLs, and templates

- Views are mostly function-based; a few CBVs exist (e.g. member list).
- Register URLs under the app’s `urls.py` and include them from `church_system/urls.py` when adding a new mount (rare).
- Templates live under project `templates/` (and app template dirs). Shared includes under `templates/include/`.
- Platform UI uses `sitecontrol` base templates / `static/css/platform.css`.
- Bootstrap 5 + Bootstrap Icons via vendor static assets.
- No DRF viewsets. Small JSON helpers (e.g. ledger) must remain session-authenticated and scoped.

---

## 9. Finance coding rules (non-negotiable)

1. Journal lines must balance (sum amounts = 0).  
2. Use existing approve / reject / void services.  
3. Respect `WorkingDay` and `FinancialPeriod` gates.  
4. Keep church consistency between transaction and accounts.  
5. Remittance percent rules: retain + remit = 100.  
6. Payroll and assets post through services into `transactions` — do not bypass.  
7. Log financial mutations via existing audit helpers/models.

See `BUSINESS_LOGIC.md` § Finance.

---

## 10. Testing

- Framework: **Django `TestCase`** via `manage.py test` (CI uses coverage + `manage.py test`).
- Locations: `<app>/tests.py`, `<app>/tests_*.py`, `church_system/tests_*.py`.
- Common patterns: `setUpTestData`, client login, `ensure_permission_matrix()` where used.
- **Do not assume pytest** — it is not the project’s primary test runner.
- When changing tenancy or permissions: add isolation / deny tests.
- When changing finance: add balance / void / period regression tests.

---

## 11. Settings and environment

Configured in `church_system/settings.py` (optional `.env` load):

| Concern | Environment variable |
|---------|----------------------|
| Debug | `DJANGO_DEBUG` (defaults True if unset) |
| Secret | `DJANGO_SECRET_KEY` (required when DEBUG is False) |
| Hosts | `DJANGO_ALLOWED_HOSTS` |
| CSRF | `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Database | `DATABASE_URL` or `DB_ENGINE=postgresql` + `DB_*` |
| Redis cache | `REDIS_URL` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER` |
| Email | `EMAIL_*`, `CHURCHHUB_ASYNC_EMAIL` |
| Public URL | `CHURCHHUB_PUBLIC_URL` |
| Sentry | `SENTRY_DSN` |

Never hardcode secrets. Never commit `.env` credentials.

---

## 12. Background jobs

- Celery app: `church_system/celery.py`
- Tasks: `church_system/tasks.py` and app-level task usage (e.g. report exports)
- Tests run Celery eager automatically when `"test" in sys.argv`
- Do not assume a full Celery Beat schedule exists for every AGENTS.md scheduled job

---

## 13. What not to do

1. **Do not invent a REST/DRF API** to match `API_STANDARDS.md` alone — there is no DRF stack in requirements today.  
2. **Do not invent soft-delete columns** or call APIs that expect them.  
3. **Do not invent Division / Visitor / Inventory models** from AGENTS.md.  
4. **Do not create managers/repositories/selectors packages** without an explicit architectural task.  
5. **Do not put business rules in templates.**  
6. **Do not bypass `permission_required` / scoping helpers.**  
7. **Do not rename models, fields, URLs, or permission codenames** without approval.  
8. **Do not modify financial history silently.**  
9. **Do not treat empty nested `docs/MODULE_SPECIFICATIONS/*` stubs as requirements.**  
10. **Do not commit secrets, disable CSRF globally, or weaken tenant isolation for convenience.**

---

## 14. Style checklist

Aligned with root `CODING_STANDARDS.md` and `AGENTS.md`:

- PEP 8; Black / Ruff where the project uses them in CI  
- Meaningful names (`MemberService`-style functions, not `utils2`)  
- Prefer small functions; avoid growing mega-views further  
- Type hints where practical on new public service APIs  
- Explicit errors; never swallow exceptions silently  
- Log security-relevant and financial events without logging passwords or unnecessary PII  

---

## 15. Suggested workflow for a typical feature

```
1. Find owning app
2. Read models + services + existing views
3. Add/adjust service functions
4. Wire thin view + form + template
5. Apply permission_required + church/denomination scoping
6. Add/adjust tests
7. Update AI_CONTEXT / root docs if behavior changed
```

For schema changes: explain migration impact first; never drop columns/tables without approval.

---

## 16. Quick import cheat sheet

```python
# Permissions
from permissions.checks import permission_required, any_permission_required
from permissions.services import user_has_permission
from permissions.roles import UserRole

# Church / denomination
from church_system.church_scope import get_active_church, filter_by_church, require_church
from church_system.denomination_scope import assert_same_denomination

# Org scope
from permissions.org_scope import church_q_for_scope
from permissions.scoping import get_manageable_churches
```

When in doubt, copy an existing pattern from the same domain app rather than inventing a new architecture.
