# ChurchHub — UAT Plan (Phase 6)

**Type:** User Acceptance Testing plan for pilot readiness  
**Date:** 22 July 2026  
**Candidate:** Current codebase (production candidate)  
**Constraint:** No new features unless a **critical** defect blocks a must-have pilot workflow  
**Companions:** `UAT_TEST_CASES.md`, `PILOT_DEPLOYMENT_PLAN.md`, `GO_LIVE_CHECKLIST.md`, `SECURITY_VALIDATION_REPORT.md`

---

## 1. Objectives

1. Validate every core business workflow with **representative roles**.  
2. Confirm **church** and **denomination** isolation under real navigation.  
3. Confirm **financial controls** (double-entry, maker-checker, periods, working days, audit).  
4. Confirm **ops** paths needed for a time-boxed pilot (backup, monitoring, email, jobs).  
5. Produce a clear **Go / No-Go** for pilot (not full enterprise scale-out).

---

## 2. Scope

### In scope

| Domain | Modules / surfaces |
|--------|-------------------|
| Identity | Login, logout, invite, password reset, MFA, portal login |
| Onboarding | Public apply, platform tenant provision, church create/onboard |
| Membership | Member CRUD, transfers, baptism register/report |
| Finance | Receipts, expenses, approve/reject/void, remittance, budgets |
| Books | Ledger UI posting through transaction SoR |
| Payroll | Employees, runs (calculate → approve → post) |
| Assets | Lifecycle, approve, dispose, depreciation |
| Community | Meetings/minutes, announcements |
| Insights | Reports (run + export), giving statements |
| Governance | Permissions matrix/overrides, site control (platform) |
| Tenancy | Church switch, denomination context, isolation negative tests |
| Ops | Health, metrics auth, notifications, email, backup smoke |

### Out of scope (pilot)

- New product features or UX redesign  
- Full SOC2/ISO certification evidence packs  
- Absolute session timeout / soft-delete (Planned items)  
- Closing Medium security backlog unless it blocks pilot (see Security report)

---

## 3. Test roles (personas)

Map UAT personas to **actual** platform capabilities / `UserRole` values.

| UAT persona | System mapping | Primary lanes |
|-------------|----------------|---------------|
| **Platform Admin** | Platform `OWNER` (and spot-check `SECURITY`) | `/platform/`, settings, tenants, impersonation |
| **Denomination Admin** | Institution `SUPER_ADMIN` or `GENERAL_OVERSEER` bound to one denomination | Hierarchy + multi-church within denom |
| **Conference** | `CONFERENCE_ADMIN` | Conference-scoped org + visibility |
| **District** | `DISTRICT_PASTOR` | District churches |
| **Church Admin** | `SUPER_ADMIN` at local church **or** tree admin with single-church focus | Local ops oversight |
| **Treasurer** | `TREASURY` | Finance, remittance, MFA required |
| **Secretary** | `SECRETARY` | Members, meetings, announcements |
| **Pastor** | `LOCAL_PASTOR` | Pastoral views, approvals where permitted |
| **Member** | `MEMBER` + portal user | Portal / limited self-service |

**Pilot rule:** Platform users never use institution `SUPER_ADMIN` as a substitute for `/platform/` capabilities.

---

## 4. Environments

| Environment | Purpose |
|-------------|---------|
| **UAT / staging** | Full UAT execution; production-like (`DEBUG=False`, Redis, Postgres, SMTP sandbox) |
| **Pilot** | Limited real churches after Go; production settings |

Seed data: two denominations (or one primary + one isolation foil), ≥2 churches per denom where isolation is tested, open working day + unlocked period for finance scripts.

---

## 5. Acceptance criteria (by module)

A module is **Accepted** when:

1. All **P0** test cases in `UAT_TEST_CASES.md` for that module pass.  
2. No open **Critical** or **Blocker** defects for that module.  
3. Role visibility matches the permission matrix (no cross-church leakage).  
4. Happy path completable by a non-developer tester with the runbook.

| Module | Acceptance summary |
|--------|-------------------|
| User onboarding | Invite → accept → login → (MFA if privileged) works; lockout behaves |
| Church onboarding | Apply/provision/create/onboard yields usable church context |
| Membership | CRUD within church; other church 403/404 |
| Transfers | Create → track → complete without cross-church PII leak |
| Baptism / profession | Register/report updates visible to authorized roles only |
| Giving | Index/statement scoped; export/auth consistent with permissions |
| Finance | Receipt/expense → pending → approve by checker → audit row |
| Ledger | Entry posts balanced journal via SoR; period/working-day enforced |
| Remittance | Policy/settlement/post path completes with audit |
| Payroll | Run calculate → approve → post; journals respect maker-checker |
| Assets | Create → submit → approve → dispose/depreciate as designed |
| Meetings | Create, minutes approval path, attendance where enabled |
| Reports | Authorized run; export produces file; unauthorized denied or scoped |
| Announcements | Create → pending → approve → visibility correct |
| Permissions | Matrix view; overrides apply; no IDOR on effective permissions |
| Site Control | Settings/email/security; tenant tools; metrics not public |
| Multi-tenant | Church + denomination isolation negative cases pass |
| Ops readiness | Health ready; backup command/task verified; email delivers |

---

## 6. Defect severity

| Severity | Definition | Pilot impact |
|----------|------------|--------------|
| **Blocker** | Cannot complete a P0 workflow | **No-Go** until fixed |
| **Critical** | Data leak, wrong church books, privilege escalation, money integrity break | **No-Go** |
| **Major** | Workaround exists; wrong UX or non-core path broken | Conditional Go with waiver |
| **Minor** | Cosmetic / docs / rare edge | Track post-pilot |
| **Enhancement** | New feature ask | Out of Phase 6 scope |

---

## 7. Execution plan

| Phase | Activity | Owner |
|-------|----------|-------|
| **U0** | Staging deploy + seed personas + MFA enroll for Treasurer/Platform | Ops + Eng |
| **U1** | Identity, onboarding, site control smoke | Platform Admin |
| **U2** | Membership, transfers, baptism, meetings, announcements | Secretary + Pastor |
| **U3** | Finance, ledger, remittance, payroll, assets, budgets | Treasurer + Pastor (checker) |
| **U4** | Reports, giving, exports | Treasurer + Church Admin |
| **U5** | Isolation negative suite (church + denomination) | Platform Admin + second denom user |
| **U6** | Ops: email, notifications, backup, health, scheduled jobs | Ops |
| **U7** | Sign-off workshop → update Go-Live Checklist | All |

**Suggested calendar:** 5–8 working days for a single denomination pilot; add 2 days if two denominations are in scope.

---

## 8. Entry / exit criteria

### Entry

- [ ] Staging matches release candidate commit  
- [ ] Phase 5 security Conditional Go acknowledged  
- [ ] Redis, Postgres, SMTP sandbox configured  
- [ ] Seed churches and personas documented  
- [ ] `UAT_TEST_CASES.md` assigned to testers  

### Exit (UAT complete)

- [ ] All P0 cases executed (Pass / Fail / Blocked recorded)  
- [ ] Zero open Blockers/Criticals **or** explicit deferred with mitigation  
- [ ] Pilot readiness score recorded in this plan’s sign-off  
- [ ] `GO_LIVE_CHECKLIST.md` ready for pilot cutover  

---

## 9. Traceability

| Artifact | Role |
|----------|------|
| `UAT_TEST_CASES.md` | Executable cases (IDs UAT-*) |
| `PILOT_DEPLOYMENT_PLAN.md` | Who/when/how for pilot |
| `GO_LIVE_CHECKLIST.md` | Cutover gates |
| `PRODUCTION_SECURITY_CHECKLIST.md` | Security gate |
| `DEPLOYMENT_CHECKLIST.md` | Infrastructure gate |
| Automated tests | Regression net (isolation, MFA, finance) — does **not** replace UAT |

---

## 10. Pilot readiness (planning baseline)

| Metric | Baseline (pre-execution) |
|--------|--------------------------|
| **Pilot readiness score** | **8.0 / 10** (code + prior phases; subject to UAT results) |
| **Recommendation** | **Conditional Go for limited pilot** after UAT P0 pass + ops checklist |

Update score and module Accepted/Attention lists in the Phase 6 return summary after UAT execution. Documentation in this phase defines the bar; live Pass/Fail is recorded in test-case results columns.
