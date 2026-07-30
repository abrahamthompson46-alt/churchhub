# ChurchHub — Technical Architecture Document

**Audience:** CTO, enterprise architects, IT evaluators  
**Alignment:** `docs/ARCHITECTURE/*`, `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md`  
**Labeling:** **Current** = implemented · **Planned** = AGENTS aspirations · **Recommended** = hardening ideas

---

## 1. System overview (Current)

ChurchHub is a **layered Django monolith** delivered as HTML over authenticated sessions. It is **not** a SPA and **does not** expose a public DRF `/api/v1/` product API today. Limited session JSON helpers exist for operational UI (permissioned and church-scoped).

```text
Browser (staff / portal / platform)
        │ HTTPS
        ▼
Nginx or cloud edge
        ▼
Gunicorn → church_system.wsgi (Django)
        │
        ├── PostgreSQL   (system of record)
        ├── Redis        (cache, sessions, Celery broker)
        └── Celery worker + Beat
```

**Presentation:** thin views → **Services** → models/ORM  
Business rules live in services; templates are presentation.

---

## 2. Logical domains (Django apps)

| Domain | Apps (examples) | Responsibility |
|--------|-----------------|----------------|
| Identity | `accounts`, `permissions` | Users, invitations, RBAC |
| Org | `organization` | Hierarchy, church history |
| People | `members` | Members, visitors, families |
| Finance | `transactions`, `giving`, `remittance`, `budgets`, `ledger`, `payroll`, `assets` | Books + stewardship |
| Church life | `meetings`, `announcements` | Events, communications |
| Experience | `dashboard`, `reports`, `portal` | Mission Control, reports, members |
| Platform | `sitecontrol` | Denominations, subscriptions, ops |

**Spec folder ≠ app name:** EVENTS → `meetings`; COMMUNICATIONS → `announcements`; FINANCE → cross-cutting (no single app).

---

## 3. Hierarchy & tenancy (Current)

```text
Platform (/platform/)  — sitecontrol operators
        │
        ▼
Denomination           — SaaS / network boundary
        │
        ▼
GC → Union → Conference → Zone → District → Church
        │
        ▼
Church-owned records (members, journals, meetings, …)
```

| Principle | Implementation |
|-----------|----------------|
| Denomination wall | Tenant isolation at SaaS boundary |
| Church as operational tenant | Day-to-day books/membership bind to church |
| Server-side scope | `church_scope` / filters on queries |
| Dual lanes | Institution apps vs platform console |
| Feature flags | Per-church capabilities (payroll, assets, …) |

---

## 4. Financial architecture (Current)

- **Books of record:** `transactions` (`Account`, `Transaction`, `TransactionLine`)  
- **`ledger`:** templates/UI that post into transactions — **not** a second GL  
- Integrity: balanced lines; approved/locked journals; void via **reversal**  
- Controls: working day, financial periods, maker-checker where configured  
- Remittance: policies, cut-off workspace, settlements  

---

## 5. Security architecture (summary)

Defense in depth: authn → authz → tenancy → CSRF → audit → secure deploy defaults.  
See [`06_SECURITY_WHITEPAPER.md`](./06_SECURITY_WHITEPAPER.md).

---

## 6. Integration surface (Current)

| Surface | Status |
|---------|--------|
| HTML staff UI | Primary |
| Member portal | Primary member channel |
| Platform UI | Operator channel |
| Session JSON helpers | Limited, authenticated |
| Public REST `/api/v1/` | **Not Current** |
| OAuth / OIDC | **Not Current** |
| Webhooks | **Not Current** (unless added later in code) |

---

## 7. Runtime topology

| Environment | Settings module pattern |
|-------------|-------------------------|
| Development | `DJANGO_ENV=development` |
| Staging | `staging` + Postgres + Redis |
| Production | `production` + validated secrets |

Deploy paths: Render blueprint · Docker Compose · self-host systemd/Nginx (`deploy/`).

---

## 8. Data & migrations

- Prefer UUID PKs on domain models  
- Schema changes via Django migrations only  
- Soft-delete (`is_deleted`) is **not** Current  
- Financial history: never silent delete/edit of posted journals  

---

## 9. Scalability notes (Current → Recommended)

**Current:** vertical scale + Postgres + Redis + Celery for async work.  
**Recommended:** read replicas for reporting, object storage for media, CDN for static, queue depth monitoring — see `docs/SCALABILITY_PLAN.md` if present.

---

## 10. References

- `docs/ARCHITECTURE/SYSTEM_ARCHITECTURE.md`  
- `docs/ARCHITECTURE/MULTI_TENANCY.md`  
- `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md`  
- `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md`
