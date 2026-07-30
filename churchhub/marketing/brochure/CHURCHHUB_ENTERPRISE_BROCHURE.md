# ChurchHub Enterprise

### Unified Church Management & Financial Integrity Platform

**Brochure Edition** · Confidential for prospective partners  
**Audience:** Local churches · Conferences · Unions · Multi-denomination networks  
**Scale:** From 100 members to 100,000+ across hierarchical organizations

---

> **Icon suggestion (cover):** `bi-building` / cathedral silhouette over a soft navy–slate gradient  
> **Screenshot suggestion:** Full-bleed Mission Control dashboard (hero KPI strip + Action Queue)

---

# Cover Page

**CHURCHHUB**  
*Enterprise Church Management System*

### One platform. Complete hierarchy. Books you can trust.

Govern membership, treasury, remittance, and church life—from the local congregation to conference and union scale—with role-based security, denomination isolation, and double-entry financial integrity.

| | |
|---|---|
| **For** | Churches · Districts · Conferences · Unions · Denominational networks |
| **Built for** | Clerks · Treasurers · Pastors · Overseers · Platform operators |
| **Delivery** | Secure cloud or private deployment · Production-ready stack |

**[ Request a Demo ]** · **[ Talk to Sales ]** · **[ Pilot Program ]**

---

# 01 · Company Introduction

ChurchHub was built for a simple reality: **church administration is enterprise work**.

Membership records, tithes and offerings, remittance obligations, pastoral meetings, and multi-level governance cannot be managed with spreadsheets and disconnected tools. Financial mistakes are not “IT issues”—they are trust issues.

ChurchHub Enterprise is a purpose-built Church Management System (ChMS) that unifies:

- **People & pastoral operations**
- **Treasury & double-entry accounting**
- **Hierarchical organization** (General Conference → Union → Conference → Zone → District → Local Church)
- **Denomination-level multi-tenancy** for SaaS and network deployments
- **Auditability** that leadership, finance committees, and external reviewers can rely on

We design for institutions that expect the same discipline they would demand from a financial system—not a consumer app with a church skin.

> **Icon:** `bi-shield-check`  
> **Screenshot:** Organization hierarchy tree with conference → zone → district → church breadcrumb

---

# 02 · Product Overview

ChurchHub is a **server-rendered, enterprise-grade operations platform** delivered through a secure web application. Staff work in a role-aware control center; members engage through a dedicated member portal.

### What leaders get on day one

| Capability | Outcome |
|------------|---------|
| **Mission Control dashboard** | Role-aware KPIs, action queues, teller console, and pastoral “This Week Pulse” |
| **Membership lifecycle** | Directory, families, visitors, baptisms, transfers, leadership, spiritual gifts |
| **Church Life** | Announcements, calendar, meetings & minutes, church history chronicle |
| **Books of record** | Double-entry journals, approvals, voids via reversal, periods & working days |
| **Stewardship stack** | Receipts, expenses, budgets, giving statements, remittance & settlements |
| **Operations modules** | Payroll, fixed assets, welfare cases, reconciliation, reporting center |
| **Platform control plane** | Denominations, subscriptions, tenant applications, operator tooling |

ChurchHub scales **with your structure**—not by forcing every congregation into a flat, single-site template.

> **Icon:** `bi-diagram-3`  
> **Screenshot:** Mega-menu navigation showing Members · Finance · Reports · Church Life · Organization

---

# 03 · Key Benefits

### For the local church (100–2,000 members)
- Replace fragmented tools with one **permissioned workspace**
- Record offerings with **confirmation slips** treasurers can print and retain
- Keep pastoral follow-ups visible: visitors, birthdays, transfers, meetings
- Give members a **portal** for profile, announcements, and live/online meetings

### For the multi-church district & conference (2,000–50,000 members)
- Enforce **scope**: users only see churches they are authorized to manage
- Roll up giving and remittance obligations across the hierarchy
- Standardize approval workflows and period controls
- Operate a **teller console** for high-volume Sabbath/service processing

### For unions, networks & denominations (50,000–100,000+ members)
- Isolate tenants with a **denomination wall** (SaaS multi-tenancy)
- Provision churches with financial defaults and subscription awareness
- Run a separate **platform lane** for operators—without mixing institution data
- Deploy with **PostgreSQL, Redis, Celery, HTTPS, and health checks** for production operations

### Cross-cutting value
| Benefit | Why it matters |
|---------|----------------|
| **Financial integrity** | Debits equal credits; approved journals are locked; corrections use reversals |
| **Least privilege** | RBAC matrix with implies/overrides—not “everyone is admin” |
| **Audit trails** | Domain audit logs for finance, organization, communications, and more |
| **Operational clarity** | Dashboards that tell staff *what to do next*, not just charts |
| **Institutional memory** | Church History chronicle for milestones that outlive any single officer |

> **Icon:** `bi-graph-up-arrow`  
> **Screenshot:** Side-by-side — Teller Console (treasury) vs This Week Pulse chips (pastoral)

---

# 04 · Core Modules

| Module | Icon | What it delivers |
|--------|------|------------------|
| **Accounts & Access** | `bi-people` | Users, invitations, roles, activity logs, session security |
| **Organization** | `bi-building` | GC → Union → Conference → Zone → District → Church; onboarding & transfers |
| **Members** | `bi-person-vcard` | Profiles, families, visitors, baptisms, departments, leadership, gifts, records |
| **Meetings (Events)** | `bi-calendar-event` | Scheduling, attendance, minutes workflow, Zoom/online join links |
| **Announcements (Church Life)** | `bi-megaphone` | Draft → approve → publish; calendar of birthdays, meetings & events |
| **Church History** | `bi-journal-richtext` | Searchable institutional chronicle scoped by church or conference |
| **Transactions (GL)** | `bi-journal-check` | Chart of accounts, receipts/expenses, approvals, voids, working day, periods |
| **Ledger UI** | `bi-journal-text` | Category-driven journal posting templates into the books of record |
| **Budgets** | `bi-calculator` | Planning and variance visibility against operational spend |
| **Giving** | `bi-cash-stack` | Member giving visibility and statements (permission-controlled) |
| **Remittance** | `bi-percent` | Policies, cut-offs, settlements, welfare workflows |
| **Payroll** | `bi-currency-exchange` | Staff/pastor payroll integrated with accounting patterns |
| **Assets** | `bi-box-seam` | Fixed asset register, policy, lifecycle controls |
| **Reports** | `bi-bar-chart-line` | Report center with export formats for leadership review |
| **Dashboard** | `bi-speedometer2` | Mission Control, notifications, cut-off workspace |
| **Member Portal** | `bi-phone` | Member-facing lane: login, profile, announcements, live meetings |
| **Site Control (Platform)** | `bi-gear-wide-connected` | Denominations, subscriptions, payments, platform announcements |

> **Screenshot mosaic:** Members directory · Receipt confirmation · Remittance cut-off · Portal live meeting card

---

# 05 · Security

Security is not a feature toggle. It is the operating model.

### Identity & access
- Django session authentication with CSRF protection on mutating requests
- Role-based access control with a curated permission registry
- Hierarchy-aware scoping (church → district → conference → …)
- Platform operators use a **separate control plane**—not institution “superuser” shortcuts

### Financial controls
- Maker-aware approval paths for sensitive postings
- Period lock and working-day gates for treasury discipline
- Idempotency on critical financial POSTs to prevent duplicate submissions
- Void via **reversing entries**—never silent edits of posted history

### Data protection
- Password hashing via Django’s framework (never plaintext)
- Upload validation (type, size, extension allowlists)
- Sensitive fields and audit practices designed to avoid logging secrets or payroll PII
- Optional MFA capabilities for privileged roles (policy-configurable)

### Operational security
- Environment-based secrets (never hardcoded credentials)
- Production posture: HTTPS, secure cookies, debug disabled
- Structured logging and optional Sentry integration

> **Icon:** `bi-lock`  
> **Screenshot:** Permission matrix / override screen (Administration) with least-privilege messaging

---

# 06 · Multi-Tenant Architecture

ChurchHub supports **true institutional multi-tenancy** without collapsing every church into one shared inbox of data.

```
Platform (/platform/)
        │
        ▼
 sitecontrol.Denomination   ← SaaS / network boundary
        │
        ▼
 Conference → Zone → District → Church   ← operational hierarchy
        │
        ▼
 Church-owned records (members, journals, meetings, …)
```

### Design principles
| Principle | Implementation |
|-----------|----------------|
| **Denomination wall** | Tenant isolation at the SaaS boundary |
| **Church as operational tenant** | Day-to-day books and membership bind to local church |
| **Server-side enforcement** | Scope filters on queries—never “hide it in the UI only” |
| **Dual lanes** | Institution apps vs platform operator console |
| **Subscription awareness** | Church provisioning and plan limits for network operators |

This architecture allows a single ChurchHub deployment to serve **one conference**—or a **multi-denomination SaaS**—without rewriting the product.

> **Icon:** `bi-layers`  
> **Screenshot:** Platform denomination list + institution dashboard with active church switcher

---

# 07 · Cloud Deployment

ChurchHub is engineered for **production-grade cloud and private-cloud** operations.

### Reference stack
| Layer | Technology |
|-------|------------|
| Application | Django (`church_system`) |
| Web tier | Gunicorn · Nginx |
| Database | PostgreSQL |
| Cache / broker | Redis |
| Background jobs | Celery · Celery Beat |
| Static assets | WhiteNoise |
| Containers | Docker · Docker Compose (prod profiles available) |
| Observability | Health endpoints · optional Sentry · metrics-ready posture |

### What operations teams receive
- Environment-separated settings (development · staging · production)
- Deployment checklists and runbooks
- Supervisor/systemd unit examples for web and workers
- Backup- and recovery-oriented operational guidance

Whether you run on a major cloud provider or a denominational private data center, ChurchHub favors **predictable, auditable deployments** over opaque black boxes.

> **Icon:** `bi-cloud-check`  
> **Screenshot:** Architecture diagram (browser → Nginx → app → PostgreSQL/Redis/Celery)

---

# 08 · Mobile Support

Church leaders do not only work at desks.

### Responsive staff experience
- Bootstrap 5 interface optimized for laptop, tablet, and phone browsers
- Critical treasury and pastoral workflows remain usable on smaller screens
- Module navigation designed for touch-friendly operations

### Member portal (mobile-first engagement)
- Secure portal login (email + date-of-birth first-password pattern, then forced change)
- Announcements and profile access on the go
- Live / online meeting join details when published to the portal

### Device trust & session hygiene
- Portal device confirmation for new browsers
- Privileged session policies aligned with institutional security posture

> **Note for buyers:** ChurchHub is a **responsive web platform** (staff app + member portal). Native iOS/Android store apps can be positioned as a future roadmap item—not a current dependency for go-live.

> **Icon:** `bi-phone` + `bi-tablet`  
> **Screenshot:** Phone mockup of member portal home + tablet mockup of receipt confirmation

---

# 09 · Analytics & Insight

Decisions need numbers—but numbers need **permission boundaries**.

### Operational intelligence
- **Mission Control KPIs** — tithe, combined offering, remittance payable, action items
- **Teller Console** — live per-teller day performance for high-volume giving days
- **Church Performance leaderboards** — hierarchy-aware giving visibility for overseers
- **District roll-ups** — conference and district stewardship summaries
- **Income vs expense trends** — multi-month church finance charts
- **This Week Pulse** — pastoral care metrics (visitors, birthdays, transfers, meetings)

### Reporting center
- Catalog of membership, finance, hierarchy, and audit-oriented reports
- Export options for leadership packs and committee meetings
- Scoped results: users only export what they are authorized to see

### Why this is different from “BI dashboards”
ChurchHub analytics are **workflow-native**. Insights sit next to the buttons that clear the queue—approve a transaction, follow up a visitor, process a remittance—not in a separate tool nobody opens.

> **Icon:** `bi-pie-chart`  
> **Screenshot:** Executive KPI grid + Income vs Expense chart + Church Performance table

---

# 10 · Pricing Placeholders

*Commercial packaging is finalized per deployment model (single conference, multi-tenant SaaS, or private enterprise). The tiers below are **placeholders for sales conversations**.*

| | **Parish** | **Conference** | **Network / Enterprise** |
|---|------------|----------------|---------------------------|
| **Best for** | Single church · 100–1,500 members | Multi-church conference / district network | Unions · denominations · SaaS operators |
| **Members (guideline)** | Up to 1,500 | Up to 25,000 | 25,000–100,000+ |
| **Churches** | 1 | Up to __ | Unlimited* |
| **Core ChMS** | Included | Included | Included |
| **Full finance & remittance** | Included | Included | Included |
| **Hierarchy & roll-ups** | — | Included | Included |
| **Platform / multi-denomination** | — | Optional | Included |
| **Member portal** | Included | Included | Included |
| **Support** | Standard | Priority | Named CSM + SLA |
| **Deployment** | Cloud shared | Cloud dedicated / VPC | Cloud or private |
| **Price** | **$___ / month** | **$___ / month** | **Custom** |

\*Subject to infrastructure sizing and fair-use policies.

### Professional services (optional)
- Data migration & chart-of-accounts mapping  
- Treasurer & clerk enablement workshops  
- Custom report packs  
- Pilot go-live hypercare (30–90 days)

> **Call to action:** Contact sales for a scoped quote based on church count, monthly transaction volume, and hosting preference.

---

# 11 · Contact Page

### Let’s build the operating system for your ministry network

ChurchHub Enterprise is ready for pilots, conference rollouts, and denomination-scale deployments.

| | |
|---|---|
| **Sales** | sales@churchhub.example |
| **Partnerships** | partners@churchhub.example |
| **Support** | support@churchhub.example |
| **Web** | www.churchhub.example |
| **Demo** | Request a guided Mission Control walkthrough |

### Pilot checklist (recommended)
1. Select 1–3 churches for a 30–60 day pilot  
2. Provision hierarchy + chart of accounts  
3. Train treasurer, clerk, and pastor roles  
4. Validate remittance cut-off and approval workflows  
5. Enable member portal for a controlled group  
6. Review audit & reporting packs with leadership  

---

**ChurchHub Enterprise**  
*Secure. Hierarchical. Financially accountable.*

© ChurchHub · All rights reserved · Brochure for prospective customers

---

# Appendix A · Suggested Icon System

Use Bootstrap Icons (already in-product) for consistency across brochure, deck, and website:

| Theme | Icons |
|-------|-------|
| Trust / security | `bi-shield-check` `bi-lock` `bi-fingerprint` |
| Hierarchy | `bi-diagram-3` `bi-layers` `bi-building` |
| Finance | `bi-wallet2` `bi-journal-check` `bi-cash-stack` `bi-bank` |
| People | `bi-people` `bi-person-heart` `bi-house-heart` |
| Insight | `bi-graph-up` `bi-bar-chart-line` `bi-speedometer2` |
| Cloud | `bi-cloud-check` `bi-hdd-network` `bi-server` |
| Mobile | `bi-phone` `bi-tablet` `bi-window-desktop` |

**Brand color direction (print/web):** deep navy `#0f172a`, trust blue `#1d4ed8`, success teal `#047857`, soft slate backgrounds—avoid generic purple AI gradients.

---

# Appendix B · Screenshot Capture Guide

See also: [`SCREENSHOT_SHOT_LIST.md`](./SCREENSHOT_SHOT_LIST.md)

Priority captures for the brochure layout:

1. **Cover / hero** — Dashboard Mission Control with KPI cards  
2. **Hierarchy** — Organization tree or conference detail  
3. **Membership** — Member directory with filters  
4. **Treasury proof** — Transaction confirmation / printable slip  
5. **Teller Console** — Live day totals table  
6. **Church Life** — Announcements list + Church History search  
7. **Security** — Permissions matrix (admin)  
8. **Portal** — Member portal home on a phone-width viewport  
9. **Platform** — `/platform/` denomination or subscription screen  
10. **Analytics** — Income vs expense chart + district roll-up  

Store files in `churchhub/marketing/screenshots/` using names like:

`01-mission-control.png` · `04-receipt-confirmation.png` · `08-portal-mobile.png`
