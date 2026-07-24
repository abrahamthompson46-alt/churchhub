# ChurchHub — Operations Manual (RC1)

**Version:** `2.0.0-rc1`  
**Date:** 22 July 2026  
**Audience:** Platform operators, denomination admins, church staff (treasurers, secretaries, pastors)  
**Companion:** `PRODUCTION_RUNBOOK.md` (engineering incidents), `UAT_TEST_CASES.md` (acceptance), `OPERATIONS_RUNBOOK.md` (legacy technical runbook)

---

## Part A — Platform operations

### A.1 Platform roles

| Role | Capabilities |
|------|----------------|
| **OWNER** | Full platform; settings; impersonation |
| **SECURITY** | Security settings; audit; impersonation |
| **BILLING** | Tenant billing views |
| **SUPPORT** | Limited tenant support |
| **READONLY** | View-only platform |

Access: `/platform/` after MFA (when required).

### A.2 Tenant lifecycle

1. **Application** — Public `/apply/` submission.  
2. **Review** — Platform approves in site control.  
3. **Provision** — `tenant_provision` creates hierarchy seed.  
4. **Onboard church** — Denomination admin uses organization church onboard.  
5. **Invite users** — Church admin invites treasurer, secretary, pastor.  
6. **MFA** — Treasurers and super admins enroll TOTP before finance work.  
7. **Go-live** — Open working day; begin live postings.

### A.3 Site settings (platform)

| Area | Path | Notes |
|------|------|-------|
| General | `/platform/` settings | Maintenance mode, session timeout |
| Security | security settings | MFA flag, lockout thresholds |
| Email | email settings | SMTP for invites/resets |
| Branding | branding settings | Logos, labels |

**Maintenance mode:** Only platform users can sign in when enabled.

### A.4 Impersonation policy

- Use only for support with ticket reference.  
- Start from platform tenant user list; end session when done.  
- MFA is **not** forced on the impersonated user (by design).  
- All actions are attributable to the impersonated account — document carefully.

### A.5 Backups & restore

| Task | How often | Command / location |
|------|-----------|-------------------|
| Automated DB backup | Daily (Beat) | `backup_database_task` |
| Manual backup | Before major change | `python manage.py backup_database` |
| Provider snapshot | Per host policy | Render/Postgres console |
| Restore drill | Before pilot + quarterly | Restore to staging; verify login + one txn |

**Restore is destructive** — practice on staging only until runbook signed.

---

## Part B — Institution administration

### B.1 Role hierarchy (summary)

Tree admins (conference → district): manage org nodes and users in scope.  
Local roles (pastor, secretary, treasury, board, member): bound to a home church.

Use **Permissions → Matrix** to see effective capabilities. Overrides are exception-only.

### B.2 Church context

Users with multiple churches use **Switch church** on the dashboard. All lists and postings use the **active church** in session.

### B.3 User management

1. Admin opens **Invite user**.  
2. Assign role + church (if required).  
3. User accepts email link, sets password.  
4. Privileged users complete MFA enrollment on first login.

### B.4 Permissions overrides

- Grant only missing capabilities; document reason.  
- Review overrides quarterly.  
- Cannot view effective permissions for users outside your management scope.

---

## Part C — Church staff workflows

### C.1 Secretary — weekly rhythm

| Task | Module | Notes |
|------|--------|-------|
| Add/update members | Members | Verify church context |
| Record transfers | Members → Transfers | Complete workflow |
| Baptism register | Members → Baptism | As events occur |
| Schedule meetings | Meetings | Minutes approval path |
| Draft announcements | Announcements | Awaits approver |

### C.2 Treasurer — weekly rhythm

| Task | Module | Notes |
|------|--------|-------|
| Open working day | Transactions | Required before posting |
| Record receipts/expenses | Transactions | Stays PENDING until approved |
| **Do not** approve own entries | — | Maker-checker |
| Request pastor/checker approval | Pending approvals | |
| Run reports | Reports | Export audited |
| Month-end | Lock period | Coordinate with checker |

### C.3 Pastor / checker

- Approve pending transactions (not own maker entries).  
- Approve announcements and meeting minutes.  
- Review dashboard KPIs for local church.

### C.4 Member portal

- Login at `/portal/login/`.  
- View own giving statement and permitted self-service (role-dependent).

---

## Part D — Finance operations manual

### D.1 Golden rules

1. **One system of record:** `transactions` — ledger UI posts here.  
2. **Maker-checker:** Creator ≠ approver (except institution superadmin bypass — use sparingly).  
3. **Working day:** Must be open for date of posting.  
4. **Period lock:** Locked periods block new/changed postings.  
5. **Audit:** Do not attempt to edit audit log rows.

### D.2 Typical receipt flow

1. Treasurer opens working day.  
2. Record receipt → **PENDING**.  
3. Pastor/checker approves → **APPROVED** (locked).  
4. Receipt print available if permitted.  
5. Void only through reversal workflow with audit.

### D.3 Remittance & welfare

- Configure policy at church/denomination level.  
- Post settlements through remittance module.  
- Welfare disbursements follow approval path; use only internal `next` URLs after redirects hardening.

### D.4 Payroll (if enabled)

1. Maintain employees scoped to host church.  
2. Create run → **calculate** → **approve** → **post**.  
3. Module journals follow same approval rules as manual transactions.

### D.5 Assets (if enabled)

Create → submit → approve → depreciate/dispose per policy.

### D.6 Budgets (if enabled)

Plan in budgets app; actuals from transactions for variance reports.

---

## Part E — Reports & exports

1. Open **Reports** index — only permitted reports shown.  
2. Set filters (period, hierarchy).  
3. Run on screen or export CSV/Excel/PDF.  
4. Large exports: use async (`async=1`) when Celery available.  
5. Exports are logged — limit who can export sensitive reports.

**Limitation:** Some export paths rely on report access rather than format-specific export permission — restrict report visibility accordingly (`KNOWN_LIMITATIONS.md` KL-SEC-03).

---

## Part F — Notifications & email

| Event | Channel |
|-------|---------|
| In-app | Dashboard notifications bell (cached unread count) |
| Invite | Email (SMTP) |
| Password reset | Email |
| Async export ready / failed | In-app `SYSTEM` notification (email optional / Recommended) |
| Transaction approve/reject | In-app `FINANCE` |
| Announcement approve/reject | In-app `INFO` |
| Meeting minutes workflow | In-app `MEETING` |

Purge: old read notifications removed by scheduled task (90+ days configurable via command).

---

## Part G — Monitoring for church sponsors (non-engineering)

Weekly checklist:

- [ ] Treasurers completed working-day open/close  
- [ ] No unexplained pending journals > 7 days  
- [ ] Month-end period locked after close  
- [ ] No support tickets about wrong church data  
- [ ] Backups acknowledged by ops (monthly)

---

## Part H — Training quick links

| Audience | Focus modules | Duration |
|----------|---------------|----------|
| Treasurer | Finance, ledger, reports, MFA | 90 min |
| Secretary | Members, meetings, announcements | 90 min |
| Pastor | Approvals, dashboard | 45 min |
| Platform admin | Site control, tenants, impersonation | 2 hr |

Hands-on scripts: `docs/UAT_TEST_CASES.md` sections A–S.

---

## Part I — Glossary

| Term | Meaning |
|------|---------|
| Active church | Church context in user session |
| Denomination | SaaS tenant boundary (e.g. SDA, Methodist profile) |
| Maker-checker | Separation of create vs approve |
| Working day | Calendar day open for postings |
| Financial period | Month/quarter lock for books |
| Platform lane | `/platform/` — not institution SUPER_ADMIN |
| SoR | System of record (`transactions`) |

---

## Part J — Document index

| Need | Read |
|------|------|
| Deploy / incident | `PRODUCTION_RUNBOOK.md` |
| Pilot cutover | `GO_LIVE_CHECKLIST.md` |
| Security | `PRODUCTION_SECURITY_CHECKLIST.md` |
| Accepted gaps | `KNOWN_LIMITATIONS.md` |
| Release changes | `RELEASE_NOTES_RC1.md` |
