# ChurchHub — Database Map (Live Schema)

**Audience:** AI agents and engineers  
**Source of truth:** Django `models.py` files in each app  
**Companions:** `SYSTEM_OVERVIEW.md`, `BUSINESS_LOGIC.md`, `CODING_GUIDE.md`, root `DATABASE_DESIGN.md`, `DATABASE_STANDARDS.md`

This map summarizes **models that exist in code**. It does not invent tables from `AGENTS.md`. For full field lists, read the cited `models.py`. Nested `docs/DATABASE/DATABASE_SCHEMA.md` may still be empty — use this file + models.

---

## 1. Engine and defaults

| Setting | Behavior |
|---------|----------|
| Production | PostgreSQL via `DATABASE_URL` (required on Render) |
| Explicit PG | `DB_ENGINE=postgresql` + `DB_*` vars |
| Local default | SQLite (`db.sqlite3`) |
| Default auto field | `BigAutoField` (project default); most domain models override with UUID PK |

---

## 2. Tenancy and hierarchy ER (conceptual)

```
sitecontrol.Denomination
        │
        ▼ (FK)
organization.Conference ──► Union ──► GeneralConference
        │
        ▼
      Zone → District → Church  ◄── operational tenant
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   members.*           transactions.*          announcements.*
   meetings.*          payroll.* (host)        assets.*
   ledger.*            remittance.* (polymorphic units)
   budgets UI → transactions.Budget
   giving UI → reads TransactionLine
```

**SaaS subscription:** `sitecontrol.TenantSubscription` OneToOne → `Church`.

**No models named:** `Organization`, `Division`, `Visitor`, `InventoryItem`, `PettyCash`, soft-delete mixins.

---

## 3. Primary key patterns

| Pattern | Examples |
|---------|----------|
| UUID PK | Most domain models (`Member`, `Church`, `Transaction`, `User`, …) |
| Integer / BigAuto | Some legacy / singleton-style models (e.g. parts of announcements/notifications/site settings — verify in model before assuming UUID) |

Agents must check the model before writing FK types.

---

## 4. App: `organization`

**File:** `organization/models.py`

| Model | Key fields / relationships |
|-------|----------------------------|
| `GeneralConference` | UUID; `name` unique; `code` unique |
| `Union` | UUID; `name`; `code`; FK → `GeneralConference`; unique `(name, general_conference)` |
| `Conference` | UUID; `name` unique; `code` unique; FK → `Union` (nullable); FK → `sitecontrol.Denomination` (nullable, PROTECT) |
| `Zone` | UUID; FK → `Conference`; unique name/code per conference |
| `District` | UUID; FK → `Zone`; unique name/code per zone |
| `Church` | UUID; FK → `District`; `address`; `is_active`; `financials_provisioned`; unique name/code per district |
| `ChurchHistoryEntry` | UUID; FK → `Church`; title/body/event_date/category/location/tags; created_by/updated_by |
| `OrganizationAuditLog` | Org change audit |

Church properties (not columns): `zone`, `conference`, `union`, `general_conference`, `denomination`.

---

## 5. App: `accounts`

**File:** `accounts/models.py`  
**AUTH_USER_MODEL:** `accounts.User`

| Model | Key fields / relationships |
|-------|----------------------------|
| `User` | UUID PK; Django `AbstractUser` fields; `role`; `scope_level`; FK `church`; FKs `scope_district` / `scope_zone` / `scope_conference` / `scope_union` / `scope_general_conference`; OneToOne `member` → `members.Member`; `is_platform_user`; `platform_role`; FK `denomination`; M2M `managed_denominations`; `mfa_enabled` (**stub**); `phone` |
| `UserActivityLog` | User activity audit |
| `UserInvitation` | Invitation workflow |

---

## 6. App: `permissions`

**File:** `permissions/models.py`

| Model | Purpose |
|-------|---------|
| `Permission` | Permission catalog (codenames) |
| `RolePermission` | Role × permission matrix grants |
| `PermissionOverride` | Per-user grant/deny overrides |
| `PermissionAuditLog` | Permission change audit |

Runtime defaults also come from `permissions/registry.py` when matrix rows are missing.

---

## 7. App: `members`

**File:** `members/models.py`

### Enums (exact string values)

| Enum | Values |
|------|--------|
| `Gender` | `Male`, `Female` |
| `MaritalStatus` | `Single`, `Married`, `Widowed`, `Divorced` |
| `MembershipStatus` | `Active`, `Inactive`, `Transferred`, `Deceased` |
| `TransferStatus` | `Pending`, `Completed`, `Rejected` |
| `RecordType` | `Baptism`, `Marriage`, `Funeral`, `Meeting`, `Transfer`, `Other` |
| `RecordStatus` | `Active`, `Archived` |

Age groups (computed, not a stored enum on Member): `CHILD`, `TEEN`, `YOUTH`, `ADULT`, `SENIOR`.

### Models

| Model | Key fields / relationships |
|-------|----------------------------|
| `Department` | UUID; FK `church`; `name`; … |
| `Family` | UUID; FK `church`; `name`; optional FK `head` → Member; unique `(church, name)` |
| `Occupation` | UUID; FK `church`; … |
| `Member` | UUID; FK `church`, optional `occupation` / `department` / `family`; `first_name`, `last_name`; `gender`; `marital_status`; `date_of_birth`; `date_joined`; `membership_status`; `is_active`; `membership_number`; `phone`; `address`; baptism fields; `profile_picture`; `created_by`; timestamps |
| `MemberTransfer` | UUID; FK `member`, `from_church`, `to_church`; status; approval metadata |
| `Record` / `RecordImage` | Member records + images |
| `History` / `HistoryImage` | Membership history events + images |
| `SpiritualGift` / `MemberSpiritualGift` | Gift catalog + M2M-style link |
| `LeadershipRole` | FK church/member; optional department; `title`; `start_date` / `end_date`; `is_active` |
| `MemberAuditLog` | Member audit |

**Constraints on Member:** unique non-empty `(church, phone)`, unique non-empty `(church, membership_number)`.

**Indexes:** church+active, church+status, church+name, church+phone, etc.

---

## 8. App: `transactions` (books of record)

**File:** `transactions/models.py`

| Model | Key fields / relationships |
|-------|----------------------------|
| `Account` | UUID; FK `church`; `name`; `code`; `account_type` (see below); `is_active` |
| `Transaction` | UUID; `reference`; `transaction_type`; `date`; `description`; FK `church`; optional FK `member`; `approval_status`; `locked`; void fields; `reversal_of` self-FK; `created_by` / `approved_by` / `approved_at`; optional FK `ledger_category` |
| `TransactionLine` | FK `transaction`, `account`; `amount` Decimal; optional `fund` |
| `MonthlyCutoff` | UUID; FK `church`; `month`; tithe/combined totals; `transferred` |
| `OfferingCategory` | UUID; FK `church`, `account`; `name`; `code`; `remit_to_district`; `is_active` |
| `Budget` | Levels CHURCH/DEPARTMENT/DISTRICT/CONFERENCE; year; org FKs; FK `account`; `amount` |
| `FinancialAuditLog` | Financial audit |
| `BankReconciliation` / `BankReconciliationItem` | Bank reconciliation |
| `FinancialPeriod` | Year/month period; `is_locked` |
| `WorkingDay` | Business date; status OPEN/CLOSED |
| `FinancialIdempotencyKey` | Idempotent financial operations |

### Account types (choices on `Account.account_type`)

Includes: `TITHE`, `COMBINED`, `INCOME`, `EXPENSE`, `DISTRICT_PAYABLE`, `TITHE_REMIT_PAYABLE`, `COMBINED_REMIT_PAYABLE`, `COMBINED_RETENTION`, `WELFARE_FUND`, `REMITTANCE_RECEIVABLE`, payroll-related expense/payable types, `BANK`, `CASH`, `FIXED_ASSET`, `ACCUMULATED_DEPRECIATION`, `DEPRECIATION_EXPENSE`.

### Transaction types

`RECEIPT`, `EXPENSE`, `TRANSFER`, `PAYROLL`, `CAPITAL`

### Approval statuses

`PENDING`, `APPROVED`, `REJECTED`

### Line fund choices

`OPERATIONAL`, `TITHE_TRUST`, `COMBINED_TRUST`, `COMBINED_RETENTION`, `WELFARE` (may be blank)

### Important integrity rules (enforced in code / constraints)

- Unique account name per church; unique non-empty code per church  
- Lines must balance to zero  
- Line account church = transaction church  
- Locked transactions reject line edits  

---

## 9. App: `ledger`

**File:** `ledger/models.py`

| Model | Purpose |
|-------|---------|
| `LedgerCategory` | Posting template: church, code, name, transaction_type (`RECEIPT`/`EXPENSE`/`TRANSFER`), default debit/credit `transactions.Account`, narration, `requires_member`, `remit_to_district`, `is_active`, `sort_order` |

Constraint: debit account ≠ credit account. Unique `(church, code)`.

**Not a second general ledger.** Posted books remain `transactions.Transaction` / `TransactionLine`.

---

## 10. Apps with no (or empty) models

| App | Schema reality |
|-----|----------------|
| `budgets` | Empty `models.py` — uses `transactions.Budget` |
| `giving` | No models — reads transactions |
| `portal` | No models — self-service over other apps |
| `admin_custom` | No domain models |
| `dashboard` | `Notification` only |

---

## 11. App: `dashboard`

**File:** `dashboard/models.py`

| Model | Purpose |
|-------|---------|
| `Notification` | User/church notifications for dashboard |

---

## 12. App: `remittance`

**File:** `remittance/models.py`

| Model | Key fields |
|-------|------------|
| `RemittancePolicy` | UUID; `offering_type` TITHE/COMBINED/WELFARE; `application_scope`; polymorphic `unit_type` + `unit_id`; `retain_percent` / `remit_percent` (must sum 100); effective dates; `is_active` |
| `RemittancePolicyAuditLog` | Policy audit snapshots |
| `SettlementBatch` | UUID; offering; from/to unit type+id; period; amounts; status DRAFT/POSTED/VOID |
| `SettlementLine` | Lines on a batch |
| `WelfareContribution` | Welfare pool contributions |
| `WelfareAssistanceCase` | Assistance cases + workflow statuses |
| `WelfareCaseAttachment` | Attachments |
| `WelfareMemberLedger` | Per-member welfare ledger entries |

**Polymorphic units:** `unit_type` / `unit_id` (and settlement from/to) are **not** Django FKs — referential integrity is application-enforced.

---

## 13. App: `payroll`

**File:** `payroll/models.py`

| Model | Notes |
|-------|-------|
| `PayComponentType`, `DeductionType` | Compensation configuration |
| `PayrollTaxTable`, `PayrollTaxBand` | Tax bands |
| `StatutoryContributionRule` | Statutory rules |
| `Employee` | UUID; FK `host_church`; polymorphic `paying_unit_type`/`paying_unit_id`; optional FK `member`; optional OneToOne `user`; encrypted TIN/SSNIT/bank; employment fields; status ACTIVE/SUSPENDED/TERMINATED |
| `EmployeeCompensation` / `EmployeeCompensationLine` | Compensation structure |
| `EmployeeLoan` | Loans |
| `PayrollRun` | Status DRAFT/CALCULATED/APPROVED/REJECTED/POSTED/PAID/VOID; links to posted/payment transactions |
| `PayrollLine` / `PayrollLineItem` | Per-employee run lines |
| `PayrollRunAuditLog` | Run audit |

---

## 14. App: `assets`

**File:** `assets/models.py`

| Model | Notes |
|-------|-------|
| `AssetCategoryTemplate` | Platform-level templates |
| `AssetCategory` | Church categories |
| `DepreciationPolicy` | Depreciation rules |
| `FixedAsset` | Status DRAFT/PENDING_APPROVAL/ACTIVE/UNDER_REPAIR/DISPOSED/REJECTED; church-scoped asset register |
| `AssetDepreciationEntry` | Depreciation postings history |
| `AssetMaintenanceLog` | Maintenance |
| `AssetAuditLog` / `AssetPolicyAuditLog` | Audits |

---

## 15. App: `meetings`

**File:** `meetings/models.py`

| Model | Notes |
|-------|-------|
| `Meeting` | Status SCHEDULED/HELD/CANCELLED; minutes status DRAFT/PENDING_APPROVAL/APPROVED/REJECTED |
| `MeetingAttendance` | Unique `(meeting, member)`; `is_present` |
| `MeetingAttachment` | Files |
| `MeetingActionItem` | Action items |
| `MeetingDecision` | Decisions |
| `AttendanceEvent` | Worship/event attendance header; `headcount` for non-member visitors |
| `AttendanceRecord` | Unique `(event, member)` |

---

## 16. App: `announcements`

**File:** `announcements/models.py`

| Model | Notes |
|-------|-------|
| `Announcement` | Church-scoped announcements (approval/archive/pin patterns) |
| `AnnouncementImage` | Images |
| `AnnouncementView` | View tracking |
| `AnnouncementAuditLog` | Audit |

Distinct from `sitecontrol.PlatformAnnouncement`.

---

## 17. App: `reports`

**File:** `reports/models.py`

| Model | Notes |
|-------|-------|
| `ReportExportJob` | Async-capable export job records |
| `ReportAccessAuditLog` | Who accessed/exported reports |

---

## 18. App: `sitecontrol` (platform)

**File:** `sitecontrol/models.py`

| Model | Notes |
|-------|-------|
| `SiteSettings` | Singleton platform settings (SMTP, maintenance, security options, …) |
| `SubscriptionPlan` | Plan catalog |
| `PlatformPaymentMethod` | Payment methods |
| `TenantSubscription` | OneToOne → Church; status TRIAL/ACTIVE/SUSPENDED/EXPIRED; billing fields; `is_operational` property |
| `PlatformAuditLog` | Immutable platform audit |
| `PlatformAnnouncement` | Platform-wide announcements |
| `TenantApplication` | Public/apply workflow; status PENDING/APPROVED/REJECTED/WITHDRAWN; types EXISTING_DISTRICT/NEW_HIERARCHY; `contact_phone_normalized` for demo identity lock |
| `Denomination` | SaaS tenant boundary; branding; feature flags; `allow_institution_branding`; defaults |
| `MarketingSettings` | Singleton public inquiry, privacy consent, retention, website and sales-notification settings |
| `MarketingCampaign` | UUID campaign; status/period and UTM attribution metadata |
| `MarketingLead` | UUID platform sales inquiry; optional denomination/campaign; consent snapshot, assignment, lifecycle, notification delivery and anonymization metadata |
| `MarketingAsset` | UUID approval-controlled HTTPS link to externally hosted collateral |

---

## 19. Cross-app relationship cheat sheet

| From | To | Relationship |
|------|----|--------------|
| `User.church` | `Church` | Home church (nullable for hierarchy/platform) |
| `User.member` | `Member` | Optional OneToOne |
| `Member.church` | `Church` | Required |
| `Account.church` | `Church` | Required |
| `Transaction.church` | `Church` | Required |
| `Transaction.member` | `Member` | Optional |
| `TransactionLine.account` | `Account` | Required |
| `Transaction.ledger_category` | `LedgerCategory` | Optional |
| `LedgerCategory` debit/credit | `Account` | PROTECT |
| `Conference.denomination` | `Denomination` | Optional PROTECT |
| `TenantSubscription.church` | `Church` | OneToOne |
| `Employee.host_church` | `Church` | Required |
| `Employee.member` | `Member` | Optional |
| `Employee.user` | `User` | Optional OneToOne |
| `Budget` | Church / District / Conference / Department + Account | Level-dependent |
| Remittance / payroll units | Hierarchy rows | Polymorphic UUID (no FK) |

---

## 20. Soft delete and deletion policy (reality)

| Documented in AGENTS / DATABASE_STANDARDS | Live schema |
|-------------------------------------------|-------------|
| `is_deleted`, `deleted_at`, `deleted_by` | **Not present** on business models |
| Soft delete only | Members use `is_active` + `membership_status`; finance uses void/reversal; other domains use status/archive flags |

Agents must not write filters on `is_deleted` unless a future migration adds it.

---

## 21. Naming collisions (read carefully)

| Name | Meaning |
|------|---------|
| App `accounts` | Users / auth |
| Model `transactions.Account` | Chart of accounts |
| App `ledger` | Posting category templates |
| GL / journals | `transactions.Transaction` + `TransactionLine` |
| App `budgets` | UI layer |
| Model `transactions.Budget` | Budget rows |

---

## 22. How agents should use this map

1. Confirm the owning app and model in this file.  
2. Open the real `models.py` before adding fields or FKs.  
3. Follow existing UUID / church-FK / constraint patterns.  
4. For polymorphic `unit_type`/`unit_id`, validate in services — do not assume DB FK integrity.  
5. Prefer extending existing models over creating parallel “v2” tables.  
6. If AGENTS.md describes a table that is not listed here, it is **not implemented** — ask before inventing it.

---

## 23. Related documentation

| Topic | Document |
|-------|----------|
| Business rules on these tables | `BUSINESS_LOGIC.md` |
| How to query safely | `CODING_GUIDE.md` |
| Architecture context | `SYSTEM_OVERVIEW.md` |
| Design aspirations | `DATABASE_DESIGN.md`, `DATABASE_STANDARDS.md`, `AGENTS.md` |
| Audit findings | `CURSOR_AUDIT_REPORT.md` |
