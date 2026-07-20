# ChurchHub — Development Rules

**Audience:** Contributors and AI agents  
**Source of truth:** Live codebase + `AGENTS.md` / `docs/AI_CONTEXT/CODING_GUIDE.md`  
**Companions:** `SETUP_GUIDE.md`, `TESTING_GUIDE.md`, root `CODING_STANDARDS.md`, `DEVELOPMENT_WORKFLOW.md`

| Label | Meaning |
|-------|---------|
| **Current** | How this repo works today |
| **Planned** | AGENTS / standards aspirations |
| **Recommended** | Process improvements |

---

## 1. Mission

Every change should leave ChurchHub more correct, secure, and maintainable. Prefer incremental improvement over rewrites. Never invent schema, APIs, or business rules.

Before coding: read `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md`, `CODING_GUIDE.md`, and `BUSINESS_LOGIC.md`.

---

## 2. Project coding standards (Current)

Aligned with root `CODING_STANDARDS.md` and practice in the tree:

| Topic | Rule |
|-------|------|
| Language | Python 3.13+ (CI uses 3.13; README states Django 6+) |
| Style | PEP 8; meaningful names; small focused functions |
| Types | Type hints where practical on new public service APIs |
| Views | Prefer thin; call services |
| Templates | Presentation only — no business rules |
| Secrets | Environment / SiteSettings — never commit `.env` |
| Dependencies | Prefer mature packages; justify new ones |

### Planned (CODING_STANDARDS / AGENTS)

Black formatting and Ruff linting as mandatory CI gates.

### Recommended

Add format/lint CI when the team is ready; until then match surrounding file style.

---

## 3. Directory structure (Current)

```text
ChurchHub/
  manage.py
  requirements.txt
  .env.example
  church_system/          # settings, urls, celery, church_scope, denomination_scope
  accounts/ … sitecontrol/  # domain apps
  admin_custom/
  templates/
  static/
  docs/
  scripts/                # render_build.sh, render_start.sh
  docker-entrypoint.sh
  Dockerfile
  docker-compose.yml
  render.yaml
  .github/workflows/ci.yml
```

### Typical app layout

Present: `models.py`, `views.py`, `urls.py`, `forms.py`, `services.py`, `admin.py`, `tests.py` / `tests_*.py`, `migrations/`.

**Absent project-wide:** `managers.py`, `repositories/`, `selectors/`, `api/` packages, `services/` packages (use flat `services.py` or named siblings like `welfare_services.py`).

Thin façade apps: `budgets`, `giving`, `portal` (see SYSTEM_OVERVIEW).

---

## 4. Naming conventions (Current)

| Kind | Convention | Examples |
|------|------------|----------|
| Apps | lowercase domain | `members`, `transactions` |
| Models | PascalCase | `Member`, `Transaction` |
| Services | verb phrases | `create_member`, `approve_transaction` |
| Permissions | snake codenames | `manage_members`, `void_transactions` |
| URL names | `namespace:name` | `members:detail` |
| Roles | constants in `UserRole` | `TREASURY`, `LOCAL_PASTOR` |

Avoid vague names (`utils2`, `helper`, `misc`).

---

## 5. Service layer usage (Current)

```text
View / form → permissions + church_scope → services.py → models
```

| Do | Don't |
|----|-------|
| Put workflows in services | Duplicate balance/transfer rules in views |
| Raise domain exceptions from services | Swallow finance errors silently |
| Reuse existing service entry points | Invent parallel “v2” services without need |
| Keep `clean()`/`save()` light | Put multi-step workflows only in models |

See `docs/AI_CONTEXT/CODING_GUIDE.md` for import cheat sheets.

### Planned

Managers / repositories / selectors layers (AGENTS). Introduce only with explicit architectural approval.

---

## 6. Permission and tenancy requirements (Current)

Every new feature that touches church-owned data must:

1. Authenticate (`@login_required` or platform decorators).  
2. Authorize (`@permission_required` / `can_*` / platform capabilities).  
3. Scope querysets (`filter_by_church`, `church_q_for_scope`, denomination asserts).  
4. Prefer fetch-from-scoped-queryset over load-by-PK-then-check.

Platform features live under `/platform/` with `is_platform_user` + capabilities.

Details: `docs/SECURITY/AUTHORIZATION.md`, `docs/ARCHITECTURE/MULTI_TENANCY.md`.

---

## 7. Financial safety rules (Current)

Non-negotiable:

1. Journal lines must balance (sum = 0).  
2. Use `transactions.services` for approve / reject / void — no silent edits to locked/posted rows.  
3. Respect WorkingDay and FinancialPeriod gates.  
4. Keep account church = transaction church.  
5. Remittance retain% + remit% = 100.  
6. Payroll/assets/remittance post through services into `transactions`.  
7. Write financial audit trails via existing helpers/models.  
8. Use idempotency helpers for retriable posts where available.

Details: `docs/AI_CONTEXT/BUSINESS_LOGIC.md`, `docs/SECURITY/AUDIT_COMPLIANCE.md`.

---

## 8. Migration guidelines (Current)

Follow `AGENTS.md` migration policy:

| Do | Don't |
|----|-------|
| Explain why before generating | Invent fields in docs without migrations |
| Prefer additive changes | Drop columns/tables without approval |
| Keep migration history | Delete or rewrite old migrations |
| Include data backfills when needed | Silently discard historical data |
| Update `docs/DATABASE/*` when schema lands | Assume soft-delete columns exist |

See `docs/DATABASE/MIGRATION_HISTORY.md`.

CI verifies: `python manage.py makemigrations --check --dry-run`.

---

## 9. Git workflow recommendations

### Current / AGENTS recommendation

```text
main
  └── develop
        └── feature/<name>
        └── release/<version>
        └── hotfix/<issue>
```

Commit messages: clear, conventional style preferred  
(`feat(members): …`, `fix(finance): …`, `docs(api): …`).

### Recommended PR checklist

- [ ] Purpose and summary  
- [ ] Files / apps touched  
- [ ] DB migrations noted  
- [ ] Tests run (`manage.py test` relevant apps)  
- [ ] Tenancy / permission impact considered  
- [ ] Finance impact considered  
- [ ] Docs updated if behavior changed  
- [ ] No secrets committed  

Do not commit unless the user/process asks. Do not force-push shared branches.

---

## 10. Code review checklist

Review for:

| Area | Questions |
|------|-----------|
| Correctness | Does it match existing services and enums? |
| Security | Authz + tenancy on every new path? |
| Finance | No silent journal mutation? |
| Maintainability | Logic in services? Names clear? |
| Tests | Deny cases / balance / isolation covered? |
| Docs | AI_CONTEXT / SECURITY / DATABASE updated if needed? |
| Compatibility | No casual renames of models/URLs/permissions? |

Reject unexplained large rewrites and invented schema.

---

## 11. Tooling reality vs planned

| Tool | Current in repo |
|------|-----------------|
| Tests | `manage.py test` + `coverage` in CI |
| pytest | Not primary |
| Black / Ruff | Documented in standards; **not** in CI workflow today |
| DRF / OpenAPI | Not present |
| Celery | Configured; Docker Compose includes worker |

---

## 12. Related documents

- `docs/AI_CONTEXT/CODING_GUIDE.md`  
- `SETUP_GUIDE.md`, `TESTING_GUIDE.md`, `DEPLOYMENT_NOTES.md`  
- `AGENTS.md` § AI Workflow / Git / Migrations  
