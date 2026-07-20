# ChurchHub — Entity Relationship Diagrams

**Audience:** Architects, AI agents  
**Source of truth:** Live Django models  
**Companions:** `DATABASE_SCHEMA.md`, `MIGRATION_HISTORY.md`, `docs/AI_CONTEXT/DATABASE_MAP.md`

Diagrams show **Current** relationships. Planned AGENTS entities that do not exist (Visitor, Inventory, Division, soft-delete) are listed under gaps — not drawn as tables.

---

## 1. Organization hierarchy + Denomination (Current)

```mermaid
erDiagram
  Denomination ||--o{ Conference : "denomination FK"
  GeneralConference ||--o{ Union : contains
  Union ||--o{ Conference : "union FK optional"
  Conference ||--o{ Zone : contains
  Zone ||--o{ District : contains
  District ||--o{ Church : contains
  Church ||--o| TenantSubscription : "OneToOne"
  SubscriptionPlan ||--o{ TenantSubscription : plan
  SubscriptionPlan ||--o{ Denomination : "default_plan optional"

  Denomination {
    uuid id PK
    slug code UK
  }
  GeneralConference {
    uuid id PK
    string name UK
    string code UK
  }
  Union {
    uuid id PK
  }
  Conference {
    uuid id PK
    uuid denomination_id FK
    uuid union_id FK
  }
  Zone {
    uuid id PK
  }
  District {
    uuid id PK
  }
  Church {
    uuid id PK
    bool is_active
    bool financials_provisioned
  }
  TenantSubscription {
    uuid id PK
    string status
  }
```

**Notes**

- Church has no direct denomination column; it is derived via district → zone → conference.  
- `OrganizationAuditLog` references entities polymorphically (`entity_type` / `entity_id`) — not drawn as FKs.

---

## 2. User, permissions, and scope (Current)

```mermaid
erDiagram
  User ||--o| Member : "OneToOne member"
  User }o--o| Church : "home church"
  User }o--o| District : scope_district
  User }o--o| Zone : scope_zone
  User }o--o| Conference : scope_conference
  User }o--o| Union : scope_union
  User }o--o| GeneralConference : scope_gc
  User }o--o| Denomination : denomination
  User }o--o{ Denomination : "M2M managed_denominations"
  User ||--o{ UserActivityLog : logs
  User ||--o{ UserInvitation : "invited_by"
  User ||--o{ PermissionOverride : overrides
  Permission ||--o{ RolePermission : grants
  Permission ||--o{ PermissionOverride : overrides
  User ||--o{ PermissionAuditLog : performed_by

  User {
    uuid id PK
    string role
    string scope_level
    bool is_platform_user
    string platform_role
    bool mfa_enabled
  }
  Permission {
    uuid id PK
    string codename UK
  }
  RolePermission {
    uuid id PK
    string role
  }
```

**Notes**

- Role × permission matrix is global; church isolation is applied in queries, not by FK on Permission.  
- Platform operators use `is_platform_user` + `platform_role` + managed denominations.

---

## 3. Membership domain (Current)

```mermaid
erDiagram
  Church ||--o{ Member : owns
  Church ||--o{ Department : owns
  Church ||--o{ Family : owns
  Church ||--o{ Occupation : owns
  Church ||--o{ SpiritualGift : owns
  Church ||--o{ LeadershipRole : owns
  Church ||--o{ MemberAuditLog : owns
  Member }o--o| Department : department
  Member }o--o| Family : family
  Member }o--o| Occupation : occupation
  Family }o--o| Member : "head"
  Member ||--o{ MemberTransfer : transfers
  Church ||--o{ MemberTransfer : "from_church"
  Church ||--o{ MemberTransfer : "to_church"
  Member ||--o{ Record : records
  Member ||--o{ History : history
  Record }o--o{ RecordImage : images
  History }o--o{ HistoryImage : images
  Member ||--o{ MemberSpiritualGift : gifts
  SpiritualGift ||--o{ MemberSpiritualGift : assigned
  Member ||--o{ LeadershipRole : roles
  Department ||--o{ LeadershipRole : optional

  Member {
    uuid id PK
    string membership_status
    bool is_active
    string phone
    string membership_number
  }
  MemberTransfer {
    uuid id PK
    string status
  }
```

**Unique (non-empty):** `(church, phone)`, `(church, membership_number)`.

**Gap vs AGENTS:** No `Visitor` entity; attendance headcount only on `AttendanceEvent`.

---

## 4. Finance and ledger (Current)

```mermaid
erDiagram
  Church ||--o{ Account : owns
  Church ||--o{ Transaction : owns
  Church ||--o{ MonthlyCutoff : owns
  Church ||--o{ OfferingCategory : owns
  Church ||--o{ Budget : "church-level"
  Church ||--o{ FinancialPeriod : owns
  Church ||--o{ WorkingDay : owns
  Church ||--o{ FinancialAuditLog : owns
  Church ||--o{ FinancialIdempotencyKey : owns
  Church ||--o{ BankReconciliation : owns
  Church ||--o{ LedgerCategory : owns
  Member ||--o{ Transaction : "optional"
  Transaction ||--o{ TransactionLine : lines
  Account ||--o{ TransactionLine : posted_to
  Account ||--o{ OfferingCategory : maps
  Account ||--o{ Budget : budgeted
  Account ||--o{ BankReconciliation : bank_account
  Transaction ||--o| Transaction : "reversal_of"
  LedgerCategory ||--o{ Transaction : "optional template"
  LedgerCategory }o--|| Account : default_debit
  LedgerCategory }o--|| Account : default_credit
  BankReconciliation ||--o{ BankReconciliationItem : items
  TransactionLine ||--o{ BankReconciliationItem : matched
  District ||--o{ Budget : "district-level"
  Conference ||--o{ Budget : "conference-level"
  Department ||--o{ Budget : "department-level"

  Account {
    uuid id PK
    string account_type
    string code
  }
  Transaction {
    uuid id PK
    string transaction_type
    string approval_status
    bool locked
    bool is_voided
  }
  TransactionLine {
    int id PK
    decimal amount
    string fund
  }
  LedgerCategory {
    uuid id PK
    string code
  }
```

**Integrity highlights**

- Lines must balance in application code (sum amounts = 0).  
- Ledger debit ≠ credit enforced by CheckConstraint.  
- Transaction reference unique per church.  
- Budget uniqueness conditional on level.

---

## 5. Payroll (Current)

```mermaid
erDiagram
  Church ||--o{ Employee : host_church
  Church ||--o{ PayrollRun : host_church
  Church ||--o{ PayComponentType : owns
  Church ||--o{ DeductionType : owns
  Church ||--o{ PayrollTaxTable : owns
  Church ||--o{ StatutoryContributionRule : owns
  Member ||--o{ Employee : optional
  User ||--o| Employee : "OneToOne optional"
  Department ||--o{ Employee : optional
  Employee ||--o{ EmployeeCompensation : comps
  EmployeeCompensation ||--o{ EmployeeCompensationLine : lines
  PayComponentType ||--o{ EmployeeCompensationLine : optional
  DeductionType ||--o{ EmployeeCompensationLine : optional
  Employee ||--o{ EmployeeLoan : loans
  PayrollRun ||--o{ PayrollLine : lines
  Employee ||--o{ PayrollLine : employee
  PayrollLine ||--o{ PayrollLineItem : items
  PayrollRun ||--o{ PayrollRunAuditLog : audit
  PayrollRun }o--o| Transaction : "accrual txn"
  PayrollRun }o--o| Transaction : "payment txn"
  PayrollTaxTable ||--o{ PayrollTaxBand : bands

  Employee {
    uuid id PK
    string paying_unit_type
    uuid paying_unit_id
    string status
  }
  PayrollRun {
    uuid id PK
    string status
    string reference UK
    string paying_unit_type
    uuid paying_unit_id
  }
```

**Note:** `paying_unit_type` + `paying_unit_id` are **not** FKs to hierarchy tables.

---

## 6. Assets (Current)

```mermaid
erDiagram
  AssetCategoryTemplate ||--o{ AssetCategory : template
  Church ||--o{ AssetCategory : owns
  Church ||--o| DepreciationPolicy : "OneToOne"
  Church ||--o{ FixedAsset : owns
  Church ||--o{ AssetPolicyAuditLog : owns
  AssetCategory ||--o{ FixedAsset : category
  Member ||--o{ FixedAsset : custodian
  FixedAsset ||--o{ AssetDepreciationEntry : entries
  FixedAsset ||--o{ AssetMaintenanceLog : maintenance
  FixedAsset ||--o{ AssetAuditLog : audit
  FixedAsset }o--o| Transaction : acquisition
  FixedAsset }o--o| Transaction : disposal
  AssetDepreciationEntry }o--o| Transaction : depreciation_posting

  FixedAsset {
    uuid id PK
    string asset_code
    string status
  }
```

---

## 7. Remittance and welfare (Current)

```mermaid
erDiagram
  RemittancePolicy ||--o{ RemittancePolicyAuditLog : audit
  SettlementBatch ||--o{ SettlementLine : lines
  SettlementLine }o--o| Transaction : source
  Church ||--o{ WelfareContribution : owns
  Church ||--o{ WelfareAssistanceCase : owns
  Church ||--o{ WelfareMemberLedger : owns
  Member ||--o{ WelfareContribution : optional
  Member ||--o{ WelfareAssistanceCase : requests
  Member ||--o{ WelfareMemberLedger : ledger
  WelfareAssistanceCase ||--o{ WelfareCaseAttachment : files
  WelfareContribution }o--o| Transaction : linked
  WelfareAssistanceCase }o--o| Transaction : disbursement
  WelfareMemberLedger }o--o| WelfareContribution : optional
  WelfareMemberLedger }o--o| WelfareAssistanceCase : optional
  WelfareMemberLedger }o--o| Transaction : optional

  RemittancePolicy {
    uuid id PK
    string unit_type
    uuid unit_id
    string offering_type
    decimal retain_percent
    decimal remit_percent
  }
  SettlementBatch {
    uuid id PK
    string from_unit_type
    uuid from_unit_id
    string to_unit_type
    uuid to_unit_id
    string status
  }
```

**Dual remittance note:** `transactions.MonthlyCutoff` also tracks church-month remit payables — related operationally, separate table (see `DATABASE_SCHEMA.md` / Architecture workflow docs).

---

## 8. SiteControl / SaaS (Current)

```mermaid
erDiagram
  SiteSettings }o--o| SubscriptionPlan : application_default_plan
  Denomination }o--o| SubscriptionPlan : default_plan
  SubscriptionPlan ||--o{ TenantSubscription : subscriptions
  PlatformPaymentMethod ||--o{ TenantSubscription : optional
  Church ||--o| TenantSubscription : "OneToOne"
  Denomination ||--o{ TenantApplication : applications
  District ||--o{ TenantApplication : optional
  Church ||--o{ TenantApplication : created_church
  UserInvitation ||--o{ TenantApplication : invitation
  User ||--o{ PlatformAuditLog : actor
  Denomination ||--o{ PlatformAuditLog : optional
  User ||--o{ PlatformAnnouncement : created_by

  TenantApplication {
    uuid id PK
    string status
    string application_type
  }
  SiteSettings {
    int singleton_id PK
  }
```

---

## 9. Meetings and attendance (Current)

```mermaid
erDiagram
  Church ||--o{ Meeting : owns
  Church ||--o{ AttendanceEvent : owns
  Department ||--o{ Meeting : optional
  Department ||--o{ AttendanceEvent : optional
  Meeting ||--o{ MeetingAttendance : attendees
  Meeting ||--o{ MeetingAttachment : files
  Meeting ||--o{ MeetingActionItem : actions
  Meeting ||--o{ MeetingDecision : decisions
  Member ||--o{ MeetingAttendance : member
  Member ||--o{ MeetingActionItem : assigned_to
  Meeting ||--o{ AttendanceEvent : optional_link
  AttendanceEvent ||--o{ AttendanceRecord : records
  Member ||--o{ AttendanceRecord : member

  Meeting {
    uuid id PK
    string status
    string minutes_status
  }
  AttendanceEvent {
    uuid id PK
    string event_type
    int headcount
  }
```

---

## 10. Announcements, reports, dashboard (Current)

```mermaid
erDiagram
  Church ||--o{ Announcement : "nullable for general"
  User ||--o{ Announcement : created_by
  Announcement ||--o{ AnnouncementImage : images
  Announcement ||--o{ AnnouncementView : views
  User ||--o{ AnnouncementView : viewer
  Announcement ||--o{ AnnouncementAuditLog : audit
  User ||--o{ ReportExportJob : jobs
  User ||--o{ ReportAccessAuditLog : access
  Church ||--o{ ReportAccessAuditLog : optional
  User ||--o{ Notification : notifications
```

Distinct from `PlatformAnnouncement` (sitecontrol).

---

## 11. Cross-domain financial posting (Current)

```mermaid
flowchart LR
  PAY[PayrollRun] -->|post / pay| TXN[Transaction + Lines]
  AST[FixedAsset / Depreciation] -->|capitalize / dispose / depreciate| TXN
  REM[SettlementBatch / Welfare] -->|post / disburse| TXN
  LED[LedgerCategory] -->|guided entry| TXN
  GIV[giving app] -.->|read only| TXN
  BUD[budgets app] -.->|UI over| Budget[transactions.Budget]
  Budget --> Account
  TXN --> Account
```

---

## 12. Planned entities (AGENTS.md) — not in ER diagrams

Do **not** assume these tables exist:

| Planned concept | Live reality |
|-----------------|--------------|
| Division | Denomination + GeneralConference |
| Generic Organization | Concrete hierarchy models |
| Visitor | AttendanceEvent.headcount only |
| Inventory / StockMovement | Absent |
| Procurement / PO | Absent |
| Petty cash | Absent |
| Soft-delete columns | Absent |
| Unified AuditEvent | Multiple domain audit tables |

---

## 13. Recommended diagram evolution

1. After soft-delete lands, annotate lifecycle fields on Member/Church/Announcement.  
2. If polymorphic units gain FKs or ContentType, redraw remittance/payroll edges.  
3. When `/api/v1/` arrives, ER stays the same — API must not invent tables.  
4. Keep `transactions` as the single financial hub in all future diagrams.

---

## 14. Related documents

- Field-level inventory: `DATABASE_SCHEMA.md`  
- Migration chronology: `MIGRATION_HISTORY.md`  
- Tenancy semantics: `docs/ARCHITECTURE/MULTI_TENANCY.md`  
- Workflow posting rules: `docs/ARCHITECTURE/WORKFLOW_ARCHITECTURE.md`  
