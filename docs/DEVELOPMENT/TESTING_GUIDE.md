# ChurchHub — Testing Guide

**Audience:** Developers and AI agents writing or running tests  
**Source of truth:** `*/tests.py`, `*/tests_*.py`, `.github/workflows/ci.yml`  
**Companions:** `DEVELOPMENT_RULES.md`, `docs/SECURITY/*`, `docs/ARCHITECTURE/MULTI_TENANCY.md`

| Label | Meaning |
|-------|---------|
| **Current** | How tests work in this repo |
| **Planned** | AGENTS coverage targets |
| **Recommended** | Priority gaps to close |

---

## 1. Philosophy (Current + AGENTS)

Testing is mandatory for significant features. Prefer Django’s test runner. When fixing a bug, add a regression test.

AGENTS targets: ~80%+ overall, higher for finance, permissions, auth, members.  
**CI today** enforces coverage **fail-under=50** on the SQLite job — treat 80% as a goal, not the current gate.

---

## 2. Current test structure

### Runner

- **Primary:** `python manage.py test`  
- **Coverage:** `coverage` package (`requirements.txt`)  
- **Not primary:** pytest (no pytest config as project standard)

### Layout

| Pattern | Examples |
|---------|----------|
| `<app>/tests.py` | `members/tests.py`, `transactions/tests.py`, `permissions/tests.py`, … |
| `<app>/tests_*.py` | `transactions/tests_working_day.py`, `transactions/tests_treasury.py`, `permissions/tests_org_scope.py`, `remittance/tests_welfare_enterprise.py`, `sitecontrol/tests_denomination_phases.py` |
| Project tests | `church_system/tests_tenant_isolation.py`, `tests_church_scope.py`, `tests_denomination_isolation.py`, `tests_enterprise.py` |
| Nested | `church_system/tests/` (e.g. flash helpers) where present |

Framework: `django.test.TestCase`, often with `Client` / `RequestFactory`, `setUpTestData`, and mixins (e.g. `TenantIsolationMixin`).

### Common setup helpers

Many suites call `permissions.services.ensure_permission_matrix()` so RBAC defaults exist before permission assertions.

---

## 3. Running tests (Current)

### Local — all tests

```bash
python manage.py test
```

### Local — one app or module

```bash
python manage.py test members
python manage.py test transactions.tests_working_day
python manage.py test church_system.tests_tenant_isolation
```

### Local — with coverage (mirrors CI SQLite job)

```bash
coverage run --source='.' manage.py test --verbosity=1
coverage report --fail-under=50
```

### CI (`.github/workflows/ci.yml`)

Triggers: push/PR to `main`, `master`, `develop`.

| Job | What it does |
|-----|----------------|
| `test-sqlite` | Python 3.13; `manage.py check`; `makemigrations --check --dry-run`; coverage run + report fail-under **50** |
| `test-postgresql` | Python 3.13; Postgres 16 service; `DB_ENGINE=postgresql` + `DB_*`; full `manage.py test` |

Env in CI: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=True`.

Celery runs eager when `"test" in sys.argv` (settings).

---

## 4. Writing tests (Current conventions)

### Pattern

```python
from django.test import TestCase, Client
from django.urls import reverse
from permissions.services import ensure_permission_matrix
from permissions.roles import UserRole
# create Conference → … → Church, User with role + church
# ensure_permission_matrix()
# client.login(...)
# assert status / side effects / isolation
```

### Guidelines

1. Prefer `setUpTestData` for shared immutable fixtures.  
2. Use real service functions for finance workflows (`record_receipt`, `approve_transaction`, `void_transaction`, …).  
3. Assert **deny** paths (403 / PermissionDenied / empty queryset), not only happy paths.  
4. Use exact enum/status strings from models.  
5. Do not invent REST API tests for `/api/v1/` — it does not exist.  
6. Keep tests independent of wall-clock where WorkingDay/Period matter — open working days explicitly.

---

## 5. Tenancy testing (Current)

Key modules:

| File | Focus |
|------|-------|
| `church_system/tests_tenant_isolation.py` | Church A must not access Church B data |
| `church_system/tests_church_scope.py` | Active church / `?church=` scoping |
| `church_system/tests_denomination_isolation.py` | Denomination wall |
| `permissions/tests_org_scope.py` | Org subtree scope |
| `sitecontrol/tests_denomination_phases.py` | Denomination SaaS phases |

### What to assert

- User of church A cannot read/update church B member/transaction/asset URLs.  
- Invalid `?church=` does not fall through to unscoped access.  
- Cross-denomination operations fail when both denominations are set.  
- Platform vs institution lanes remain separated.

When adding church-owned models/views, extend isolation tests.

---

## 6. Permission testing (Current)

| File | Focus |
|------|-------|
| `permissions/tests.py` | Matrix, overrides, resolution |
| App tests | View-level `@permission_required` behavior |

### What to assert

- Unauthenticated → redirect/login.  
- Authenticated without codename → 403.  
- Deny override beats role grant.  
- Maker-checker: submitter cannot approve own item where enforced.  
- Export endpoints require export permissions.

Helper: `ensure_permission_matrix()` before role-based checks.

---

## 7. Financial integrity testing (Current)

| File | Focus |
|------|-------|
| `transactions/tests.py` | Core journals / approvals |
| `transactions/tests_working_day.py` | Working day gates |
| `transactions/tests_treasury.py` | Treasury / cash position behaviors |
| `payroll/tests.py` | Payroll → journal posting |
| `ledger/tests.py` | Category / posting helpers |
| `remittance/tests*.py` | Policies / welfare |
| `assets/tests.py` | Asset capitalization / lifecycle |
| `budgets/tests.py` | Budget UI/services over `transactions.Budget` |

### What to assert

- Unbalanced lines rejected.  
- Approve/reject/void state machine (including reversal creation).  
- Locked period / closed working day blocks posting.  
- Creator cannot approve own transaction (where coded).  
- Idempotency keys prevent duplicate posts on retry.  
- Remittance retain + remit = 100.  
- Payroll post/pay create `Transaction` rows of expected types.

---

## 8. Regression testing (Current)

When fixing a bug:

1. Reproduce with a failing test.  
2. Fix the code.  
3. Leave the test in the nearest `tests*.py`.  

High-value regression areas: church scope fallthrough, denomination wall, void/reversal, permission overrides, export gating.

---

## 9. Coverage and gaps

### Current CI gate

`coverage report --fail-under=50` (SQLite job only).

### Planned (AGENTS.md)

80%+ overall; higher for finance, permissions, authentication, membership.

### Recommended coverage improvements

| Priority | Area |
|----------|------|
| P0 | Isolation tests for every new church-owned detail/update view |
| P0 | Finance void/period/working-day edge cases when touching posting |
| P1 | Permission deny + override matrix for new codenames |
| P1 | Remittance dual-path (cutoff vs settlement) consistency |
| P1 | Platform capability matrix (impersonation, bootstrap) |
| P2 | Report export audit logging |
| P2 | Raise CI fail-under gradually toward AGENTS targets |
| P2 | Add Black/Ruff CI separately from test coverage |

Apps with thinner suites should gain tests when modified (do not expand scope just for coverage theater).

---

## 10. Troubleshooting tests

| Issue | Fix |
|-------|-----|
| Permission checks fail oddly | Call `ensure_permission_matrix()` |
| DB errors on Postgres CI only | Avoid SQLite-only assumptions; use ORM |
| Celery tasks not running | Eager mode should apply under `manage.py test` |
| Timezone flakiness | Use `django.utils.timezone`; open WorkingDay for church |
| Fixture order / FK issues | Create hierarchy Conference→…→Church before members/txns |

---

## 11. Agent checklist before claiming “done”

- [ ] Ran relevant `manage.py test <app>`  
- [ ] Added/updated tests for tenancy or permissions if those areas changed  
- [ ] Added finance regression tests if journals/approvals changed  
- [ ] Did not invent API client tests for nonexistent `/api/v1/`  
- [ ] Migrations still `--check` clean  

---

## 12. Related documents

- Rules: `DEVELOPMENT_RULES.md`  
- Tenancy: `docs/ARCHITECTURE/MULTI_TENANCY.md`  
- Authz: `docs/SECURITY/AUTHORIZATION.md`  
- Finance rules: `docs/AI_CONTEXT/BUSINESS_LOGIC.md`  
- CI definition: `.github/workflows/ci.yml`  
