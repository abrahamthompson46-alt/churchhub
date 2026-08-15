# ChurchHub Documentation Index

**Purpose:** Map of Phase 0 documentation for humans and AI agents.  
**Constitution:** Root [`AGENTS.md`](../../AGENTS.md) — project principles and enterprise aspirations.  
**Knowledge base:** This `docs/` tree — detailed, **code-backed** documentation.  
**Source of truth for implementation:** Live Django code. Where docs and code disagree, **code wins** until docs are updated.

| Label | Meaning |
|-------|---------|
| **Current** | Implemented today (documented from code) |
| **Planned** | `AGENTS.md` / root constitution aspirations |
| **Recommended** | Suggested next engineering steps |

---

## AI agent reading order

### Always (before any code change)

1. [`AGENTS.md`](../../AGENTS.md) — constitution (do not invent rules that contradict it without approval)  
2. [`AI_CONTEXT/SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) — what exists in the monolith  
3. [`AI_CONTEXT/CODING_GUIDE.md`](CODING_GUIDE.md) — how code is actually written  
4. [`AI_CONTEXT/BUSINESS_LOGIC.md`](BUSINESS_LOGIC.md) — domain rules as implemented  
5. Relevant module spec under `MODULE_SPECIFICATIONS/`  
6. Relevant security / architecture / API doc if touching auth, tenancy, finance, or HTTP JSON  

### By work type

| Work | Read next |
|------|-----------|
| Schema / models | [`DATABASE_MAP.md`](DATABASE_MAP.md), [`DATABASE/DATABASE_SCHEMA.md`](../DATABASE/DATABASE_SCHEMA.md), [`ENTITY_RELATIONSHIP.md`](../DATABASE/ENTITY_RELATIONSHIP.md), [`MIGRATION_HISTORY.md`](../DATABASE/MIGRATION_HISTORY.md) |
| Auth / RBAC / tenancy | [`SECURITY/AUTHENTICATION.md`](../SECURITY/AUTHENTICATION.md), [`AUTHORIZATION.md`](../SECURITY/AUTHORIZATION.md), [`ARCHITECTURE/MULTI_TENANCY.md`](../ARCHITECTURE/MULTI_TENANCY.md), [`SECURITY_AUTHORIZATION_INVARIANTS.md`](../SECURITY_AUTHORIZATION_INVARIANTS.md) (contract for P0/P1) |
| Finance | [`MODULE_SPECIFICATIONS/FINANCE/finance_spec.md`](../MODULE_SPECIFICATIONS/FINANCE/finance_spec.md) + TRANSACTIONS / LEDGER / GIVING / REMITTANCE / PAYROLL / ASSETS specs; [`AUDIT_COMPLIANCE.md`](../SECURITY/AUDIT_COMPLIANCE.md) |
| JSON / AJAX | [`API/API_CONVENTIONS.md`](../API/API_CONVENTIONS.md), [`API_REFERENCE.md`](../API/API_REFERENCE.md) — **no DRF `/api/v1/`** |
| Workflows | [`ARCHITECTURE/WORKFLOW_ARCHITECTURE.md`](../ARCHITECTURE/WORKFLOW_ARCHITECTURE.md) |
| Setup / test / deploy | [`DEVELOPMENT/SETUP_GUIDE.md`](../DEVELOPMENT/SETUP_GUIDE.md), [`TESTING_GUIDE.md`](../DEVELOPMENT/TESTING_GUIDE.md), [`DEPLOYMENT_NOTES.md`](../DEVELOPMENT/DEPLOYMENT_NOTES.md), [`DEVELOPMENT_RULES.md`](../DEVELOPMENT/DEVELOPMENT_RULES.md) |
| Residual risks | [`CURSOR_AUDIT_REPORT.md`](CURSOR_AUDIT_REPORT.md) |

### Cursor project rules

Persistent agent rules (always apply): `.cursor/rules/*.mdc` — architecture, database, Django standards, security, documentation.

---

## Document catalog (completed Phase 0)

### AI context — `docs/AI_CONTEXT/`

| File | Role |
|------|------|
| [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | Stack, apps, mounts, what is / is not implemented |
| [CODING_GUIDE.md](CODING_GUIDE.md) | Project coding conventions for agents |
| [BUSINESS_LOGIC.md](BUSINESS_LOGIC.md) | Domain rules from code |
| [DATABASE_MAP.md](DATABASE_MAP.md) | Model map / relationships overview |
| [DOCUMENT_INDEX.md](DOCUMENT_INDEX.md) | This index |
| [CURSOR_AUDIT_REPORT.md](CURSOR_AUDIT_REPORT.md) | Architectural audit / residual risks |

### Architecture — `docs/ARCHITECTURE/`

| File | Role |
|------|------|
| [SYSTEM_ARCHITECTURE.md](../ARCHITECTURE/SYSTEM_ARCHITECTURE.md) | Layered monolith architecture |
| [MULTI_TENANCY.md](../ARCHITECTURE/MULTI_TENANCY.md) | Denomination + church isolation |
| [SECURITY_ARCHITECTURE.md](../ARCHITECTURE/SECURITY_ARCHITECTURE.md) | Defense-in-depth overview |
| [WORKFLOW_ARCHITECTURE.md](../ARCHITECTURE/WORKFLOW_ARCHITECTURE.md) | Approvals / state machines |

### Database — `docs/DATABASE/`

| File | Role |
|------|------|
| [DATABASE_SCHEMA.md](../DATABASE/DATABASE_SCHEMA.md) | Schema notes from models |
| [ENTITY_RELATIONSHIP.md](../DATABASE/ENTITY_RELATIONSHIP.md) | ER relationships |
| [MIGRATION_HISTORY.md](../DATABASE/MIGRATION_HISTORY.md) | Migration inventory |

### Security — `docs/SECURITY/`

| File | Role |
|------|------|
| [AUTHENTICATION.md](../SECURITY/AUTHENTICATION.md) | Session auth, MFA stub, sessions |
| [AUTHORIZATION.md](../SECURITY/AUTHORIZATION.md) | RBAC, scope, platform capabilities |
| [AUDIT_COMPLIANCE.md](../SECURITY/AUDIT_COMPLIANCE.md) | Domain audit trails, retention gaps |

### Security contract / audit (root `docs/`)

These are the 14 August 2026 audit pack. They do **not** replace `SECURITY/*.md` Current docs.

| File | Role |
|------|------|
| [SECURITY_AUTHORIZATION_INVARIANTS.md](../SECURITY_AUTHORIZATION_INVARIANTS.md) | **Authorization contract** (MUST rules for remediation and tests) |
| [SECURITY_AUDIT_REPORT.md](../SECURITY_AUDIT_REPORT.md) | Full audit narrative / score |
| [SECURITY_FINDINGS_REGISTER.md](../SECURITY_FINDINGS_REGISTER.md) | CH-SEC-* findings |
| [SECURITY_REMEDIATION_DESIGN.md](../SECURITY_REMEDIATION_DESIGN.md) | Per-finding design |
| [SECURITY_REMEDIATION_ROADMAP.md](../SECURITY_REMEDIATION_ROADMAP.md) | P0–P3 plan |
| [SECURITY_PHASE2_ANNOUNCEMENTS_DESIGN.md](../SECURITY_PHASE2_ANNOUNCEMENTS_DESIGN.md) | Phase 2 CH-SEC-002/008 design + implementation notes |
| [SECURITY_PHASE3_FINANCIAL_DESIGN.md](../SECURITY_PHASE3_FINANCIAL_DESIGN.md) | Phase 3 financial integrity / maker-checker design + implementation contract |
| [SECURITY_PHASE4_MEDIA_TENANCY_DESIGN.md](../SECURITY_PHASE4_MEDIA_TENANCY_DESIGN.md) | Phase 4 media URL gate, unanchored tenancy, platform stats (Option A) |

### API — `docs/API/`

| File | Role |
|------|------|
| [API_CONVENTIONS.md](../API/API_CONVENTIONS.md) | Current JSON status; planned `/api/v1/` |
| [API_REFERENCE.md](../API/API_REFERENCE.md) | Live JsonResponse / AJAX endpoints only |

### Development — `docs/DEVELOPMENT/`

| File | Role |
|------|------|
| [DEVELOPMENT_RULES.md](../DEVELOPMENT/DEVELOPMENT_RULES.md) | Dev process rules |
| [SETUP_GUIDE.md](../DEVELOPMENT/SETUP_GUIDE.md) | Local setup |
| [DEPLOYMENT_NOTES.md](../DEVELOPMENT/DEPLOYMENT_NOTES.md) | Deploy notes (e.g. Render) |
| [TESTING_GUIDE.md](../DEVELOPMENT/TESTING_GUIDE.md) | How tests are run |

### Module specifications — `docs/MODULE_SPECIFICATIONS/`

| Spec | Live Django app | Notes |
|------|-----------------|-------|
| [ACCOUNTS/accounts_spec.md](../MODULE_SPECIFICATIONS/ACCOUNTS/accounts_spec.md) | `accounts` | Custom User, invites |
| [ORGANIZATION/organization_spec.md](../MODULE_SPECIFICATIONS/ORGANIZATION/organization_spec.md) | `organization` | Hierarchy |
| [PERMISSIONS/permissions_spec.md](../MODULE_SPECIFICATIONS/PERMISSIONS/permissions_spec.md) | `permissions` | Matrix + overrides |
| [MEMBERS/members_spec.md](../MODULE_SPECIFICATIONS/MEMBERS/members_spec.md) | `members` | Membership |
| [FINANCE/finance_spec.md](../MODULE_SPECIFICATIONS/FINANCE/finance_spec.md) | *(umbrella — no `finance` app)* | Points to books of record |
| [TRANSACTIONS/transactions_spec.md](../MODULE_SPECIFICATIONS/TRANSACTIONS/transactions_spec.md) | `transactions` | **Books of record** |
| [LEDGER/ledger_spec.md](../MODULE_SPECIFICATIONS/LEDGER/ledger_spec.md) | `ledger` | Templates + post UI (not a second GL) |
| [GIVING/giving_spec.md](../MODULE_SPECIFICATIONS/GIVING/giving_spec.md) | `giving` | Read-only; empty models |
| [REMITTANCE/remittance_spec.md](../MODULE_SPECIFICATIONS/REMITTANCE/remittance_spec.md) | `remittance` | Policies, settlements, welfare |
| [PAYROLL/payroll_spec.md](../MODULE_SPECIFICATIONS/PAYROLL/payroll_spec.md) | `payroll` | Runs → PAYROLL journals |
| [ASSETS/assets_spec.md](../MODULE_SPECIFICATIONS/ASSETS/assets_spec.md) | `assets` | Fixed assets / depreciation |
| [EVENTS/events_spec.md](../MODULE_SPECIFICATIONS/EVENTS/events_spec.md) | **`meetings`** | No `events` app |
| [COMMUNICATIONS/communications_spec.md](../MODULE_SPECIFICATIONS/COMMUNICATIONS/communications_spec.md) | **`announcements`** | `CommunicationsConfig` |
| [REPORTS/reports_spec.md](../MODULE_SPECIFICATIONS/REPORTS/reports_spec.md) | `reports` | Catalog + exporters |
| [SITE_CONTROL/site_control_spec.md](../MODULE_SPECIFICATIONS/SITE_CONTROL/site_control_spec.md) | `sitecontrol` | `/platform/` SaaS |

**Not a separate Phase 0 module folder (but live apps):** `budgets` (UI over `transactions.Budget`), `dashboard`, `portal`, `admin_custom`. Cross-referenced from finance / overview docs.

---

## Spec folder vs live app (do not invent)

| Spec folder name | Actual app package |
|------------------|--------------------|
| FINANCE | No app — use `transactions` + companions |
| EVENTS | `meetings` |
| COMMUNICATIONS | `announcements` |
| SITE_CONTROL | `sitecontrol` |

---

## Root markdown (constitution & legacy)

Root `*.md` files (`AGENTS.md`, `SECURITY.md`, `API_STANDARDS.md`, domain whitepapers, etc.) remain **aspirational or historical**. Prefer `docs/` for implementation detail. Do not treat root `API_STANDARDS.md` as proof that `/api/v1/` exists.

---

## Phase 0 completion checklist

| Area | Status |
|------|--------|
| AI_CONTEXT | Complete |
| ARCHITECTURE | Complete |
| DATABASE | Complete |
| SECURITY | Complete |
| API | Complete (documents absence of DRF) |
| DEVELOPMENT | Complete |
| MODULE_SPECIFICATIONS (listed above) | Complete |
| Cursor `.cursor/rules/*.mdc` | Configured |

---

## Agent hard rules (summary)

1. Code is source of truth — do not invent models, fields, APIs, roles, or workflows.  
2. Separate **Current** vs **Planned (AGENTS.md)** vs **Recommended** in docs and designs.  
3. No parallel general ledger beside `transactions`.  
4. Enforce RBAC + church/denomination scope on every church-owned query.  
5. Financial mutations only through services (balance, period, working day, void≠edit).  
6. Update docs when architecture or contracts change.  
7. Wait for approval for schema renames, destructive migrations, and new apps.  
