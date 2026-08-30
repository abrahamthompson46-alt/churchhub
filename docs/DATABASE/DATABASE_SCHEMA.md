# ChurchHub — Database Schema (Live)

**Audience:** Architects, AI agents, DBAs  
**Source of truth:** Django `*/models.py` and migrations  
**Companions:** `ENTITY_RELATIONSHIP.md`, `MIGRATION_HISTORY.md`, `docs/AI_CONTEXT/DATABASE_MAP.md`, root `DATABASE_DESIGN.md`, `AGENTS.md`

| Label | Meaning |
|-------|---------|
| **Current** | Schema as implemented |
| **Planned (AGENTS.md)** | Enterprise data standards not fully realized |
| **Recommended** | Safe future evolution |

---

## 1. Engine and global defaults (Current)

| Setting | Value |
|---------|-------|
| Production DB | PostgreSQL via `DATABASE_URL` |
| Local default | SQLite |
| `AUTH_USER_MODEL` | `accounts.User` |
| `DEFAULT_AUTO_FIELD` | `django.db.models.BigAutoField` |
| Soft-delete columns | **None** (`is_deleted` / `deleted_at` / `deleted_by` absent) |
| ContentType GFK | Unused; polymorphic patterns use `*_type` + `*_id` UUID pairs |

### Primary key patterns

| Pattern | Models |
|---------|--------|
| UUID PK | Vast majority of domain models |
| BigAutoField | `Occupation`, `Record`, `RecordImage`, `History`, `HistoryImage`, `TransactionLine`, `BankReconciliationItem`, `Announcement`, `AnnouncementImage`, `AnnouncementView`, `Notification` |
| Singleton int | `SiteSettings.singleton_id` (`PositiveSmallIntegerField`, default 1) |

---

## 2. Tenant and financial ownership (Current)

```
sitecontrol.Denomination          ← SaaS tenant wall
        │
        ▼ FK
organization.Conference → … → Church   ← operational tenant
```

| Ownership pattern | Fields | Used by |
|-------------------|--------|---------|
| Church FK | `church` / `host_church` | Most operational tables |
| Denomination FK | `denomination` | User, Invitation, Conference, TenantApplication, PlatformAuditLog |
| Polymorphic org unit | `unit_type` + `unit_id` | RemittancePolicy, SettlementBatch |
| Polymorphic paying unit | `paying_unit_type` + `paying_unit_id` | Employee, PayrollRun |
| User scope anchors | `church`, `scope_*`, `denomination` | User, UserInvitation |
| Financial books | Always under `transactions` church FK | Account, Transaction, Budget, Periods, … |

**Financial ownership rule:** The general ledger is `transactions.Transaction` + `TransactionLine`. `ledger.LedgerCategory` is a posting template only. `budgets` / `giving` apps have **no tables**.

---

## 3. Apps without schema

| App | Status |
|-----|--------|
| `budgets` | Empty `models.py` — uses `transactions.Budget` |
| `giving` | Empty `models.py` — reads transactions |
| `portal` | No models |
| `admin_custom` | No models |
| `church_system` | No models |

---

## 4. Complete model inventory by app

### 4.1 `accounts` (3 models)

#### `accounts.User`
| Item | Detail |
|------|--------|
| PK | `id` UUID |
| Enums | `role` → UserRole; `scope_level` → OrgScopeLevel; `platform_role` → OWNER/SECURITY/BILLING/SUPPORT/READONLY |
| FKs | `church` → Church SET_NULL; `scope_district/zone/conference/union/general_conference` SET_NULL; `denomination` → Denomination PROTECT |
| O2O | `member` → Member SET_NULL (`related_name=user_account`) |
| M2M | `managed_denominations` → Denomination (`platform_operators`) |
| Indexes | `(role, is_active)`, `(church, is_active)`, `(scope_level, is_active)` |
| Tenant | church + denomination + scope FKs |
| Notes | `mfa_enabled` stub; `is_active` from AbstractUser |

#### `accounts.UserActivityLog`
| Item | Detail |
|------|--------|
| PK | UUID |
| Enums | action: LOGIN, LOGOUT, PASSWORD_CHANGE, ROLE_CHANGE, CHURCH_ASSIGN, USER_CREATE, USER_DEACTIVATE, USER_ACTIVATE, INVITE_*, PROFILE_UPDATE, EMAIL_CHANGE, SCOPE_CHANGE |
| FKs | `user` CASCADE; `performed_by` SET_NULL |
| Indexes | `(user, action)`, `(-created_at)` |

#### `accounts.UserInvitation`
| Item | Detail |
|------|--------|
| PK | UUID; `token` UUID unique |
| FKs | church + scope units + denomination (nullable); `invited_by` SET_NULL |
| Enums | role / scope_level (same as User) |

---

### 4.2 `permissions` (4 models)

| Model | PK | Key relations / constraints |
|-------|-----|-----------------------------|
| `Permission` | UUID | `codename` unique; `is_active` |
| `RolePermission` | UUID | FK `permission`; `role` CharField; **unique_together** `(role, permission)`; index `(role, permission)` |
| `PermissionOverride` | UUID | FK user, permission; indexes `(user, permission, is_active)`, `(expires_at)` |
| `PermissionAuditLog` | UUID | actions MATRIX_*/OVERRIDE_*; FKs performed_by, target_user |

Tenant: **global** catalog (not church-scoped). Authorization scope is applied at query time.

---

### 4.3 `organization` (7 models)

| Model | PK | FKs / constraints |
|-------|-----|-------------------|
| `GeneralConference` | UUID | `name` unique, `code` unique |
| `Union` | UUID | FK → GC CASCADE; **unique_together** `(name, general_conference)` |
| `Conference` | UUID | `name`/`code` unique; FK `denomination` PROTECT nullable; FK `union` SET_NULL nullable |
| `Zone` | UUID | FK → Conference; unique `(name, conference)`; **UniqueConstraint** `uniq_zone_code_per_conference` `(conference, code)`; index `org_zone_conf_code_idx` |
| `District` | UUID | FK → Zone; unique `(name, zone)`; **UniqueConstraint** `uniq_district_code_per_zone`; index `org_dist_zone_code_idx` |
| `Church` | UUID | FK → District; unique `(name, district)`; **UniqueConstraint** `uniq_church_code_per_district`; index `org_church_dist_code_idx`; flags `is_active`, `financials_provisioned` |
| `OrganizationAuditLog` | UUID | actions CREATE/UPDATE/DEACTIVATE/ACTIVATE/TRANSFER; polymorphic entity refs (not FK); FK `performed_by` |

---

### 4.4 `sitecontrol` (8 models)

| Model | PK | Key points |
|-------|-----|------------|
| `SiteSettings` | `singleton_id` PositiveSmallInteger | Platform singleton; FK `application_default_plan` → SubscriptionPlan; `auto_provision_public_trials`; `public_demo_trial_days` (max 30) |
| `SubscriptionPlan` | UUID | `code` SlugField unique; feature flags; `is_active` |
| `PlatformPaymentMethod` | UUID | method_type BANK_TRANSFER/MOBILE_MONEY/CARD/CASH/INVOICE |
| `TenantSubscription` | UUID | **O2O** `church` CASCADE; FK plan PROTECT; status TRIAL/ACTIVE/SUSPENDED/EXPIRED; billing_interval MONTHLY/YEARLY |
| `PlatformAuditLog` | UUID | Immutable; many action codes; FK user, denomination; indexes on created_at/action |
| `PlatformAnnouncement` | UUID | Platform-wide; FK created_by |
| `TenantApplication` | UUID | status PENDING/APPROVED/REJECTED/WITHDRAWN; type EXISTING_DISTRICT/NEW_HIERARCHY; `contact_phone_normalized`; FKs district, denomination PROTECT, reviewed_by, created_church, invitation |
| `Denomination` | UUID | `code` Slug unique; SaaS wall; FK default_plan; index `(is_active, code)` |

---

### 4.5 `members` (13 models)

#### Enumerations
| Enum | Values |
|------|--------|
| Gender | Male, Female |
| MaritalStatus | Single, Married, Widowed, Divorced |
| MembershipStatus | Active, Inactive, Transferred, Deceased |
| TransferStatus | Pending, Completed, Rejected |
| RecordType | Baptism, Marriage, Funeral, Meeting, Transfer, Other |
| RecordStatus | Active, Archived |

#### Models

| Model | PK | Relations / constraints | Tenant |
|-------|-----|-------------------------|--------|
| `Department` | UUID | FK church; unique `(church, name)` | church |
| `Family` | UUID | FK church; FK head → Member SET_NULL; unique `(church, name)` | church |
| `Occupation` | BigAuto | FK church; unique `(church, name)` | church |
| `Member` | UUID | FKs church, occupation, department, family, created_by; indexes church+active/status/name/phone; **UniqueConstraint** `uniq_member_phone_per_church`, `uniq_member_number_per_church` (non-empty) | church |
| `MemberTransfer` | UUID | FKs member, from_church, to_church, requested_by, processed_by; indexes status/churches | via churches |
| `RecordImage` | BigAuto | — | — |
| `Record` | BigAuto | FK church, member; **M2M** images → RecordImage; FK created_by; index `(church, record_type, event_date)` | church |
| `HistoryImage` | BigAuto | — | — |
| `History` | BigAuto | FK church, member; **M2M** images; FK created_by | church |
| `SpiritualGift` | UUID | FK church; unique `(church, name)` | church |
| `MemberSpiritualGift` | UUID | FK member, gift; unique `(member, gift)` | via member |
| `LeadershipRole` | UUID | FK church, member, department nullable | church |
| `MemberAuditLog` | UUID | FK church, member, performed_by; action CREATE/UPDATE/STATUS/TRANSFER_*/EXPORT/DEACTIVATE/ACTIVATE | church |

---

### 4.6 `transactions` — books of record (12 models)

#### Account types (`Account.account_type`)
`TITHE`, `COMBINED`, `INCOME`, `EXPENSE`, `DISTRICT_PAYABLE`, `TITHE_REMIT_PAYABLE`, `COMBINED_REMIT_PAYABLE`, `COMBINED_RETENTION`, `WELFARE_FUND`, `REMITTANCE_RECEIVABLE`, `SALARY_EXPENSE`, `EMPLOYER_SSNIT_EXPENSE`, `SALARIES_PAYABLE`, `PAYE_PAYABLE`, `SSNIT_PAYABLE`, `PENSION_PAYABLE`, `BANK`, `CASH`, `FIXED_ASSET`, `ACCUMULATED_DEPRECIATION`, `DEPRECIATION_EXPENSE`

#### Transaction enums
| Field | Values |
|-------|--------|
| transaction_type | RECEIPT, EXPENSE, TRANSFER, PAYROLL, CAPITAL |
| approval_status | PENDING, APPROVED, REJECTED |
| fund (line) | OPERATIONAL, TITHE_TRUST, COMBINED_TRUST, COMBINED_RETENTION, WELFARE (may be blank) |
| WorkingDay.status | OPEN, CLOSED |
| Budget.level | CHURCH, DEPARTMENT, DISTRICT, CONFERENCE |
| Idempotency action | RECEIPT, EXPENSE, REMITTANCE, LEDGER, PAYROLL_POST, PAYROLL_PAY |

#### Models

| Model | PK | Key relations / constraints | Tenant |
|-------|-----|-----------------------------|--------|
| `Account` | UUID | FK church; unique `(church, name)`; UniqueConstraint `account_church_code_uniq` non-empty code; indexes church+code/active | church |
| `Transaction` | UUID | FK church, member, voided_by, reversal_of (self), created_by, approved_by, ledger_category; UniqueConstraint `uniq_txn_reference_per_church`; indexes church+status+date, type, reference; flags locked, is_voided | church |
| `TransactionLine` | BigAuto | FK transaction, account; indexes `txn_line_account_idx`, `txn_line_txn_acct_idx` | via txn |
| `MonthlyCutoff` | UUID | FK church; unique `(church, month)` | church |
| `OfferingCategory` | UUID | FK church, account PROTECT; unique `(church, code)` | church |
| `Budget` | UUID | FKs church/district/conference/department (nullable by level), account; conditional UniqueConstraints per level (church/dept/district/conference + year + account) | by level |
| `FinancialAuditLog` | UUID | FK transaction nullable, church, performed_by; named indexes | church |
| `BankReconciliation` | UUID | FK church, bank_account → Account, reconciled_by | church |
| `BankReconciliationItem` | BigAuto | FK reconciliation, transaction_line | via rec |
| `FinancialPeriod` | UUID | FK church, locked_by; unique `(church, year, month)` | church |
| `WorkingDay` | UUID | FK church, opened_by, closed_by; unique `(church, date)`; indexes church+status/date | church |
| `FinancialIdempotencyKey` | UUID | FK church, user, transaction nullable; unique `(church, user, action, idempotency_key)` | church |

---

### 4.7 `ledger` (1 model)

| Model | PK | Relations / constraints |
|-------|-----|-------------------------|
| `LedgerCategory` | UUID | FK church; debit/credit → Account PROTECT; unique `(church, code)`; **CheckConstraint** `ledger_category_debit_ne_credit`; transaction_type RECEIPT/EXPENSE/TRANSFER; flags requires_member, remit_to_district, is_active |

---

### 4.8 `remittance` (8 models)

| Model | PK | Key points | Tenant |
|-------|-----|------------|--------|
| `RemittancePolicy` | UUID | offering TITHE/COMBINED/WELFARE; scope GROSS_COLLECTION/SETTLEMENT_FROM_BELOW; **polymorphic** unit_type+unit_id; retain/remit percents; index on unit+offering+scope | polymorphic unit |
| `RemittancePolicyAuditLog` | UUID | CREATE/UPDATE/DEACTIVATE; FK policy, changed_by | via policy |
| `SettlementBatch` | UUID | DRAFT/POSTED/VOID; from/to unit_type+id; period + amounts | polymorphic |
| `SettlementLine` | UUID | FK batch; source_transaction SET_NULL | via batch |
| `WelfareContribution` | UUID | FK church, member, transaction; indexes church/member+date | church |
| `WelfareAssistanceCase` | UUID | statuses PENDING…CANCELLED; UniqueConstraint `remittance_welfare_case_number_unique` `(church, case_number)`; many user FKs; disbursement_transaction | church |
| `WelfareCaseAttachment` | UUID | FK case, uploaded_by | via case |
| `WelfareMemberLedger` | UUID | entry_type CONTRIBUTION/REQUEST/DISBURSEMENT/ADJUSTMENT; direction IN/OUT/NEUTRAL | church |

Unit types: `CHURCH`, `DISTRICT`, `CONFERENCE`, `UNION`, `GENERAL_CONFERENCE`.

---

### 4.9 `payroll` (13 models)

| Model | PK | Key points | Tenant |
|-------|-----|------------|--------|
| `PayComponentType` | UUID | unique `(host_church, code)` | host_church |
| `DeductionType` | UUID | calculation_method FIXED/PERCENT_*/COMPUTED; unique `(host_church, code)` | host_church |
| `PayrollTaxTable` | UUID | FK host_church | host_church |
| `PayrollTaxBand` | UUID | FK tax_table | via table |
| `StatutoryContributionRule` | UUID | unique `(host_church, code, effective_from)` | host_church |
| `Employee` | UUID | polymorphic paying unit; FK host_church, member, department; **O2O** user; unique `(host_church, employee_number)`; encrypted TIN/SSNIT/bank; status ACTIVE/SUSPENDED/TERMINATED | host_church + unit |
| `EmployeeCompensation` | UUID | FK employee | via emp |
| `EmployeeCompensationLine` | UUID | FK compensation, pay_component, deduction_type | via comp |
| `EmployeeLoan` | UUID | status ACTIVE/PAID/CANCELLED | via emp |
| `PayrollRun` | UUID | `reference` unique; status DRAFT…VOID; polymorphic paying unit; FKs host_church, transaction, payment_transaction, approvers; unique `(host_church, paying_unit_type, paying_unit_id, year, month)` | host_church + unit |
| `PayrollLine` | UUID | unique `(payroll_run, employee)` | via run |
| `PayrollLineItem` | UUID | item_type EARNING/DEDUCTION/EMPLOYER | via line |
| `PayrollRunAuditLog` | UUID | CREATE/CALCULATE/APPROVE/REJECT/POST/PAY/VOID/REOPEN/REVERSE/EXPORT | via run |

---

### 4.10 `assets` (8 models)

| Model | PK | Key points | Tenant |
|-------|-----|------------|--------|
| `AssetCategoryTemplate` | UUID | platform; `code` unique; GRA 1–4; depreciation STRAIGHT_LINE/DECLINING_BALANCE | platform |
| `AssetCategory` | UUID | FK church, template; unique `(church, code)` | church |
| `DepreciationPolicy` | UUID | **O2O** church → `depreciation_policy` | church |
| `FixedAsset` | UUID | status DRAFT…REJECTED; unique `(church, asset_code)`; FKs category, custodian_member, acquisition/disposal transactions, approvers | church |
| `AssetDepreciationEntry` | UUID | unique `(asset, period_year, period_month)`; FK transaction | via asset |
| `AssetMaintenanceLog` | UUID | FK asset | via asset |
| `AssetAuditLog` | UUID | FK asset, user; index `(asset, -created_at)` | via asset |
| `AssetPolicyAuditLog` | UUID | POLICY_UPDATE/CATEGORY_*; FK church | church |

---

### 4.11 `meetings` (7 models)

Enums: MeetingStatus SCHEDULED/HELD/CANCELLED; MeetingType BOARD/CHURCH_BOARD/DEACONS/DEPARTMENT/GENERAL/OTHER; MinutesStatus DRAFT/PENDING_APPROVAL/APPROVED/REJECTED; ActionItemStatus OPEN/IN_PROGRESS/DONE; EventType WORSHIP/SABBATH_SCHOOL/PRAYER/DEPARTMENT/OTHER.

| Model | PK | Constraints | Tenant |
|-------|-----|-------------|--------|
| `Meeting` | UUID | indexes church+scheduled/minutes/type | church |
| `MeetingAttendance` | UUID | unique `(meeting, member)` | via meeting |
| `MeetingAttachment` | UUID | FK meeting | via meeting |
| `MeetingActionItem` | UUID | FK meeting, assigned_to member | via meeting |
| `MeetingDecision` | UUID | FK meeting | via meeting |
| `AttendanceEvent` | UUID | FK church, optional meeting/department | church |
| `AttendanceRecord` | UUID | unique `(event, member)` | via event |

---

### 4.12 `announcements` (4 models)

| Model | PK | Key points | Tenant |
|-------|-----|------------|--------|
| `Announcement` | BigAuto | visibility general/church; status PENDING/APPROVED/REJECTED/ARCHIVED; FK church nullable; named indexes | church (nullable if general) |
| `AnnouncementImage` | BigAuto | FK announcement | via ann |
| `AnnouncementView` | BigAuto | unique `(announcement, user)` | via ann |
| `AnnouncementAuditLog` | UUID | CREATE/UPDATE/APPROVE/REJECT/ARCHIVE/PIN/UNPIN/EXPORT | church |

---

### 4.13 `reports` (2) · `dashboard` (1)

| Model | PK | Key points |
|-------|-----|------------|
| `ReportExportJob` | UUID | status PENDING/RUNNING/COMPLETE/FAILED; FK user |
| `ReportAccessAuditLog` | UUID | RUN/EXPORT; FK user, church nullable |
| `Notification` | BigAuto | category INFO/FINANCE/MEMBER/SYSTEM; FK user |

---

## 5. Relationship summary (Current)

### One-to-one
| From | To |
|------|-----|
| `User.member` | `Member` |
| `Employee.user` | `User` |
| `TenantSubscription.church` | `Church` |
| `DepreciationPolicy.church` | `Church` |

### Many-to-many
| From | To | Through |
|------|-----|---------|
| `User.managed_denominations` | `Denomination` | implicit M2M table |
| `Record.images` | `RecordImage` | implicit M2M |
| `History.images` | `HistoryImage` | implicit M2M |

### Notable self-FK
| Model | Field |
|-------|-------|
| `Transaction.reversal_of` | self SET_NULL `reversals` |

---

## 6. Gaps vs AGENTS.md / DATABASE_STANDARDS (explicit)

| Planned | Current |
|---------|---------|
| Soft-delete `is_deleted` / `deleted_at` / `deleted_by` | Absent — use status/void/archive/`is_active` |
| UUID for all enterprise entities | Mixed — several BigAuto legacy PKs |
| Division hierarchy level | Denomination (SaaS) + GeneralConference (org) |
| Visitors / inventory / procurement / petty cash tables | Not present |
| Universal audit columns on every table | Domain audit tables instead |
| Generic Organization model | Concrete hierarchy tables |
| Fund as first-class entity | Fund **tags** on `TransactionLine` + account types |
| giving/budgets schemas | Feature/UI only; Budget in transactions |

---

## 7. Recommended future schema evolution

1. Soft-delete mixin for members/org/announcements (not finance — keep void/reversal).  
2. Migrate remaining BigAuto PKs to UUID carefully (or document permanent exceptions).  
3. Tighten nullable `Conference.denomination` / `User.denomination` where product allows.  
4. Reduce polymorphic UUID pairs or add validation tables / content-type constraints.  
5. Align `permissions.RolePermission.role` choices with expanded UserRole set via migration.  
6. Unify remittance cutoff vs settlement ownership in schema docs and eventually data model.  
7. Do **not** invent AGENTS tables without approved migrations.

---

## 8. Related documents

- `ENTITY_RELATIONSHIP.md` — diagrams  
- `MIGRATION_HISTORY.md` — how schema evolved  
- `docs/AI_CONTEXT/DATABASE_MAP.md` — agent-oriented map  
- `docs/ARCHITECTURE/MULTI_TENANCY.md` — tenancy semantics  
