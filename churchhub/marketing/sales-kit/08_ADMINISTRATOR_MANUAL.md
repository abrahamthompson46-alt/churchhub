# ChurchHub — Administrator Manual

**Audience:** Conference / church system administrators, secretaries with access rights  
**Scope:** Day-2 administration after deploy (not platform SaaS ops — see §8)

---

## 1. Roles at a glance

| Role | Typical duties |
|------|----------------|
| Institution admin | Users, invitations, org structure, feature-aware setup |
| Secretary / clerk | Members, visitors, transfers, announcements |
| Treasurer | Receipts, expenses, approvals, giving, remittance |
| Pastor | Visitors, meetings, pastoral Action Queue |
| Overseer | Cross-church visibility within scope |

Permissions are **role-matrix driven**. Never share one “god” login.

---

## 2. First-week admin checklist

1. Sign in at `/accounts/login/` → Mission Control  
2. Confirm **active church** context (church switcher)  
3. Invite staff (`Administration` / users) — least privilege  
4. Verify hierarchy units (conference → churches)  
5. Confirm chart of accounts / posting categories with treasury  
6. Open working day / period per finance policy  
7. Publish a test announcement; verify portal visibility if used  
8. Walk one receipt → confirmation → register  

---

## 3. User & access management

| Task | Where |
|------|-------|
| Directory of users | Users & Access |
| Invite | Invite User (email invitation acceptance flow) |
| Roles / matrix | Permissions → Role Matrix |
| Exceptions | Permission Overrides (use sparingly; audit) |
| Effective access | Effective User Permissions view |
| Activity | User Activity Log / Permission Audit Log |

**Rules**

- Prefer roles over one-off overrides  
- Revoke promptly on role change  
- Platform operators are **not** managed as church superusers  

---

## 4. Organization administration

- Maintain GC → … → Church records; avoid duplicate churches  
- Use church onboarding wizard when adding congregations  
- Church transfer between districts: use formal transfer flow (preserves history)  
- Church History: institutional chronicle (searchable; permissioned)  

---

## 5. Membership administration

- Member directory: create/edit with duplicate caution (name/DOB/contact)  
- Families, departments, leadership assignments  
- Transfers: register + approval path as configured  
- Visitors: assign follow-up; convert to member when ready  
- Lookups / occupations: configure lists under member configuration (if permitted)  

---

## 6. Communications & meetings

- Announcements: draft → approve → publish (don’t bypass approval if policy requires)  
- Calendar: upcoming meetings, birthdays, announcements  
- Meetings: agenda, minutes approval queue, attendance  
- Portal submissions (prayer/testimony): staff review queue when enabled  

---

## 7. Finance administration (with treasurer)

Admins often enable process; treasurers execute. Align on:

- Who may record receipts/expenses  
- Who approves (maker-checker)  
- Working-day open/close ownership  
- Remittance policy owners  
- Report export permissions  

Never instruct staff to edit posted journals in place — use void/reversal procedures.

---

## 8. Platform administration (operators only)

If you are a **platform** operator (`/platform/`):

| Area | Tasks |
|------|-------|
| Denominations | Create, terminology, branding, billing |
| Applications | Review public church applications |
| Tenants | Provision, feature registry, subscriptions |
| Imports | Member / transaction import hubs |
| Settings | Email, security policy, registration controls |
| Health | Tenant health, operations, audit log |

Institution admins should not need Django `/admin/` — treat it as break-glass.

---

## 9. Troubleshooting

| Symptom | Check |
|---------|-------|
| User sees wrong church data | Active church + role scope |
| Missing module | Feature registry for that church |
| Portal email links fail | `CHURCHHUB_PUBLIC_URL` |
| Can’t approve finance | Pending queue permission + maker ≠ checker policy |
| Login lockout | Rate limit / wait or admin unlock process |

---

## 10. Related guides

- User manual (role how-tos): [`09_USER_MANUAL.md`](./09_USER_MANUAL.md)  
- Quick-start: [`10_QUICK_START_GUIDE.md`](./10_QUICK_START_GUIDE.md)  
- Security: [`06_SECURITY_WHITEPAPER.md`](./06_SECURITY_WHITEPAPER.md)
