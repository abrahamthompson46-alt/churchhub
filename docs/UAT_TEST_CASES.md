# ChurchHub — UAT Test Cases

**Date:** 22 July 2026  
**Companion:** `UAT_PLAN.md`  
**How to use:** Copy Result columns into your tracker (Pass / Fail / Blocked / N/A). Record build SHA and environment.

**Priority:** P0 = must pass for pilot · P1 = should pass · P2 = nice / edge

---

## Result log header

| Field | Value |
|-------|-------|
| Environment | |
| Build / commit | |
| Tester | |
| Dates | |
| Denominations in seed | |
| Churches in seed | |

---

## A. Identity & user onboarding

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-ID-01 | P0 | Platform Admin | Login `/accounts/login/` with MFA enrolled | Dashboard or `/platform/` reachable after MFA | | |
| UAT-ID-02 | P0 | Treasurer | Login without MFA enrolled | Redirected to MFA enroll; cannot use finance until enrolled | | |
| UAT-ID-03 | P0 | Secretary | Login (MFA not required) | Lands on institution dashboard | | |
| UAT-ID-04 | P0 | Church Admin | Invite user (`accounts:invite_user`) → accept token → set password | New user can log in with assigned role/church | | |
| UAT-ID-05 | P0 | Any | Logout | Session ended; protected URLs redirect to login | | |
| UAT-ID-06 | P0 | Any | Password reset request → email → set new password | Reset works; old password fails | | |
| UAT-ID-07 | P1 | Any | Fail login N times | Lockout / rate-limit message for configured window | | |
| UAT-ID-08 | P1 | Member | Portal login `/portal/login/` | Portal home; cannot open treasury screens | | |

**Module accept:** All P0 Pass.

---

## B. Church onboarding & organization

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-ORG-01 | P0 | Platform Admin | Review `/apply/` application → approve / `tenant_provision` | Tenant/church appears; usable hierarchy | | |
| UAT-ORG-02 | P0 | Denomination Admin | Create church (`organization:church_create`) + onboard | Church selectable; defaults seeded (COA/assets as designed) | | |
| UAT-ORG-03 | P0 | Conference | View churches under conference | Only conference subtree visible | | |
| UAT-ORG-04 | P0 | District | View churches under district | Only district churches | | |
| UAT-ORG-05 | P1 | Pastor / Secretary | `dashboard:switch_church` among allowed churches | Context switches; data follows active church | | |
| UAT-ORG-06 | P0 | Treasurer (Church A) | Attempt switch/open Church B URL | Denied or church not in switcher | | |

**Module accept:** All P0 Pass.

---

## C. Membership management

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-MEM-01 | P0 | Secretary | Add member in Church A | Appears on Church A list | | |
| UAT-MEM-02 | P0 | Secretary | Edit + view detail | Changes persist; audit if applicable | | |
| UAT-MEM-03 | P0 | Secretary Church A | Open Church B member detail URL | **403 or 404** | | |
| UAT-MEM-04 | P0 | Pastor | View member list for home church | Sees local members only | | |
| UAT-MEM-05 | P1 | Member | Portal view of own profile (if enabled) | Own data only | | |
| UAT-MEM-06 | P1 | Secretary | Soft status change (inactive/transfer pending) | Status reflected; list filters work | | |

**Module accept:** All P0 Pass.

---

## D. Transfers

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-TRF-01 | P0 | Secretary | Create transfer (`members:transfer_create`) | Transfer record created; visible in list | | |
| UAT-TRF-02 | P0 | Secretary / Admin | Progress transfer to completion | Member church/status updated per design | | |
| UAT-TRF-03 | P0 | Other church user | Open transfer detail by guessing UUID | **403/404** | | |
| UAT-TRF-04 | P1 | Conference | Visibility of transfers in scope | Only in-scope churches | | |

**Module accept:** All P0 Pass.

---

## E. Baptism / profession updates

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-BAP-01 | P0 | Secretary / Pastor | Open baptism register (`members:baptism_register`) | Form/report loads for active church | | |
| UAT-BAP-02 | P0 | Secretary | Record baptism / profession update | Member spiritual status fields updated | | |
| UAT-BAP-03 | P1 | Unauthorized role | Attempt register URL | Permission denied | | |
| UAT-BAP-04 | P1 | Secretary | Export/report if available | Scoped to church; permission respected | | |

**Module accept:** All P0 Pass.

---

## F. Giving

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-GIV-01 | P0 | Treasurer | Open giving index | Church-scoped giving data | | |
| UAT-GIV-02 | P0 | Treasurer | Member statement for local member | Correct totals vs postings | | |
| UAT-GIV-03 | P0 | Treasurer Church A | Statement for Church B member id | **403/404** | | |
| UAT-GIV-04 | P1 | Treasurer | Export giving (if UI offers) | Requires export/manage finance permission | | |

**Module accept:** All P0 Pass.

---

## G. Finance (transactions)

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-FIN-01 | P0 | Treasurer | Open working day | Working day open for church/date | | |
| UAT-FIN-02 | P0 | Treasurer | Record receipt | PENDING journal; balanced lines | | |
| UAT-FIN-03 | P0 | Treasurer | Attempt to approve **own** receipt | **Rejected** (maker-checker) | | |
| UAT-FIN-04 | P0 | Pastor / checker | Approve receipt | APPROVED + locked; audit APPROVE | | |
| UAT-FIN-05 | P0 | Treasurer | Record expense → approve by other | Same maker-checker rules | | |
| UAT-FIN-06 | P0 | Checker | Reject pending | Status rejected; audit | | |
| UAT-FIN-07 | P0 | Authorized | Void approved (reversal path) | Reversal journal + VOID audit; original not silently edited | | |
| UAT-FIN-08 | P0 | Treasurer Church A | Open Church B transaction detail | **403/404** | | |
| UAT-FIN-09 | P1 | Treasurer | Print receipt | Printable view for approved/allowed txn | | |
| UAT-FIN-10 | P1 | Bulk approve | Bulk approve where permitted | Only eligible txns; no self-approve | | |

**Module accept:** All P0 Pass.

---

## H. Ledger

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-LED-01 | P0 | Treasurer | View chart / accounts for church | Local COA only | | |
| UAT-LED-02 | P0 | Treasurer | Create entry → confirm | Posts via transaction SoR; balanced | | |
| UAT-LED-03 | P0 | Treasurer | Post with **no** open working day | Blocked with clear message | | |
| UAT-LED-04 | P0 | Admin | Lock financial period → attempt post | Blocked | | |
| UAT-LED-05 | P1 | Unlock period (authorized) | Unlock → post succeeds | Period controls work both ways | | |

**Module accept:** All P0 Pass.

---

## I. Remittance

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-REM-01 | P0 | Treasurer / Admin | Configure or view remittance policy | Policy scoped correctly | | |
| UAT-REM-02 | P0 | Treasurer | Record remittance / settlement post | Journal created; status correct | | |
| UAT-REM-03 | P0 | Checker | Approve if pending | Maker-checker honored | | |
| UAT-REM-04 | P1 | Welfare disburse (if used) | Disburse path | Audit rows; no open redirect on `next` | | |

**Module accept:** All P0 Pass.

---

## J. Payroll

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-PAY-01 | P0 | Treasurer / HR-capable | Create employee at Church A | Visible only in Church A list | | |
| UAT-PAY-02 | P0 | Treasurer | Create payroll run → calculate | Totals computed | | |
| UAT-PAY-03 | P0 | Approver | Approve run | Status advances | | |
| UAT-PAY-04 | P0 | Poster | Post run | Module journals created; checker rules apply | | |
| UAT-PAY-05 | P0 | Church A user | View Church B employee | Not listed / 403 | | |
| UAT-PAY-06 | P1 | Bank export | Export payment file | Permission required | | |

**Module accept:** All P0 Pass.

---

## K. Assets

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-AST-01 | P0 | Treasurer / Admin | Create asset Church A | Appears in Church A register | | |
| UAT-AST-02 | P0 | Workflow | Submit → approve | Status transitions | | |
| UAT-AST-03 | P0 | Church A | Open Church B asset URL | **403/404** | | |
| UAT-AST-04 | P1 | Dispose / depreciate | Run dispose or depreciation | Journals/audit as designed | | |

**Module accept:** All P0 Pass.

---

## L. Meetings

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-MTG-01 | P0 | Secretary | Create meeting | Meeting listed for church | | |
| UAT-MTG-02 | P0 | Secretary | Capture minutes → submit for approval | Pending visible to approver | | |
| UAT-MTG-03 | P0 | Pastor / Admin | Approve minutes | Approved; export if permitted | | |
| UAT-MTG-04 | P1 | Attendance | Record attendance | Scoped to meeting/church | | |

**Module accept:** All P0 Pass.

---

## M. Reports

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-RPT-01 | P0 | Treasurer | Open reports index | Only permitted reports listed | | |
| UAT-RPT-02 | P0 | Treasurer | Run a core financial report | Rows match known seed postings | | |
| UAT-RPT-03 | P0 | Treasurer | Export CSV/Excel/PDF | File downloads; access audited | | |
| UAT-RPT-04 | P0 | Member / low privilege | Open restricted report key | **403** | | |
| UAT-RPT-05 | P1 | Async export | Queue export job → download | Job owned by requester only | | |
| UAT-RPT-06 | P1 | Cross-church filters | Attempt other church in hierarchy filter | Denied or empty per scope | | |

**Known attention:** Format-specific `can_export_reports_*` may not gate every export path — record actual behavior; Major if viewers can export sensitive data against policy.

**Module accept:** All P0 Pass; note export-permission nuance under Outstanding.

---

## N. Announcements

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-ANN-01 | P0 | Secretary | Create announcement | Pending or draft per rules | | |
| UAT-ANN-02 | P0 | Approver | Approve from pending | Visible to intended audience | | |
| UAT-ANN-03 | P0 | Other church | Should not see private/local announcement | Isolation holds | | |
| UAT-ANN-04 | P1 | Reject | Reject path | Not published | | |

**Module accept:** All P0 Pass.

---

## O. Permissions

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-PERM-01 | P0 | Church Admin | View role matrix | Matrix loads for manageable scope | | |
| UAT-PERM-02 | P0 | Church Admin | Create override for user in scope | Effective permissions change | | |
| UAT-PERM-03 | P0 | Church Admin | Open `user_effective` for out-of-scope user | **Denied** (no superuser IDOR) | | |
| UAT-PERM-04 | P1 | Platform | Confirm institution superadmin ≠ platform OWNER | Lanes separate | | |

**Module accept:** All P0 Pass.

---

## P. Site Control (platform)

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-SC-01 | P0 | Platform Admin | Open `/platform/` settings | Site/security/email/branding editable | | |
| UAT-SC-02 | P0 | Platform Admin | Toggle MFA required (staging only) | Behavior matches flag | | |
| UAT-SC-03 | P0 | Platform Admin | Impersonate institution user → end | Session restored; MFA not enrolled on target | | |
| UAT-SC-04 | P0 | Institution Treasurer | Hit `/platform/` | Denied / redirected | | |
| UAT-SC-05 | P0 | Anonymous | `GET /metrics/` | **401** | | |
| UAT-SC-06 | P1 | READONLY platform | Attempt settings change | Denied | | |

**Module accept:** All P0 Pass.

---

## Q. Multi-tenant validation

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-TEN-01 | P0 | Denom A Treasurer | Member/txn/asset of Denom B | **403/404** | | |
| UAT-TEN-02 | P0 | Platform | Set denomination context → list tenants | Filter applies; clear restores | | |
| UAT-TEN-03 | P0 | Conference A | Cannot manage Conference B org nodes | Denied | | |
| UAT-TEN-04 | P0 | Platform OWNER | Manage settings without becoming institution user | Platform lane intact | | |
| UAT-TEN-05 | P1 | Tree admin | Sees aggregate data only within tree | No foreign district bleed | | |

**Module accept:** All P0 Pass.

---

## R. Financial integrity pack

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-ACC-01 | P0 | Treasurer | Receipt lines | Debits = credits | | |
| UAT-ACC-02 | P0 | Checker | Maker-checker | Creator ≠ approver | | |
| UAT-ACC-03 | P0 | Admin | Period lock | Posts blocked | | |
| UAT-ACC-04 | P0 | Treasurer | Working day closed | Posts blocked | | |
| UAT-ACC-05 | P0 | Auditor role | Financial audit log | Immutable history for approve/void | | |
| UAT-ACC-06 | P0 | Treasurer | Export trial data / report | Figures reconcile to journals | | |

**Module accept:** All P0 Pass.

---

## S. Operational readiness

| ID | P | Role | Steps | Expected | Result | Notes |
|----|---|------|-------|----------|--------|-------|
| UAT-OPS-01 | P0 | Ops | `GET /health/live/` + `/health/ready/` | 200 | | |
| UAT-OPS-02 | P0 | Ops | Trigger `backup_database` (or Beat job) | Artifact created; restore dry-run documented | | |
| UAT-OPS-03 | P0 | Ops | Send test email (invite or password reset) | Delivered to sandbox inbox | | |
| UAT-OPS-04 | P0 | User | Create event that notifies → `/dashboard/notifications/` | Notification appears; mark-read works | | |
| UAT-OPS-05 | P1 | Ops | Confirm Celery worker + Beat running | Scheduled tasks fire (or logged) | | |
| UAT-OPS-06 | P1 | Ops | Force handled 404 / permission denied | User-safe page; no stack trace to client | | |
| UAT-OPS-07 | P1 | Ops | Log review | Auth failures / finance audit visible | | |

**Module accept:** All P0 Pass.

---

## T. Sign-off sheet

| Module | P0 status | Accepted? | Owner | Date |
|--------|-----------|-----------|-------|------|
| User onboarding | | ☐ | | |
| Church onboarding | | ☐ | | |
| Membership | | ☐ | | |
| Transfers | | ☐ | | |
| Baptism/profession | | ☐ | | |
| Giving | | ☐ | | |
| Finance | | ☐ | | |
| Ledger | | ☐ | | |
| Remittance | | ☐ | | |
| Payroll | | ☐ | | |
| Assets | | ☐ | | |
| Meetings | | ☐ | | |
| Reports | | ☐ | | |
| Announcements | | ☐ | | |
| Permissions | | ☐ | | |
| Site Control | | ☐ | | |
| Multi-tenant | | ☐ | | |
| Financial integrity | | ☐ | | |
| Ops readiness | | ☐ | | |

**UAT overall:** ☐ Pass · ☐ Pass with waivers · ☐ Fail  

**Waivers:** _______________________________________________
