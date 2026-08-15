# ChurchHub Security Authorization Invariants

**Status:** Security contract (target state)  
**Date:** 14 August 2026  
**Audit baseline:** `8eb5730f91b18212e17f48b3550afa952492437b` (`main`)  
**Type:** Read-only contract. Application code was not modified for this document.

This file is the **authorization contract** against which P0/P1 remediation and regression tests are judged. It is not a claim that every rule is already true in production.

| Label | Meaning |
|-------|---------|
| **MUST / MUST NOT** | Required after remediation. Tests fail if violated. |
| **Current** | Live Django code at inspection time |
| **Contradiction** | Live code that violates this contract (see §16) |

Companions: `docs/SECURITY_AUDIT_REPORT.md`, `docs/SECURITY_FINDINGS_REGISTER.md`, `docs/SECURITY_REMEDIATION_DESIGN.md`, `docs/SECURITY_REMEDIATION_ROADMAP.md`.

Institution RBAC source: `permissions/registry.py`, `permissions/services.py`, `permissions/checks.py`, `permissions/scoping.py`, `permissions/org_scope.py`.  
Platform RBAC source: `sitecontrol/rbac.py`.  
Tenancy source: `church_system/denomination_scope.py`, `church_system/church_scope.py`.

---

## How authorization is resolved (source of truth)

Institution authorization is **not** Django `auth.Permission` / groups.

Resolution order in `permissions.services._resolve_permission`:

1. Unauthenticated → **DENY**.
2. `is_superadmin(user)` (`permissions/superadmin.py`) → grant every **institution** permission codename, still subject to **denomination + org-scope** on data (`INV-AUTH-01`, `INV-TEN-18`).
3. Active per-user `PermissionOverride` → that grant or deny wins.
4. `RolePermission` matrix cell for `user.role` + codename (falls back to registry `default_roles` if the matrix is missing).
5. Implied grants: another granted permission lists this codename in `implies`.

`is_superadmin` is true for institution `User.role == SUPER_ADMIN` or Django `is_superuser` on the **institution lane**. Platform operators (`is_platform_user`) are **excluded** and use `sitecontrol.rbac` capabilities instead.

**INV-AUTH-01:** Permission checks on views/services are necessary but not sufficient. Every church-owned read or write MUST also pass tenant (denomination) and organizational subtree checks. A granted codename MUST NOT authorize an object outside `get_manageable_churches(user)` (or the portal-member equivalent).

**INV-AUTH-02:** Template `{% can %}` / `permission_flags` are UI only. Absence of a button MUST NOT be treated as enforcement.

**INV-AUTH-03:** Session `current_church_id` and hidden form fields MUST NOT expand scope. `get_active_church` MUST resolve only inside `get_manageable_churches`.

**INV-AUTH-04:** Tests MUST call `user_has_permission` / `can_*` helpers with a seeded matrix. Role-name equality is not authorization.

---

## Vocabulary (actual codes vs informal names)

The registry does **not** define `manage_transactions` or `manage_remittance`. Remediation MUST NOT invent those codes unless this contract is explicitly revised.

| Informal name | Actual permission / mechanism |
|---------------|-------------------------------|
| View transactions | `view_transactions` |
| Create receipts | `manage_receipts` |
| Create expenses | `manage_expenses` |
| Broad finance ops (legacy) | `manage_finances` (implies receipts, expenses, ledger, settlements, welfare **cases**, contribution recording, `view_reconciliation`, etc. — **does not** imply `approve_transactions`, `void_transactions`, `manage_reconciliation`, or `finalize_reconciliation`) |
| Post GL journals | `manage_ledger_entries` |
| District remittance **payment** (cash/bank clearing) | No dedicated code. **Contract:** require `manage_finances` (not `view_transactions` / `view_remittance` alone). Policy config: `manage_remittance_policy`. Settlements: `manage_settlements` / `post_settlements`. |
| View remittance summaries | `view_remittance` |
| Bank rec view / mutate / lock | `view_reconciliation` / `manage_reconciliation` / `finalize_reconciliation` |
| Approve / reject / void journals | `approve_transactions` / `reject_transactions` / `void_transactions` |
| Reverse | Implemented only as **void + reversal journal**. Permission is `void_transactions`. There is no separate reverse permission. |
| View all churches | `view_all_churches` — **subtree/denomination only** (`INV-TEN-07`). |

Platform capabilities (`sitecontrol/rbac.py`): `view`, `manage_tenants`, `manage_security`, `impersonate`, etc. They do not grant institution `can_*` helpers.

---

## 1. Tenant isolation

### Definitions

| Term | Meaning in this codebase |
|------|--------------------------|
| **Tenant / SaaS wall** | `sitecontrol.Denomination` reached via `Church.district.zone.conference.denomination` |
| **Organization subtree** | GC → Union → Conference → Zone → District → Church, filtered by `church_q_for_scope` (`permissions/org_scope.py`) |
| **Platform** | `/platform/` lane; `User.is_platform_user`; capabilities + `managed_denominations` unless Owner/Django superuser |

Default `scope_level` by role (`OrgScopeLevel.default_for_role`): SUPER_ADMIN and GENERAL_OVERSEER → DENOMINATION; UNION_ADMIN → UNION; CONFERENCE_ADMIN → CONFERENCE; ZONE_DIRECTOR → ZONE; DISTRICT_PASTOR → DISTRICT; LOCAL_PASTOR, SECRETARY, TREASURY, BOARD_MEMBER, MEMBER → CHURCH.

### INV-TEN-01 — Denomination wall

An institution user MUST NOT read or write church-owned data whose denomination differs from `get_user_denomination(user)`.

This includes: members, users (institution), transactions, accounts, files, announcements (church and denomination-scoped), reports, exports, welfare, meetings, assets, payroll, contributions, audit logs (institution), and media bytes.

### INV-TEN-02 — Unscoped institution user

If denomination cannot be resolved (`church` and `denomination` both empty):

- `church_q_for_scope` for `DENOMINATION` level already returns `pk__in=[]` unless Django superuser.
- **Contract:** `get_manageable_churches` MUST also deny (empty queryset). Unanchored `SUPER_ADMIN` MUST NOT see all churches.

### INV-TEN-03 — When a user may access another church

Access to a church-owned object is allowed only if **all** of:

1. User is authenticated on the correct lane (institution vs portal vs platform).
2. User holds the required permission **or** is acting as the owning portal member on a self-service object.
3. The object’s church is in `get_manageable_churches(user)` **or** (portal) equals `user.member.church`.
4. That church’s denomination equals the user’s denomination.

| Target | Church-scoped staff (LOCAL_PASTOR, SECRETARY, TREASURY, BOARD_MEMBER, MEMBER) | District / zone / conference / union / GC / denomination-scoped role | Platform operator |
|--------|-------------------------------------------------------------------------------|---------------------------------------------------------------------|-------------------|
| Own church | Yes, if permission | Yes, if church in subtree | Only via platform tenant tools + `filter_churches_for_operator`; **not** via institution apps |
| Other church, same district | No (unless `scope_level` ≥ DISTRICT and that district is the user’s node) | Yes if district is in subtree | Same as operator filter |
| Other district, same conference | No unless scope ≥ ZONE/CONFERENCE and node matches | Yes if in subtree | Operator filter |
| Other conference, same denomination | No unless scope ≥ UNION/GC/DENOMINATION | Yes if in subtree | Operator filter |
| Other denomination / tenant | **MUST DENY** | **MUST DENY** | Allowed only if `operator_has_global_access` **or** denomination ∈ `managed_denominations`. Stats, lists, edits, and **files** all follow this. |
| Platform control room | Institution users MUST NOT access `/platform/` | Same | Capability + optional IP allowlist + MFA policy |

### INV-TEN-04 — Platform operators are not institution superadmins

`is_superadmin` MUST remain false for `is_platform_user`. Platform users MUST NOT receive institution permission bypass. They MUST NOT use `/members/`, `/transactions/`, etc. (`UserScopeMiddleware`). Exception: `/accounts/profile`, invite-accept, MFA, and **authorized** media after object ACL (not “all files”).

### INV-TEN-05 — Church transfer across denominations

`Church.clean()` forbids moving a church to a district in another denomination. Every persist path (`tenant_edit`, repositories, admin) MUST run that validation (`full_clean()` or equivalent). Destination denomination MUST be allowed for the operator.

### INV-TEN-06 — UUIDs are not a security boundary

Knowing a UUID, file name, or sequential code MUST NOT grant access.

### INV-TEN-07 — `view_all_churches` is not `view_all_denominations`

`view_all_churches` / `can_switch_church_context` MAY list and switch among churches in `get_manageable_churches(user)` only.

It MUST NOT:

- unfilter querysets to `Model.objects.all()`,
- include `visibility=general` rows with no denomination,
- expose platform-wide KPIs of other denominations to scoped operators.

`filter_by_church` already uses manageable IDs when no active church is selected (`church_system/church_scope.py`). Announcement and media code MUST do the same.

### INV-TEN-18 — Unanchored superadmin

If `is_superadmin(user)` is true but `get_user_denomination(user)` is missing, `get_manageable_churches` MUST return an empty queryset. `User.clean()` already rejects this assignment; persist paths MUST `full_clean()` so the row cannot exist. Fail-open “all churches” is forbidden.

---

## 2. Role authorization

Defaults below are `PERMISSION_REGISTRY` `default_roles`. Production matrices and overrides can differ; tests MUST use `user_has_permission`, not role name equality.

**Role sets (registry):**

- `_ROLE_TREE`: SUPER_ADMIN, GENERAL_OVERSEER, UNION_ADMIN, CONFERENCE_ADMIN, ZONE_DIRECTOR, DISTRICT_PASTOR
- `_ROLE_ALL_STAFF`: tree + LOCAL_PASTOR, SECRETARY, TREASURY
- `_ROLE_LEADERSHIP`: tree + LOCAL_PASTOR
- `_ROLE_TREASURY_OPS`: SUPER_ADMIN, GENERAL_OVERSEER, CONFERENCE_ADMIN, TREASURY
- `_ROLE_POLICY`: SUPER_ADMIN, GENERAL_OVERSEER, UNION_ADMIN, CONFERENCE_ADMIN
- `_ROLE_READ`: all staff + BOARD_MEMBER
- `_ROLE_HIERARCHY`: same as `_ROLE_TREE`

There is no hard-delete permission for journals, members, or audit rows. “Delete” in this matrix means archive / deactivate / void / reverse as implemented.

### 2.1 Institution roles — default action classes

Scope for every cell: denomination wall + `get_manageable_churches` (or portal self). SUPER_ADMIN bypasses **codenames** but MUST still obey `INV-TEN-01` / `INV-TEN-18`.

| Role | Read (directory, journals, recon worksheets, published announcements) | Create (members, receipts, expenses, remittance payment, meetings) | Update (in-scope records they may manage) | Delete / archive | Approve (journals, minutes, announcements, welfare, assets, payroll, budgets) | Void / reverse journals | Administrative (users, matrix, org tree, periods unlock) |
|------|------|--------|--------|------------------|--------------------------------------------------------------|-------------------------|----------------------------------------------------------|
| SUPER_ADMIN | Yes (codename bypass) | Yes | Yes | Archive/void as granted by bypass | Yes, plus documented SoD break-glass on **own** journal | Yes | Yes in **own denomination** only |
| GENERAL_OVERSEER | Yes (`manage_finances`, view_*) | Yes | Yes | Archive; void via leadership imply | Yes (leadership) | Yes | Denomination / policy |
| UNION_ADMIN | Yes | Yes (`manage_finances`) | Yes in union subtree | Archive; void (leadership) | Journals/minutes/announcements/welfare/assets/payroll/budgets: Yes. Recon **create/match**: **No** (not treasury_ops / local / district pastor) | Yes | Union subtree; unlock periods (policy) |
| CONFERENCE_ADMIN | Yes | Yes | Yes | Archive; void | Yes including recon mutate (`_ROLE_TREASURY_OPS`) | Yes | Conference subtree |
| ZONE_DIRECTOR | Yes | Yes | Yes | Archive; void | Journals etc. Yes. Recon create/match: **No** | Yes | Zone subtree |
| DISTRICT_PASTOR | Yes | Yes | Yes | Archive; void | Yes including recon mutate | Yes | District subtree; unlock periods |
| LOCAL_PASTOR | Yes | Yes | Own church | Archive; void | Yes including recon mutate | Yes | Own church users/working day/lock periods. Not matrix (`manage_permissions` is policy) |
| SECRETARY | Yes finance **view** + `manage_finances` create | Members, receipts, expenses, remittance **payment**, welfare cases, campaigns, meetings | Members/meetings/announcements they may manage | Archive announcements; **not** void journals | **MUST NOT** approve/void journals, minutes (approve_minutes is leadership), welfare, assets, payroll, budgets, recon match | **MUST NOT** | Not `manage_users` / matrix / org tree |
| TREASURY | Yes | Receipts/expenses/ledger/contributions/remittance payment/recon create | Giving/campaigns/assets (manage_assets) / payroll prepare | Not void | Recon **finalize** Yes. Journal approve/void: **No**. Asset approve/dispose: Yes. Payroll approve: **No** | **MUST NOT** | Not users/org/matrix |
| BOARD_MEMBER | Members, transactions, recon **view**, ledger **view**, remittance **view**, welfare **view**, reports, announcements | **MUST NOT** finance writes | **MUST NOT** | **MUST NOT** | **MUST NOT** | **MUST NOT** | **MUST NOT** |
| MEMBER | Own portal profile; `view_members` is granted but **media/directory staff actions** follow §4; own giving/contributions; published in-audience announcements | May `create_announcements` (pending); portal self-service | Own portal profile | **MUST NOT** | **MUST NOT** | **MUST NOT** | **MUST NOT** |

SECRETARY **may** record receipts/expenses and initiate remittance payments under the default matrix; those journals stay PENDING unless receipt auto-approve applies. SECRETARY **must not** approve, void, or run recon worksheets.

TREASURY **may** create money movement and (with `finalize_reconciliation`) lock recon; **must not** approve others’ journals unless granted `approve_transactions`.

BOARD_MEMBER **may** view in-scope journals and recon worksheets; **must not** POST remittance payment or recon create/match.

### 2.2 Default finance permission map (actual codenames)

| Permission | SA/GO | UA | CA | ZD | DP | LP | SEC | TRE | BM | MEM |
|------------|-------|----|----|----|----|----|-----|-----|----|-----|
| `view_transactions` | Y | Y | Y | Y | Y | Y | Y | Y | Y | N |
| `manage_finances` | Y | Y | Y | Y | Y | Y | Y | Y | **N** | N |
| `manage_receipts` / `manage_expenses` | Y | Y | Y | Y | Y | Y | Y | Y | N | N |
| District remittance **payment** (contract = `manage_finances`) | Y | Y | Y | Y | Y | Y | **Y** | Y | **N** | N |
| `view_reconciliation` | Y | Y | Y | Y | Y | Y | Y | Y | Y | N |
| `manage_reconciliation` | Y | **N** | Y | **N** | Y | Y | **N** | Y | **N** | N |
| `finalize_reconciliation` | Y | Y | Y | Y | Y | Y | **N** | Y | N | N |
| `approve_transactions` / `void_transactions` | Y | Y | Y | Y | Y | Y | **N** | **N** | **N** | N |
| `manage_working_day` / `lock_periods` | Y | Y | Y | Y | Y | Y | N | N | N | N |
| `unlock_periods` | Y | Y | Y | N | Y | N | N | N | N | N |
| `view_all_churches` | Y | Y | Y | Y | Y | N | N | N | N | N |

`manage_finances.implies` includes `view_reconciliation` but **not** `manage_reconciliation`. SECRETARY therefore sees recon lists and MUST be denied recon POST.

### 2.3 Platform roles (`sitecontrol/rbac.py`)

| Role | Typical caps | MUST NOT |
|------|----------------|----------|
| OWNER | All listed caps + global denominations | Use institution apps (`/members/`, `/transactions/`, …) |
| SECURITY | Settings/security/operators, audit, announcements, registration | Tenant relocate without `manage_tenants` |
| BILLING | Plans, subscriptions, `manage_tenants`, billing | Impersonate (not in set) |
| SUPPORT | Tenants, applications, platform announcements, impersonate, import | Global stats of unmanaged denoms; all private media |
| READONLY | `view`, audit, billing view | Any mutate, including tenant_edit and remittance |

---

## 3. Object-level authorization

Pattern for every sensitive object:

```
authenticated?
  → correct lane (institution | portal | platform)?
    → permission or self-ownership?
      → object.church ∈ get_manageable_churches(user)
         OR portal self
         OR platform operator_can_access_denomination?
        → denomination wall
          → object state allows the action
            → maker-checker if mutating a controlled record
              → ALLOW
DENY (404 for media/object IDOR; 403 for authenticated wrong permission on a known in-scope object is acceptable for HTML forms)
```

| Resource | Ownership | State gates | Permitted actions |
|----------|-----------|-------------|-------------------|
| `Member` | `member.church` | Portal = own member | View/edit per `view_members` / `edit_members` in scope; portal HTML: self. **Private photo bytes:** §4 |
| `User` (institution) | church / scope node | `user_may_manage_target` | Invite/role only inside subtree; never platform users |
| `Transaction` | `transaction.church` | PENDING vs APPROVED/locked vs voided | Create: receipts/expenses/ledger perms; approve: `approve_transactions` + SoD; void: `void_transactions` + approved + period |
| `Account` (GL) | `account.church` | — | Manage CoA vs view trial balance |
| `BankReconciliation` | `recon.church` + bank account church | `is_reconciled` | View / match / finalize as in §6 |
| `Announcement` | `church` and/or `denomination` (required) | PENDING/APPROVED/REJECTED/ARCHIVED | See §5 |
| `MeetingAttachment` | `meeting.church` | Portal: `show_on_portal` | View if meeting viewable |
| `WelfareCaseAttachment` | `case.church` / `case.member` | Staff welfare perms; portal: own case | |
| `ReportExportJob` | `job.user` | COMPLETE | Download owner only |
| `Church` | denomination via district chain | — | Institution manage_org in subtree; platform tenant tools scoped |
| Private media | Owning row as in §4 | — | Bytes only if object would be readable |

**INV-OBJ-01:** `get_object_or_404(Model, pk=...)` without a scoped queryset is forbidden for tenant-owned models.

**INV-OBJ-02:** Capability-alone checks (`can_approve_announcements(user)` without the announcement) are forbidden for object fetch.

---

## 4. Media

### INV-MED-01 — Authentication is not authorization

**NO authenticated user may access private media merely because they are authenticated.**

`protected_media` MUST call a deny-by-default object/tenant service (`user_may_access_media`). `is_authenticated` is only the first gate after public branding.

### Public vs private

| Path prefix | Class | Anonymous | Authenticated |
|-------------|--------|-----------|----------------|
| `platform/branding/` | Public | ALLOW | ALLOW |
| `denominations/branding/` | Public (login logos, including institution branding) | ALLOW | ALLOW |
| Any other prefix under `MEDIA_ROOT` | Private | Login redirect | Object ACL or **404** |
| Unknown prefix | Private | 404 | **404** (fail closed) |

Current `FileField.upload_to` prefixes: `members/profile_pictures/`, `records/`, `history/`, `meetings/attachments/`, `welfare/cases/`, `announcements/`, `exports/reports/`, plus public branding. Anything else MUST DENY.

### Conditions by action

| Action | Required |
|--------|----------|
| View / display (`<img>`, inline) | Same as download |
| Download (`GET /media/...` or X-Accel) | `user_may_access_media` true for that stored name |
| Export job file via `/media/exports/reports/` | `ReportExportJob.user_id == request.user.id` only |
| Export job via `reports:export_job_download` | Same owner rule |
| Replace / delete file | Owning object’s **update/delete** permission + scope; not a separate media permission |
| Generate new export | Report permission + scope; file then owner-only |

Portal **MEMBER** role: own profile photo (denomination must match); own welfare attachments; portal-visible meeting files of **their** church; announcement images only if the announcement is visible under §5. Default `view_members` on MEMBER MUST NOT grant other members’ private photos.

Staff (non-MEMBER): church in `get_manageable_churches` **and** the module view permission that would show the parent record (e.g. welfare files require welfare view, not merely church membership).

Platform operator: MUST use the same object ACL. `CAP_VIEW` MUST NOT mean all private files. Impersonation uses the impersonated user’s ACL.

Missing denomination, missing church where church scope is required, unknown prefix, or no owning row → **DENY**.

### INV-MED-02 — Deny response

Unauthorized media GET MUST return **404** (not 403) and MUST NOT stream bytes, MUST NOT set `X-Accel-Redirect`, MUST NOT reveal whether the path exists via distinct status/timing if practical.

### INV-MED-03 — Authoritative layer

See §14. Application media-authorization service + `protected_media` are authoritative. Middleware MUST NOT be the sole ACL. Templates, hidden URLs, and JavaScript MUST NOT be the ACL. The storage backend MUST NOT decide tenant authorization.

### INV-MED-04 — No successful access audit for denials

A denied media request MUST NOT write a “file downloaded” / successful export-style audit. Optional security log of denials MUST NOT include confirmation that the file exists (no “found but forbidden” vs “missing” distinction in the client).

---

## 5. Announcements

Four products exist in code; they MUST NOT be collapsed:

| Kind | Model | Tenant key (contract) | Who may read published content |
|------|--------|------------------------|--------------------------------|
| Church-scoped | `announcements.Announcement` `visibility=church` | `church_id` required; denomination derived from church | Users with `view_announcements` whose manageable churches include that church, plus audience (roles/departments). Portal members of that church. |
| Denomination-scoped (“general”) | same model `visibility=general` | `church_id` MUST be null; **`denomination_id` MUST be set** | Users whose `get_user_denomination` equals that denomination, with `view_announcements`, passing audience filters. Not other denominations. |
| Platform-wide banner | `sitecontrol.PlatformAnnouncement` | Platform-owned; not church data | Created with `CAP_MANAGE_ANNOUNCEMENTS`. Shown to institution users as a **banner** (`get_active_platform_announcement`). Not a substitute for denomination general posts. Login-page show is explicit `show_on_login`. |
| Organizational (hierarchy) | Not a separate model | Use church or denomination-scoped rows in the creator’s subtree | Same as church/denomination kinds. Conference admin posting `visibility=church` for a church they manage is organizational only via **scope**, not a fourth visibility enum. |

### INV-ANN-01

`visibility=general` MUST NOT be implemented as “global NULL church.” It means **denomination-wide**.

### INV-ANN-02

`view_all_churches` MUST NOT load `Announcement.objects` unfiltered. Pending queues MUST use `pending_for_user` / `can_approve_announcement(user, obj)`.

### INV-ANN-03 — Detail

`GET` detail allowed if and only if:

- creator of the row, or
- object-scoped approver (`can_approve_announcement`), or
- row ∈ `visible_announcements(user)`.

Otherwise 404/403. Images follow the same visibility (`INV-MED-01`).

### INV-ANN-04 — Writes

Create general: `is_top_level_approver` **and** denomination assignment. Create church: `create_announcements` and church in scope. Approve: object-scoped `approve_announcements`. Archive: scoped `archive_announcements` or creator rules already in services.

---

## 6. Finance — read vs write

### INV-FIN-01 — No read permission authorizes a write

| Permission | MAY | MUST NOT |
|------------|-----|----------|
| `view_transactions` | List/detail in-scope journals, receipts HTML | Create, remittance POST, recon create/match, approve, void |
| `view_pending_approvals` | See queue | Approve/reject |
| `view_reconciliation` | List/detail worksheet | Create, match, finalize |
| `view_remittance` | Policies/summaries | Record district remittance payment, post settlements |
| `view_ledger` | Browse GL | `post_ledger_entry` |
| `view_audit_log` | Read financial audit | Mutate journals |
| `manage_receipts` | Create receipts | Approve (unless auto-approve policy), void, remittance pay, recon mutate |
| `manage_expenses` | Create expenses | Same |
| `manage_finances` | Receipts/expenses/ledger/settlements/contributions/remittance **payment** (contract) | Approve/void unless also those perms; recon mutate unless `manage_reconciliation` |
| `manage_reconciliation` | Create worksheet, match lines | Finalize unless `finalize_reconciliation` |
| `finalize_reconciliation` | Lock recon | Implied manage via registry `implies` |
| `approve_transactions` | Approve/reject pending in scope | Create-as-approve own row (SoD) |
| `void_transactions` | Void approved via reversal | Edit posted lines in place |
| `manage_ledger_entries` | Post category journals | Skip working day / period / balance |

### INV-FIN-02 — Wrappers

`_finance_required` and `ledger_finance_required` MUST NOT wrap POST handlers that create GL or recon rows if they OR view-only codes.

HTML GET for remittance form: `manage_finances`. POST: same.  
Recon GET list/detail: `view_reconciliation` or manage/finalize.  
Recon POST create/match: `manage_reconciliation`.  
Recon POST finalize: `finalize_reconciliation`.

### INV-FIN-03 — BOARD_MEMBER

Default BOARD_MEMBER has `view_transactions` and `view_reconciliation`. Remittance write and recon mutate MUST DENY (including direct POST).

### INV-FIN-04 — SECRETARY

Default SECRETARY has `manage_finances` and `manage_expenses`. They MAY create in-scope receipts/expenses/remittance payments (pending). They MUST obey period, working day, amount > 0, church scope, and MUST NOT approve/void/recon-match unless the matrix grants those codes.

### INV-FIN-05 — Posted journals

No in-place edit of APPROVED/locked lines. Correction = void/reversal. Unbalanced journals MUST NOT lock.

---

## 7. Maker-checker

### INV-SOD-01 — Journals

`approve_transaction`: `created_by_id == user.id` MUST raise unless `is_superadmin` (documented break-glass). Enforced in `transactions/services.py`. MUST remain server-side in the service, not only the view.

Receipt auto-approve (`receipt_should_auto_approve`) is the **only** documented SoD exception: capped income receipts, audited with `auto_approved` / `sod_exception`. MUST NOT apply to expenses, transfers, remittance, ledger, assets, payroll, or welfare disbursement.

`approve_module_journal` MUST NOT approve when no distinct checker exists; callers MUST NOT treat the register as posted while the journal is PENDING.

### INV-SOD-02 — Welfare

`approve_welfare_case`: `case.created_by_id == user.id` MUST DENY.

### INV-SOD-03 — Announcements / minutes / assets / payroll

Existing helpers (`exclude_self_submitted`, `assert_segregation_of_duties` on asset approve, payroll approve vs prepare) MUST stay in **services**. Creator MUST NOT approve own pending announcement except where product already auto-approves top-level general posts (still same user — treat as explicit exception only if `is_top_level_approver` and documented).

### INV-SOD-04 — Void

Void is a privileged reversal, not a second approval of the original. The voiding user MAY be the original creator if they hold `void_transactions` (leadership). Contract does not require creator ≠ voider unless product later tightens it. Concurrent double-void MUST be impossible (`select_for_update` / unique `reversal_of`).

---

## 8. Business date and periods

Posting date = `resolve_transaction_date`: explicit date if provided, else open working day, else local date.

### INV-DATE-01 — Create / post

MUST: period unlocked (`assert_period_open`) AND open working day matching the posting date (`assert_working_day_allows_posting`) for receipts, expenses, transfers, remittance payments, ledger posts, contribution receipts, payroll pay/post, welfare disbursement.

Asset depreciation/disposal CAPITAL journals MUST use the same two asserts and must not update the register if the journal is not approved/locked.

### INV-DATE-02 — Backdate / future-date

A user MUST NOT post to a date other than the **open working day**. That is how backdating and future-dating are forbidden, even if the calendar month is unlocked. Opening a working day on a past date is a `manage_working_day` action (leadership) and MUST itself require an unlocked period.

### INV-DATE-03 — Modify

PENDING unlocked journals: no silent rewrite of posted lines. Reject/void paths only.

### INV-DATE-04 — Approve

`assert_period_open` on the transaction date. MUST NOT approve into a locked month.

### INV-DATE-05 — Void / reverse

Original and reversal dates MUST be in an unlocked period. If a working day is open on the reversal date, posting rules apply. Void MUST NOT proceed if the original month is locked.

### INV-DATE-06 — Closed period

`lock_periods` / `unlock_periods` are separate permissions. Unlock is narrower (`_ROLE_POLICY` + DISTRICT_PASTOR). Unlock MUST be audited.

---

## 9. MFA

Policy is optional (`SiteSettings.mfa_required_for_privileged` + role lists). When a user `user_requires_mfa`:

### INV-MFA-01 — Challenge lifetime

Pending post-password challenge (`SESSION_MFA_PENDING_AT`) MUST expire (contract: 600 seconds, aligned with email OTP TTL). Missing timestamp MUST be treated as expired. Email OTP: 600 seconds; overwritten on resend; deleted on success.

### INV-MFA-02 — Maximum attempts

Per-user verify failures MUST use the same cap as staff `login_max_attempts` (default **5**, SiteSettings min 3 max 20). Lockout duration: `login_lockout_minutes` (default **15**). MUST NOT permanently lock the account solely for MFA failures (`is_active` stays true).

### INV-MFA-03 — Per-user throttling

MUST count verify (and failed enroll TOTP) failures on cache key `user.pk`. Excessive attempts MUST return a generic throttle message and HTTP 429. Valid code during lockout MUST DENY without consuming a new success path.

### INV-MFA-04 — Per-IP throttling

MUST use a separate IP counter with a **higher** cap (recommended **20**) so office NAT is not treated as one treasurer. Different users on the same IP MUST remain allowed until the IP cap. The same user locked on one IP MUST remain locked from another IP.

### INV-MFA-05 — Success retires the challenge

Successful verification MUST `mark_mfa_verified`, pop pending session keys, clear failure counters, and complete `login()` (session rotation). Reusing a retired pending challenge MUST fail.

### INV-MFA-06 — Replay

Email OTP: delete cache on success. Recovery: consume hash. TOTP: store used token/timestep for the window (contract TTL ≥ TOTP `valid_window`). Failed recovery counts as a verify failure.

### INV-MFA-07 — Recovery and trusted device

Remaining recovery codes stay hashed. Trusted device: 30-day hashed cookie may skip the challenge; MUST NOT skip throttling on verify POST if the cookie is invalid.

### INV-MFA-08 — Limiter attachment

MUST NOT attach `/accounts/mfa` to username-based `LoginRateLimitMiddleware.LOGIN_PATHS`. MFA POSTs do not submit a username. Throttle messages MUST NOT enumerate remaining attempts or whether the account exists.

Pending MFA session (password OK, not logged in) is **not** an authenticated app session. Private media MUST remain denied.

TOTP `valid_window` MUST stay ≤ 2.

Email send: existing 3 sends / 900s per user MUST remain; locked user/IP MUST NOT send.

---

## 10. Idempotency

### INV-IDEM-01 — Required claim

These writes MUST `claim_financial_idempotency` (church + user + action + key) **inside** `transaction.atomic`, `select_for_update` on an existing incomplete row, and `complete_financial_idempotency` only after the journal exists:

| Operation | Action key (existing or contract) | Current |
|-----------|-----------------------------------|--------|
| Receipt (teller) | `RECEIPT` | Yes in views |
| Expense | `EXPENSE` | Yes in views |
| District remittance payment | `REMITTANCE` | Yes in view; uniqueness of month also in service (racy) |
| Ledger post | `LEDGER` | Yes in ledger services |
| Payroll post / pay | payroll services | Yes |
| Welfare disbursement | welfare services | Yes |
| **Member contribution / bulk / import** | `CONTRIBUTION` | **Missing — MUST add** |
| Transfers (non-remittance) | if UI posts TRANSFER | MUST claim if a user-facing POST exists |

### INV-IDEM-02 — Not the same as GL journals

Bank reconciliation create/match/finalize: no `FinancialIdempotencyKey` required (not a GL post). Duplicate recon create SHOULD still be guarded by church+account+statement_date uniqueness if the product forbids two open worksheets.

Settlement post: MUST remain single-post (row lock or unique constraint).

### INV-IDEM-03 — Incomplete keys

An in-flight key MUST NOT be returned for a second caller to “continue.” Second caller waits on lock or receives replay/in-progress error.

---

## 11. Auditability

### MUST write immutable records

| Event | Log |
|-------|-----|
| Journal create / approve / reject / void / remittance | `FinancialAuditLog` (model already blocks update/delete) |
| Permission matrix / override | `permissions` audit |
| Platform tenant/operator/settings/impersonation/import | `PlatformAuditLog` (immutable) |
| MFA enroll/verify/email/recovery/trusted device | `UserActivityLog` |
| Report run/export | `ReportAccessAuditLog` |
| Asset approve/depreciate/dispose | asset log + financial audit when GL posted |
| Member sensitive updates / transfers | existing member audit paths |
| CSV/Excel downloads of finance or assets | `audit_export` or equivalent (assets/contributions currently missing) |
| Reconciliation match | Financial audit (currently missing on match) |

### MUST NOT

- Log passwords, OTP plaintext, recovery codes, session tokens.
- Allow Django admin delete of `FinancialAuditLog` / `PlatformAuditLog`.
- Allow delete of `UserActivityLog` (contract; admin currently can delete).
- Write a **successful** media-download audit on 404 denials.

Failed authorization on HTML MAY be Django 403 without a financial audit row (no object). Optional security log is fine.

---

## 12. Deny-by-default

If any of the following is missing, the result MUST be DENY:

- Unauthenticated access to non-public resources
- Permission resolution false
- Church not in manageable set
- Denomination mismatch or denomination missing
- Platform operator without capability **or** without denomination access for that tenant
- Unknown media prefix
- Media path with no owning row
- Announcement without denomination (general) or church (church visibility) after backfill
- Financial POST without required **write** permission
- Approve when creator == approver (except documented receipt auto-approve / break-glass superadmin)
- Posting when period locked or working day closed/mismatched
- MFA verify while lockout cache is set
- Idempotency replay of a completed key
- JSON/session helpers that skip the same checks as HTML

**INV-DENY-01:** Fail open (`scoped = qs`, `OR visibility=general` with no denomination, `if authenticated: deliver`) is forbidden.

---

## 13. API / JSON security

There is no DRF `/api/v1/`. Session `JsonResponse` helpers (member search, ledger categories, dashboard teller totals, notification counts, health/metrics) MUST:

- require login except documented public health (token in production),
- use the same `can_*` and scoped querysets as the HTML page,
- not accept a church id outside manageable churches,
- remain CSRF-protected for POST.

**INV-API-01:** A JSON URL MUST NOT be a permission bypass for an HTML-gated feature.

---

## 14. Storage security

| Layer | Role |
|-------|------|
| **Authoritative ACL** | Application: `user_may_access_media` (and domain services for HTML). |
| **Enforcement for bytes** | `protected_media` (always; DEBUG and production). |
| **Web server** | Nginx: public aliases for branding only; `/internal-media/` MUST stay `internal`; other `/media/` MUST proxy to Django. Defense in depth, not ACL. |
| **Storage backend** | Filesystem or S3. S3 MUST NOT make private objects world-readable. If S3 is enabled, `FileField.url` MUST NOT skip the ACL (signed URL only after allow). |

Gunicorn MUST NOT serve `MEDIA_ROOT` as static files.

---

## 15. Testable invariants (regression scenarios)

Each scenario is a MUST. Prefer 404 for cross-tenant object/media; 403 for in-tenant missing permission. Test **direct HTTP**, not only UI buttons.

1. **Tenant/denomination A user → Tenant A private file → ALLOW (200 + bytes).**
2. **Tenant/denomination A user → Tenant B private file → 404; zero file bytes; no X-Accel; no successful download audit.**
3. **Unauthenticated → private file → redirect to login; branding logo 200.**
4. **Authenticated wrong role (portal MEMBER) → another member’s photo even in the same church → 404; zero bytes.**
5. **Unknown media prefix → 404.**
6. **Missing tenant/denomination (unscoped user) → private file → 404.**
7. **Direct URL `/media/...` (not only `<img>` in a template) MUST obey 1–6.**
8. **BOARD_MEMBER → GET transaction list ALLOW; POST remittance MUST DENY; POST recon create/match MUST DENY.**
9. **SECRETARY → POST in-scope receipt/expense/remittance allowed by default matrix; POST approve/void MUST DENY; POST recon match MUST DENY; journals PENDING (except capped receipt auto-approve).**
10. **User with only `view_transactions` override → same write DENY as (8).**
11. **`view_all_churches` conference admin denom A → church announcement denom B MUST DENY; general announcement denom B MUST DENY; general announcement denom A MAY allow.**
12. **Approver church A → pending announcement PK of church B → 404/403; no body.**
13. **Scoped platform READONLY → dashboard MUST NOT include other denominations’ church names or global counts; OWNER MAY see global.**
14. **SUPPORT POST tenant_edit district in another denomination → reject; `Church.district` unchanged.**
15. **Creator approve own journal → error (not superadmin).**
16. **Creator approve own welfare case → DENY.**
17. **Post receipt on closed working day → DENY; locked period → DENY.**
18. **Two identical contribution POSTs with same idempotency key → one `MemberContribution` and one receipt.**
19. **Valid MFA → login completes. Invalid MFA → stay on challenge. N+1 invalid → 429. Valid code during lock DENY. Success clears lock. Challenge expiry redirects to login. TOTP/email replay after success fails. Same user two IPs: user lock applies. Two users one IP: allowed until IP cap. Retry after throttle TTL succeeds. Throttle text does not enumerate accounts.**
20. **Export job of user A → `/media/exports/reports/<file>` as user B → 404; `export_job_download` as B → 404.**
21. **JSON member search church_id of other denomination → empty/403, never rows.**
22. **Unanchored SUPER_ADMIN (no church, no denomination) → `get_manageable_churches` empty (or save rejected).**

---

## 16. Current contradictions (code vs this contract)

Do not treat this section as permission to weaken the contract. Remediation must close remaining rows.

Inspection of **this workspace** (including uncommitted files) vs the MUST rules:

| Invariant | Current code |
|-----------|----------------|
| INV-MED-01 / INV-MED-02 | **Aligned on this working tree:** `church_system/media_authorization.py` `user_may_access_media` + `protected_media` 404. Tests no longer assert unscoped 200. **Audit baseline `main` contradicted this** (`is_authenticated` only). Remaining: S3 `FileField.url` may still bypass Django if bucket env is set (`INV-MED-03`). Templates still emit `.url`; that is safe only while MEDIA_URL hits `protected_media`. |
| INV-MFA-01 … INV-MFA-08 | **Aligned on this working tree:** per-user/per-IP cache lock, pending TTL, TOTP replay cache, enroll/verify 429, `LOGIN_PATHS` still excludes `/accounts/mfa`. **Audit baseline `main` contradicted this.** |
| INV-FIN-01 / INV-FIN-03 / INV-FIN-04 remittance & recon | **Aligned on this working tree:** `_remittance_write_required` (`manage_finances`); recon list/detail GET uses view/manage/finalize; recon create/match POST uses `manage_reconciliation`. **Audit baseline `main` used `_finance_required` (OR `view_transactions`) on remittance POST and recon writes.** |
| INV-FIN-02 ledger | `ledger_finance_required` still ORs `view_ledger` onto posting views (`ledger/views.py`). |
| INV-TEN-07 / INV-ANN-01 | **Aligned on this working tree (Phase 2):** `Announcement.denomination` FK; selectors require denomination predicate; `visible_announcements` never uses unfiltered `scoped = qs`. **Audit baseline / Phase 1 contradicted this.** Quarantined NULL-denomination rows remain fail-closed. |
| INV-OBJ-02 / INV-ANN-03 | **Aligned on this working tree (Phase 2):** denomination-scoped object load + object-scoped `can_approve_announcement`. **Audit baseline contradicted this.** |
| INV-TEN-05 | `repo.save_church` → `Model.save()` skips `Church.clean()`. |
| INV-TEN-02 / INV-TEN-18 | `get_manageable_churches`: unanchored superadmin returns **all** churches. `User.clean()` would block; `save()` does not `full_clean()`. |
| INV-DATE-01 / INV-SOD-01 | Asset depreciation/disposal skip working day and `approve_module_journal`; register updates while GL is PENDING. |
| INV-IDEM-01 | `record_member_contribution` has no idempotency claim. |
| INV-IDEM-03 | `claim_financial_idempotency` returns incomplete keys without locking. |
| INV-SOD-02 | `approve_welfare_case` does not compare creator vs approver. |
| INV-SOD-04 | `void_transaction` checks `is_voided` without `select_for_update`. |
| INV-TEN-03 platform stats | `platform_stats()` / over-limit names are global; `CAP_VIEW` operators see them. |
| §11 activity log | `UserActivityLogAdmin` allows delete. |
| §11 exports | Asset/contribution CSV without `audit_export`. |

**Not contradictions (already aligned on audit baseline and still aligned):**

- Core `approve_transaction` SoD and period/working-day on receipt/expense/remittance **service**.
- `export_job_for_user` owner scope for the reports download view.
- `PlatformAuditLog` / `FinancialAuditLog` immutability.
- `filter_by_church` using manageable IDs.
- `church_q_for_scope` deny-empty for unscoped denomination **non-superadmin**.
- CSRF on session POSTs; no DRF `/api/v1/`.
- Public branding prefixes only.

---

## 17. How to use this document

1. Every P0/P1 PR MUST cite invariant IDs in tests or brief comments (e.g. `INV-MED-01`, `INV-FIN-01`, `INV-MFA-03`).
2. A PR that changes `_finance_required`, `protected_media`, `visible_announcements`, or `get_manageable_churches` MUST update this file if the contract changes — not silently weaken it.
3. Role-name tests are insufficient; grant/deny via `user_has_permission` and scoped fixtures.
4. Do not invent `manage_transactions` or `manage_remittance` to satisfy a test.
5. Until remaining §16 rows are closed, production remains **READY WITH CRITICAL REMEDIATIONS**, not security-hardened.
