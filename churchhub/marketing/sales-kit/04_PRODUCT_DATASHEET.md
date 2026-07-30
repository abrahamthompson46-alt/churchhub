# ChurchHub — Product Datasheet

**Version:** Sales kit (code-aligned)  
**Product:** ChurchHub Enterprise ChMS  
**Delivery:** Web application (responsive) · Member portal · Platform console  

---

## 1. Product summary

| Item | Specification |
|------|----------------|
| Category | Church Management System (ChMS) + church treasury |
| Architecture | Server-rendered Django monolith |
| Hierarchy | GC → Union → Conference → Zone → District → Church |
| Multi-tenancy | Denomination isolation + church operational scope |
| Books of record | Double-entry `transactions` ledger |
| Auth | Django sessions · CSRF · RBAC · portal member login |
| Optional modules | Payroll, assets, budgets, ledger UI, campaigns (feature-gated) |

---

## 2. Module matrix

| Module | Included | Notes |
|--------|----------|-------|
| Dashboard / Mission Control | Yes | KPIs, Action Queue, teller, cut-off |
| Organization & church history | Yes | Hierarchy CRUD, transfers, chronicle |
| Members & visitors | Yes | Profiles, families, convert visitors |
| Meetings & attendance | Yes | Minutes workflow, live links |
| Announcements & calendar | Yes | Approve/publish |
| Transactions / treasury | Yes | Receipts, expenses, approvals, periods, reconciliation |
| Giving statements | Yes | Permission-controlled |
| Remittance & welfare | Yes* | *Feature / policy dependent |
| Budgets | Yes* | Feature-gated |
| Ledger UI | Yes* | Posts into books of record |
| Payroll | Yes* | Feature-gated |
| Fixed assets | Yes* | Feature-gated |
| Reports & exports | Yes | CSV / Excel / PDF (as implemented) |
| Permissions / invitations | Yes | Matrix, overrides, audit |
| Member portal | Yes | Announcements, profile, self-service |
| Site Control (platform) | Yes | Denominations, plans, subscriptions, imports |

---

## 3. Technical footprint

| Layer | Technology |
|-------|------------|
| Application | Python · Django (`church_system`) |
| App server | Gunicorn |
| Edge | Nginx (self-host) or platform edge (e.g. Render) |
| Database | PostgreSQL (required staging/production) |
| Cache / broker | Redis |
| Jobs | Celery · Celery Beat |
| Static | WhiteNoise / Nginx |
| Media | Local disk or S3 (`django-storages`) |
| Containers | Docker · Docker Compose |
| Observability | `/health/*`, `/metrics/`, optional Sentry |

---

## 4. Security controls (summary)

- Session authentication; login rate limiting  
- RBAC permission registry with hierarchy scope  
- Platform users vs institution users (separate lane)  
- Maker-checker paths for sensitive finance  
- Period lock / working-day gates  
- Void via reversing entries  
- Upload validation allowlists  
- MFA capabilities — **policy-configurable** (not universal by default)  
- Production validation rejects DEBUG, weak secrets, SQLite, missing Redis  

Full detail: [`06_SECURITY_WHITEPAPER.md`](./06_SECURITY_WHITEPAPER.md)

---

## 5. Browser support

Modern evergreen browsers (Chrome, Edge, Firefox, Safari). Staff UI responsive; portal mobile-first.

---

## 6. Packaging tiers (placeholder)

| Tier | Churches | Members (guideline) | Price |
|------|----------|---------------------|-------|
| Parish | 1 | ≤ ~1,500 | $___ / mo |
| Conference | Multi | ≤ ~25,000 | $___ / mo |
| Network / Enterprise | Unlimited* | 25k–100k+ | Custom |

\*Subject to infrastructure sizing and fair use.

---

## 7. Compliance posture

Designed for auditability (domain audit logs, financial immutability patterns). Formal certifications (e.g. SOC 2) — **state only if attained**; otherwise list as roadmap with legal review.

---

## 8. Related documents

Executive summary · Architecture · Security whitepaper · Deployment guide · Administrator / user manuals  

**Sales:** sales@churchhub.example
