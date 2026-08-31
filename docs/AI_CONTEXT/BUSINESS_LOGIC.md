# ChurchHub — Business Logic (As Implemented)

**Audience:** AI agents and engineers  
**Source of truth:** Live Django models and services  
**Companions:** `SYSTEM_OVERVIEW.md`, `DATABASE_MAP.md`, `CODING_GUIDE.md`, root `BUSINESS_RULES.md`, `FINANCE.md`, `MEMBERSHIP.md`, `AGENTS.md`

This document describes **rules the code enforces today**. Where root docs describe richer rules that are not implemented, that gap is called out explicitly.

---

## 1. Tenancy and data ownership

### Rules in force

1. **Operational records belong to a Church** (or resolve through one). Examples: Member, Account, Transaction, Announcement, Meeting, FixedAsset, Budget (church-level).
2. **Denomination isolates SaaS tenants.** `Conference.denomination` → derived on Church. Cross-denomination member transfer is blocked when both sides have denominations set (`members.services.request_transfer`).
3. **Users only act within manageable churches / org scope.** Use `church_system.church_scope`, `permissions.org_scope`, `permissions.scoping` — never rely on UI alone.
4. **Platform users** (`is_platform_user=True`) use `/platform/` and must not be assigned a home church (`accounts.User.clean`).

### Not implemented (docs only)

- Soft-delete (`is_deleted` / `deleted_at`) — use status / void / deactivate patterns that exist on each model instead.

---

## 2. Organization hierarchy

**Models:** `organization.models`

```
GeneralConference → Union → Conference → Zone → District → Church
```

- `Conference.union` may be null.
- `Conference.denomination` → `sitecontrol.Denomination` (nullable, PROTECT).
- Church helpers: `.zone`, `.conference`, `.union`, `.general_conference`, `.denomination` (properties).
- Church flags: `is_active`, `financials_provisioned`.
- Moving a church across denominations via district change is blocked in `Church.clean` (use transfer workflow).

**Audit:** `OrganizationAuditLog`.

---

## 3. Membership

**Primary code:** `members/models.py`, `members/services.py`

### 3.1 Member identity

Key fields (not exhaustive — see `DATABASE_MAP.md`):

- Names: `first_name`, `last_name`
- Demographics: `gender`, `marital_status`, `date_of_birth`
- Church links: `church`, optional `department`, `family`, `occupation`
- Status: `membership_status`, `is_active`
- Contact: `phone`, `address`
- Baptism: `baptism_date`, `baptism_place`, `baptism_certificate_number`
- IDs: UUID `id`, optional `membership_number` (unique per church when non-empty)

### 3.2 MembershipStatus (exact values)

From `MembershipStatus` TextChoices:

| Value | Effect on `is_active` |
|-------|------------------------|
| `Active` | Forced `True` on save |
| `Inactive` | Forced `False` |
| `Transferred` | Forced `False` |
| `Deceased` | Forced `False` |

Default: `Active`.

> Root `AGENTS.md` lists many additional statuses (Visitor, Bible Student, Missing, Suspended, …). **Those are not in the live enum.** Do not invent them without a migration and product approval.

### 3.3 Duplicate prevention

| Layer | Behavior |
|-------|----------|
| Soft warn | `find_duplicate_members` — same church, case-insensitive first+last name; match DOB and/or phone |
| Hard reject | `create_member` / `update_member` — unique non-empty `phone` and `membership_number` per church |
| DB | Constraints `uniq_member_phone_per_church`, `uniq_member_number_per_church` |

### 3.4 Family

- `Family`: `church`, `name`, optional `head` (Member), `address`, `phone`
- Unique `(church, name)`
- Head must belong to same church
- Member.family must belong to member’s church
- Transfer completion clears `family` (and `department`)

### 3.5 Transfers

**Statuses (`TransferStatus`):** `Pending` (default), `Completed`, `Rejected`

| Service | Rule |
|---------|------|
| `request_transfer` | Creates Pending; blocks same church, already Transferred, existing Pending, cross-denomination when both denoms set |
| `complete_transfer` | Only Pending; ends active leadership at from-church; clears department/family; moves member to `to_church`; sets status Active + is_active True; creates history records; → Completed |
| `reject_transfer` | Only Pending → Rejected |

Helpers: `can_process_transfer`, `user_can_view_transfer`, `log_member_audit`.

### 3.6 Leadership

`LeadershipRole`: `church`, `member`, optional `department`, `title`, `start_date`, optional `end_date`, `is_active`, `created_at`.  
Member and department must match role church.

### 3.7 Related membership objects

- `Department`, `Occupation` — per church
- `Record` / `RecordImage`, `History` / `HistoryImage`
- `SpiritualGift` / `MemberSpiritualGift`
- `MemberAuditLog`

---

## 4. Finance and accounting

**Primary code:** `transactions/models.py`, `transactions/services.py`

### 4.1 Chart of accounts

`Account` is per-church with typed `account_type` values including (among others):

`TITHE`, `COMBINED`, `INCOME`, `EXPENSE`, remit/retention/welfare types, payroll payable/expense types, `BANK`, `CASH`, fixed-asset / depreciation types.

Constraints: unique `(church, name)`; unique `(church, code)` when code non-empty.

### 4.2 Transactions

**Types:** `RECEIPT`, `EXPENSE`, `TRANSFER`, `PAYROLL`, `CAPITAL`

**Approval:** `PENDING` (default) → `APPROVED` | `REJECTED`

**Integrity:**

- Lines: `TransactionLine.amount` (signed decimal); sum of lines must be **0** (`validate_transaction_balance` / `Transaction.validate_balance`)
- Line account church must match transaction church
- Locked transactions reject line edits
- Fields: `locked`, `is_voided`, `voided_at`, `voided_by`, `reversal_of`, `created_by`, `approved_by`, `approved_at`, optional `ledger_category`, optional `member`

### 4.3 Void / reversal

`void_transaction`:

- Requires not already voided, `APPROVED`, and not itself a reversal
- Creates opposite-line APPROVED reversal with `reversal_of` set
- Marks original `is_voided=True`
- Hooks welfare void; period must be open; working-day rules apply when an open day matches

**Do not** edit posted history in place. Use void/reversal.

### 4.4 Working day and periods

| Model | Key rule |
|-------|----------|
| `WorkingDay` | Status `OPEN` / `CLOSED`; open day is posting business date |
| `FinancialPeriod` | `is_locked`; locked period blocks posting (`PeriodLockedError`) |

Services include `assert_working_day_allows_posting`, `assert_period_open`, open/close/lock helpers.

### 4.5 Monthly cutoff

`MonthlyCutoff` per `(church, month)`:

- Aggregates approved non-voided remittance payable lines into `total_tithe`, `total_combined`
- `total_payable` = tithe + combined
- `transferred` flag when remittance transfer marked

Coexists with remittance `SettlementBatch` — see §5 (dual remittance concepts).

### 4.6 Budgets

Model lives in **`transactions.Budget`** (UI in `budgets` app).

Levels: `CHURCH`, `DEPARTMENT`, `DISTRICT`, `CONFERENCE`  
Fields include year, org FKs by level, `account`, `amount`, `notes`.

### 4.7 Offering categories

`OfferingCategory`: per-church `name`, `code`, linked `account`, `remit_to_district`, `is_active`; unique `(church, code)`.

### 4.8 Fund tags on lines

`TransactionLine.fund` choices: `OPERATIONAL`, `TITHE_TRUST`, `COMBINED_TRUST`, `COMBINED_RETENTION`, `WELFARE` (optional blank).

### 4.9 Maker-checker

Financial approval is maker-checker oriented: approve/reject/void gated by permissions (`can_approve_transactions`, etc.). Creators should not self-approve where services enforce that pattern — verify in `transactions/services.py` when changing approval flows.

### 4.10 Ledger app

`ledger.LedgerCategory` is a **posting template** (church, DR/CR accounts, remittance flags). The general ledger is still `Transaction` / `TransactionLine`. Do not treat `ledger` as a second books-of-record store.

### 4.11 Giving app

No giving tables. Statements are derived from approved transaction lines via `giving/services.py`.

---

## 5. Remittance and welfare

**Primary code:** `remittance/models.py`, `remittance/services.py`, `remittance/welfare_services.py`

### 5.1 RemittancePolicy

- Offering types: `TITHE`, `COMBINED`, `WELFARE`
- Application scopes: `GROSS_COLLECTION`, `SETTLEMENT_FROM_BELOW`
- Unit types (polymorphic): `CHURCH`, `DISTRICT`, `CONFERENCE`, `UNION`, `GENERAL_CONFERENCE` + `unit_id` UUID
- **`retain_percent` + `remit_percent` must equal 100**

### 5.2 SettlementBatch

Statuses: `DRAFT` → `POSTED` | `VOID`  
Tracks from/to unit, period, gross/retain/remit amounts, lines.

### 5.3 Dual remittance note

`transactions.MonthlyCutoff` and `remittance.SettlementBatch` both relate to remittance operations. Agents must inspect both call paths before changing remittance behavior — do not assume a single source of truth.

### 5.4 Welfare

| Model | Purpose |
|-------|---------|
| `WelfareContribution` | Member (or anonymous) contributions linked to transactions |
| `WelfareAssistanceCase` | Assistance workflow |
| `WelfareCaseAttachment` | Case files |
| `WelfareMemberLedger` | Per-member welfare activity |

Assistance case statuses include: `PENDING`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, `DISBURSED`, `CANCELLED`.

---

## 6. Payroll

**Primary code:** `payroll/models.py`, `payroll/services.py`

### PayrollRun statuses

`DRAFT` → `CALCULATED` → `APPROVED` → `POSTED` → `PAID`  
Also: `REJECTED`, `VOID`

Typical service flow:

1. `create_payroll_run` → DRAFT  
2. `calculate_payroll_run` → CALCULATED  
3. `approve_payroll_run` → APPROVED  
4. `treasury_approve_payroll_run` — dual approval fields (status remains APPROVED)  
5. `post_payroll_run` → POSTED; creates `Transaction` with type `PAYROLL`  
6. `pay_payroll_run` → PAID; creates payment transaction  

Also: `reject_payroll_run`, `reopen_payroll_run`, `void_payroll_run` (not for POSTED/PAID per service rules).

Employees use polymorphic `paying_unit_type` / `paying_unit_id` plus `host_church`. Sensitive fields use encryption helpers in the payroll app.

---

## 7. Fixed assets

**Primary code:** `assets/models.py`, `assets/services.py`

`FixedAsset` statuses: `DRAFT`, `PENDING_APPROVAL`, `ACTIVE`, `UNDER_REPAIR`, `DISPOSED`, `REJECTED`

Editable when DRAFT or REJECTED. Approval / capitalize / depreciate paths post into the financial core via services. Categories may come from platform templates (`AssetCategoryTemplate`) or church categories.

---

## 8. Meetings and attendance

**Primary code:** `meetings/models.py`

### Meetings

- `MeetingStatus`: `SCHEDULED`, `HELD`, `CANCELLED`
- Minutes: `MinutesStatus` — `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`
- Related: attachments, action items, decisions
- `MeetingAttendance`: present/absent for a formal meeting; unique `(meeting, member)`

### Worship / event attendance

- `AttendanceEvent` types include: `WORSHIP`, `SABBATH_SCHOOL`, `PRAYER`, `DEPARTMENT`, `OTHER`
- `AttendanceRecord` per member; unique `(event, member)`
- `headcount` on event for visitors/guests **not** on the member roll

**Gap:** There is no `Visitor` model or visitor-to-member conversion workflow. Do not invent one from AGENTS.md without approval.

---

## 9. Announcements

**Church:** `announcements.Announcement` — church-scoped, approval/archive/pin patterns, images, views, audit.

**Platform:** `sitecontrol.PlatformAnnouncement` — separate platform messaging.

Do not conflate the two.

---

## 10. Permissions and authorization

**Primary code:** `permissions/services.py`, `permissions/checks.py`, `permissions/roles.py`, `permissions/org_scope.py`, `permissions/registry.py`

### Role codes (`UserRole`)

`SUPER_ADMIN`, `GENERAL_OVERSEER`, `UNION_ADMIN`, `CONFERENCE_ADMIN`, `ZONE_DIRECTOR`, `DISTRICT_PASTOR`, `LOCAL_PASTOR`, `SECRETARY`, `TREASURY`, `BOARD_MEMBER`, `MEMBER`

### Org scope levels (`OrgScopeLevel`)

`CHURCH`, `DISTRICT`, `ZONE`, `CONFERENCE`, `UNION`, `GENERAL_CONFERENCE`, `DENOMINATION`

### `user_has_permission(user, codename)` resolution order

1. Unauthenticated → False  
2. Superadmin → True  
3. Active `PermissionOverride` → use override  
4. RolePermission matrix (or registry defaults if tables not ready)  
5. Implied grants from `PERMISSION_REGISTRY`  
6. Optional per-request cache  

Views should use `permission_required` / `any_permission_required` / `can_*` from `permissions.checks`. Object-level church scope helpers live in `permissions.scoping_checks`.

---

## 11. Platform / SaaS business logic

**Primary code:** `sitecontrol/models.py`, `registration_services.py`, `provisioning_services.py`, `billing_services.py`

| Concept | Behavior |
|---------|----------|
| `Denomination` | SaaS isolation, branding, feature flags, defaults |
| `TenantSubscription` | OneToOne Church; statuses `TRIAL`, `ACTIVE`, `SUSPENDED`, `EXPIRED`; operational check uses status + `expires_at` |
| `TenantApplication` | Statuses `PENDING`, `APPROVED`, `REJECTED`, `WITHDRAWN`; types `EXISTING_DISTRICT`, `NEW_HIERARCHY` |
| `SubscriptionActivationRequest` | Church-submitted full-version request; statuses `PENDING`, `ACKNOWLEDGED`, `ACTIVATED`, `REJECTED`; payment reference required; no email send |
| Approval path | Queued: `submit_tenant_application` → `approve_tenant_application` / `reject_tenant_application`. Public demo: `submit_tenant_application` → `auto_provision_public_demo` (TRIAL, frozen `expires_at`, first user, no invite) |
| Demo cutoff | `SubscriptionAccessMiddleware` + `TenantSubscription.is_operational` (date, not the expire job) |
| Paid upgrade request | `submit_activation_request` → in-app notify all platform operators; activate via `record_subscription_payment` |
| Demo identity | One APPROVED application per email / username / normalized phone |
| `SiteSettings` | Singleton platform settings (SMTP, maintenance, etc.) |
| `PlatformAuditLog` | Immutable platform audit |

---

## 12. Reports and dashboard

- `reports`: builds scoped datasets; `ReportExportJob` for async-capable exports; `ReportAccessAuditLog`
- `dashboard`: KPIs, notifications (`Notification`), church switching for hierarchy users. **Current:** `DashboardScope` drives roll-ups; compact hero on `control-center--home`; `build_kpi_widgets` + `dashboard/metrics.py` (including vs prior-month deltas); `dashboard/home_panels.py` for inbox, attendance, visitor funnel, settlement strip, budget glance, activity feed, coaching hints, portal staff alert links, and member portal banner.

Always scope report queries to the user’s manageable churches / denomination.

---

## 13. Portal

`portal` provides member-linked self-service views. **Current:** `SpiritualSubmission` (prayer, thanksgiving, testimony) with forms at `/portal/prayer/` and `/portal/thanksgiving/`; moderated **praise wall** at `/portal/praise/` (reviewed thanksgiving/testimony only); staff inbox at `/portal/staff/submissions/` with CSV export via `view_portal_submissions` / `manage_portal_submissions`; pastoral team in-app notifications and immutable `SpiritualSubmissionAuditLog`; submit rate limit (12/hour per user). After deploy, run `python manage.py seed_permissions` if new portal permissions were added.

---

## 14. Audit expectations (implemented vs aspirational)

**Present (domain-specific):** FinancialAuditLog, MemberAuditLog, OrganizationAuditLog, PermissionAuditLog, PlatformAuditLog, AssetAuditLog / AssetPolicyAuditLog, RemittancePolicyAuditLog, AnnouncementAuditLog, ReportAccessAuditLog, UserActivityLog, PayrollRunAuditLog, etc.

**Aspirational (`AGENTS.md`):** universal soft-delete + single audit pattern for every module. Do not assume every model has full old/new JSON audit or soft-delete columns.

---

## 15. Agent rules for business logic changes

1. Read the relevant `*/services.py` before changing a workflow.  
2. Prefer extending services over copying rules into views.  
3. Never invent statuses, account types, or roles that are not in the code.  
4. Never silently edit approved/locked financial records.  
5. Preserve denomination and church isolation on every new query path.  
6. When root docs conflict with code, **follow the code** and note the gap in the PR / explanation.
