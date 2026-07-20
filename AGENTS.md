# AGENTS.md

# ChurchHub Enterprise

Version: 2.0

Author: Lead Enterprise Architecture Team

---

# Mission

ChurchHub Enterprise is an enterprise-grade Church Management System (ChMS)
designed for churches of all sizes, supporting hierarchical administration
from the local church through districts, zones, conferences, and multi-conference
deployments.

The software must be:

- Secure
- Scalable
- Maintainable
- Auditable
- Extensible
- Production Ready

Every implementation decision should improve reliability,
maintainability, and user experience without sacrificing
existing functionality.

---

# AI Role

You are the Lead Software Architect for ChurchHub Enterprise.

Behave as an experienced architect with expertise in:

- Django
- PostgreSQL
- Enterprise Architecture
- Church Administration
- Financial Systems
- Accounting
- Reporting
- Security Engineering
- DevOps
- Database Design
- User Experience
- API Design

You are NOT simply generating code.

You are responsible for protecting the long-term health of the
entire application.

---

# Primary Objectives

Always prioritize:

1. Correctness
2. Stability
3. Backward Compatibility
4. Security
5. Maintainability
6. Performance
7. User Experience

Never prioritize speed over quality.

---

# Development Philosophy

Every change should leave the codebase better than it was before.

Prefer:

- Incremental improvements
- Reusable code
- SOLID principles
- Clean Architecture
- Domain Driven Design
- Explicit code
- Self-documenting code

Avoid:

- Quick fixes
- Technical debt
- Duplicate code
- Massive rewrites
- Hidden side effects

---

# Core Principles

Never:

- Break existing functionality.
- Rename models without approval.
- Rename database fields without approval.
- Remove business rules.
- Delete historical records.
- Delete migrations.
- Rewrite working modules without justification.
- Duplicate business logic.
- Introduce security vulnerabilities.
- Modify financial records silently.

Always:

- Explain proposed changes.
- Work in small reviewable commits.
- Test every change.
- Reuse existing utilities.
- Extend existing functionality whenever possible.
- Preserve backward compatibility.

---

# Architecture Principles

ChurchHub follows a layered architecture.

Presentation Layer

↓

Views

↓

Services

↓

Repositories / Managers

↓

Models

↓

Database

Views should remain thin.

Business rules belong in Services.

Database queries belong inside Managers or Repositories.

Templates should contain presentation logic only.

Never place business rules inside templates.

---

# Project Organization

Every Django app represents one business domain.

Example:

members/

    models.py

    managers.py

    services/

    repositories/

    validators/

    forms/

    selectors/

    api/

    permissions/

    reports/

    templates/

    tests/

Large applications should never become monolithic.

---

# Code Quality Standards

Follow:

PEP8

Black formatting

Type hints where practical

Docstrings on public APIs

Meaningful naming

Keep functions focused.

Maximum preferred function length:

50 lines

Maximum preferred class length:

300 lines

Maximum preferred view:

250 lines

Large services should be broken into smaller services.

---

# SOLID Principles

Apply all SOLID principles.

Single Responsibility

Open/Closed

Liskov Substitution

Interface Segregation

Dependency Inversion

Avoid tightly coupled code.

---

# DRY Principle

Never duplicate:

Validation

Business rules

Permission logic

Queries

Formatting

Utilities

Search existing implementations before creating new ones.

---

# Naming Standards

Use meaningful names.

Good:

MemberService

AttendanceRepository

BudgetValidator

TransferWorkflow

Poor:

Utils

Helper

DataManager

MiscFunctions

Avoid abbreviations.

---

# Error Handling

Never suppress exceptions silently.

Always:

Log errors.

Provide meaningful messages.

Raise appropriate exceptions.

Protect sensitive information.

---

# Logging

Log:

Authentication

Permission failures

Financial changes

Member transfers

Administrative actions

Report generation

Imports

Exports

Errors

Warnings

Critical failures

Never log passwords.

Never log sensitive personal information.

---

# Documentation Standards

Every major feature should include:

Updated documentation

Business rules

Developer notes

Migration notes

API documentation

User documentation

Architecture updates

Documentation is part of the feature.

---

# Definition of Done

A feature is NOT complete until:

✓ Code is clean

✓ Tested

✓ Reviewed

✓ Secure

✓ Documented

✓ Responsive

✓ Accessible

✓ Performs well

✓ Does not break existing functionality

---

# AI Workflow

Before implementing anything:

1. Understand the existing code.

2. Search for reusable logic.

3. Explain the proposed implementation.

4. Identify risks.

5. Wait for approval for major changes.

6. Implement incrementally.

7. Verify functionality.

8. Suggest future improvements.

Never assume requirements.

Ask questions when uncertain.

---

# AI Must Never

Never:

Invent database fields.

Invent business rules.

Generate fake migrations.

Ignore existing services.

Replace stable code unnecessarily.

Break APIs.

Duplicate logic.

Skip testing.

Guess requirements.

Perform large refactors without approval.

Delete historical data.

Bypass permission checks.

Ignore audit logging.

Modify financial data directly.

Hardcode configuration values.

Expose confidential information.

Always preserve enterprise quality.
# ============================================================================
# SECTION 2
# ORGANIZATION, CHURCH HIERARCHY & MEMBERSHIP DOMAIN
# ============================================================================

# Organization Hierarchy

ChurchHub Enterprise supports hierarchical church administration.

The hierarchy is:

Division
    ↓
Union
    ↓
Conference
    ↓
Zone
    ↓
District
    ↓
Local Church

All organizational data must respect this hierarchy.

Never allow a lower-level organization to access data belonging to another
organization unless explicitly authorized.

Always enforce hierarchy filtering in queries, APIs, reports, and dashboards.

---

# Organization Rules

Every organization shall have:

- Name
- Code
- Type
- Parent Organization
- Address
- GPS Coordinates (optional)
- Phone
- Email
- Status
- Date Created
- Created By
- Updated By

Organization types are fixed.

Never allow arbitrary hierarchy levels without approval.

---

# Multi-Tenancy

ChurchHub is a multi-tenant system.

Every business record belongs to an organization.

Examples:

Member

Attendance

Offering

Expense

Budget

Meeting

Department

Asset

Event

Visitor

Announcement

Every query involving church-owned data must be tenant-aware.

Never expose data belonging to another tenant.

Never trust client-side filtering.

Always enforce tenant isolation on the server.

---

# Permission Scope

Permissions operate within organizational boundaries.

Examples:

Church Clerk

→ Can manage members within their church only.

District Pastor

→ Can access churches inside their district.

Conference Administrator

→ Can access all districts in the conference.

Union Administrator

→ Can access conferences inside the union.

Division Administrator

→ Can access all subordinate organizations.

Super Administrator

→ Full system access.

Permission scope must always be validated.

---

# Organization Transfers

Support:

Church Transfer

District Transfer

Conference Transfer

Union Transfer

Every transfer must:

Maintain history.

Record previous organization.

Record new organization.

Record transfer reason.

Record approval.

Record approval date.

Record approving officer.

Never overwrite transfer history.

---

# Membership Domain

Members are the heart of the system.

Protect membership records carefully.

Never permanently delete members.

---

# Member Identity

Each member has:

Unique Member ID

First Name

Middle Name

Surname

Preferred Name

Gender

Date of Birth

Nationality

Marital Status

Occupation

Baptism Date

Profession of Faith Date

Membership Date

Photo

Signature (optional)

Status

Emergency Contact

Church

District

Zone

Conference

Union

Division

Each Member ID must be globally unique.

---

# Duplicate Prevention

Never create duplicate members.

Before creation check:

Name similarity

Birth date

Phone number

Email

Government ID (if configured)

Membership ID

Warn the user about possible duplicates.

---

# Membership Status

Support statuses including:

Visitor

Bible Student

Baptized Member

Profession of Faith

Missing

Inactive

Transferred

Removed

Deceased

Former Member

Suspended

Archived

Status changes must preserve history.

---

# Membership History

Track every significant event:

Baptism

Profession of Faith

Transfer In

Transfer Out

Ordination

Discipline

Restoration

Marriage

Death

Each event must include:

Date

Officer

Location

Notes

Supporting documents (optional)

Never delete historical events.

---

# Family Management

Support family grouping.

Family includes:

Head of Household

Spouse

Children

Dependents

Relationship Type

Family Address

Primary Contact

Members may belong to only one active family at a time unless explicitly supported.

---

# Contact Information

Support multiple:

Addresses

Phone Numbers

Email Addresses

Emergency Contacts

Preferred communication method

Do not overwrite historical contact information without audit.

---

# Leadership Roles

Members may hold multiple leadership roles.

Examples:

Elder

Pastor

Head Elder

Treasurer

Clerk

Youth Leader

Sabbath School Superintendent

Deacon

Deaconess

Personal Ministries Leader

Family Ministries Leader

Health Ministries Leader

Stewardship Leader

Communication Director

Role assignments require:

Start Date

End Date

Organization

Approval (optional)

History

---

# Departments

Support departments such as:

Sabbath School

Youth

Pathfinder

Adventurer

Children's Ministries

Women's Ministries

Men's Ministries

Stewardship

Publishing

Communication

Education

Health Ministries

Religious Liberty

Personal Ministries

Music

Prayer Ministry

Community Services

Family Ministries

Possibility Ministries

The department list should be configurable.

---

# Ministry Membership

A member may belong to multiple ministries.

Track:

Join Date

Role

Leader

Status

Attendance

Responsibilities

---

# Attendance

Attendance must support:

Sabbath Worship

Midweek Prayer

Youth Meetings

Committee Meetings

Camp Meetings

Evangelistic Meetings

Special Programs

Support:

Present

Absent

Excused

Visitor

Late

Attendance should support bulk entry.

Never duplicate attendance records.

---

# Visitors

Visitors are not members.

Track:

Name

Phone

Email

Address

Invited By

Visit Date

Interests

Follow-up Status

Assigned Elder

Assigned Bible Worker

Support visitor-to-member conversion while preserving visit history.

---

# Bible Studies

Track:

Student

Instructor

Lesson

Progress

Completion

Interests

Prayer Requests

Notes

Status

Generate follow-up reminders automatically where configured.

---

# Small Groups

Support:

Cell Groups

Prayer Bands

Bible Study Groups

Choirs

Ministry Teams

Track:

Leader

Members

Meeting Schedule

Attendance

Growth

---

# Spiritual Gifts

Support configurable gifts.

Examples:

Teaching

Leadership

Mercy

Administration

Hospitality

Evangelism

Music

Service

Counseling

Members may possess multiple gifts.

---

# Skills

Support recording professional skills.

Examples:

Doctor

Teacher

Engineer

Lawyer

Accountant

Electrician

Builder

Farmer

Musician

Useful for ministry planning and community outreach.

---

# Member Documents

Allow secure storage of:

Transfer Letters

Baptism Certificates

Marriage Certificates

Birth Certificates

Photos

Consent Forms

Background Checks (if required)

Documents must support permissions and versioning.

---

# Privacy

Sensitive member information must be protected.

Never expose:

Private phone numbers

Addresses

Birth dates

Emergency contacts

Personal notes

Medical information

Without appropriate permissions.

Apply the principle of least privilege.

---

# Search Standards

Support searching by:

Member ID

Name

Phone

Email

Family

Department

Church

District

Conference

Status

Leadership Role

Search should be fast and indexed where appropriate.

---

# Member Dashboard

Every member profile should provide a consolidated view of:

Personal Details

Family

Attendance

Giving Summary (permission-controlled)

Leadership Roles

Departments

Documents

Transfers

Membership History

Communication Log

Audit Trail

The dashboard should provide a complete, read-only timeline of the member's journey where permissions allow.

# END OF SECTION 2
# ============================================================================
# SECTION 3
# FINANCE, TREASURY, ACCOUNTING & ASSET MANAGEMENT
# ============================================================================

# Financial Philosophy

ChurchHub Enterprise must maintain complete financial integrity.

Financial records are permanent business records.

Never sacrifice accounting accuracy for convenience.

Every financial transaction must be:

- Traceable
- Auditable
- Reversible through approved adjustments
- Linked to a responsible user
- Time-stamped
- Protected from unauthorized modification

Never silently modify historical financial records.

---

# Accounting Principles

The accounting system follows Double-Entry Bookkeeping.

Every transaction must balance.

Total Debits = Total Credits

Never allow unbalanced journal entries.

Support:

- Accrual Accounting
- Cash Accounting (configurable)
- Fund Accounting
- Department Accounting
- Multi-Organization Accounting

---

# Chart of Accounts

Support configurable Chart of Accounts.

Minimum account categories:

Assets

Liabilities

Equity / Net Assets

Income

Expenses

Each account must include:

- Account Code
- Account Name
- Parent Account
- Account Type
- Normal Balance
- Organization
- Active Status
- Reporting Category

Never allow duplicate account codes within the same organization.

---

# Journal Entries

Every financial operation ultimately creates journal entries.

Journal Entries must include:

- Reference Number
- Posting Date
- Business Date
- Description
- Debit Account
- Credit Account
- Amount
- Currency
- Exchange Rate (optional)
- Created By
- Approved By
- Source Module
- Audit Reference

Journal entries are immutable after posting.

Corrections must be made through reversing entries.

---

# Business Date

The system shall support a configurable Business Date.

Business Date is independent of the server clock.

Reports, postings, and reconciliations use Business Date.

Never rely solely on client device time.

---

# Funds

Support multiple church funds.

Examples:

General Fund

Tithe Fund

Combined Offering

Mission Offering

Building Fund

Education Fund

Youth Fund

Welfare Fund

Disaster Relief Fund

Special Projects

Funds must remain historically accurate.

Fund balances should always reconcile.

---

# Tithes

Support recording:

Regular Tithe

Back Tithe

Special Tithe

Anonymous Tithe (where permitted)

Each tithe entry should support:

- Member
- Envelope Number
- Receipt Number
- Date
- Amount
- Payment Method
- Fund
- Notes

Do not allow duplicate receipt numbers.

---

# Offerings

Support configurable offering categories.

Examples:

Combined Offering

Mission Offering

Building Fund

Thanksgiving Offering

Harvest Offering

Youth Offering

Children's Ministries

Community Services

Special Campaign

Future offering types must be configurable.

---

# Donations

Support:

Individual Donations

Corporate Donations

Anonymous Donations

In-Kind Donations

Restricted Donations

Unrestricted Donations

Track:

Donor

Purpose

Restrictions

Receipt

Acknowledgment

---

# Receipts

Generate sequential receipts.

Receipt requirements:

Unique Number

Business Date

Cashier

Member/Donor

Amount

Payment Method

Status

Organization

Support:

Print

Email

PDF

Reprint with audit logging.

Never reuse receipt numbers.

---

# Payment Methods

Support:

Cash

Cheque

Bank Transfer

Mobile Money

Card

Online Payment

Electronic Wallet

Additional payment methods should be configurable.

---

# Expenses

Expense records must include:

Department

Vendor

Category

Invoice

Receipt

Approval

Payment Method

Funding Source

Supporting Documents

Status

Expenses require appropriate approval workflows.

---

# Budgets

Support budgeting at multiple levels.

Organization

Department

Project

Event

Ministry

Budget lifecycle:

Draft

Submitted

Approved

Locked

Archived

Budget revisions must preserve history.

---

# Budget Controls

Warn when spending exceeds budget.

Support:

Soft Limits

Hard Limits

Approval Overrides

Budget Transfers

Variance Analysis

Never silently exceed hard budget limits.

---

# Bank Accounts

Support multiple bank accounts.

Track:

Account Name

Bank

Branch

Account Number

Currency

Opening Balance

Current Balance

Status

Bank accounts must support reconciliation.

---

# Bank Reconciliation

Support:

Statement Import

Matching

Outstanding Items

Adjustments

Reconciliation Reports

Historical Reconciliations

Never delete completed reconciliations.

---

# Petty Cash

Support petty cash management.

Track:

Custodian

Float Amount

Expenses

Replenishments

Approvals

Current Balance

Audit History

---

# Treasury

Treasury should support:

Cash Position

Fund Balances

Cash Forecast

Liquidity Reports

Bank Transfers

Internal Transfers

Cash Counts

Variance Reports

---

# Procurement

Support:

Purchase Requests

Purchase Orders

Vendor Selection

Goods Receipt

Invoice Matching

Approvals

Vendor Payments

Three-way matching is preferred.

---

# Vendors

Vendor records include:

Name

Address

Phone

Email

Tax Information

Payment Terms

Status

Performance Notes

Support vendor history.

---

# Projects

Financial projects should support:

Budget

Income

Expenses

Funding Sources

Milestones

Progress

Reports

Projects may span multiple financial years.

---

# Grants

Support grant management.

Track:

Grantor

Award Date

Purpose

Restrictions

Reporting Deadlines

Balance

Expenditure

Compliance Notes

---

# Payroll

Payroll must support:

Employees

Pastors

Contract Workers

Allowances

Deductions

Taxes

Benefits

Loans

Net Pay

Payroll must integrate with accounting.

---

# Fixed Assets

Support asset lifecycle.

Asset Categories:

Land

Buildings

Furniture

Equipment

Vehicles

Electronics

Musical Instruments

Computers

Books

Other Assets

---

# Asset Information

Each asset includes:

Asset Code

Description

Category

Location

Department

Custodian

Purchase Date

Purchase Cost

Supplier

Warranty

Useful Life

Residual Value

Current Status

---

# Asset Lifecycle

Support:

Acquisition

Transfer

Maintenance

Repair

Depreciation

Revaluation

Disposal

Write-Off

Every stage requires audit history.

---

# Depreciation

Support methods:

Straight Line

Reducing Balance

Units of Production

Depreciation runs should be repeatable and auditable.

---

# Inventory

Inventory should support:

Church Supplies

Office Supplies

Books

Communion Supplies

Cleaning Materials

Media Equipment

Uniforms

Track:

Quantity

Unit Cost

Average Cost

Location

Minimum Stock

Maximum Stock

Reorder Level

---

# Stock Movements

Every movement records:

Issue

Receipt

Transfer

Adjustment

Loss

Damage

Return

No stock quantity may become negative unless explicitly configured.

---

# Events

Events should support financial tracking.

Examples:

Camp Meeting

Youth Congress

Evangelistic Campaign

Conference Session

Marriage Seminar

Family Life Weekend

Track:

Income

Expenses

Budget

Registrations

Sponsors

Donations

Financial Summary

---

# Financial Reports

Generate:

Trial Balance

General Ledger

Income Statement

Statement of Financial Position

Cash Flow Statement

Budget vs Actual

Fund Balance Report

Departmental Income & Expense

Bank Reconciliation Report

Asset Register

Depreciation Report

Inventory Valuation

Donation Summary

Giving Statements

Member Contribution History (permission-controlled)

Reports must support:

PDF

Excel

CSV

Print

---

# Financial Audit

Every financial action must record:

User

Business Date

Timestamp

Organization

Previous Value

New Value

Reason

IP Address (if available)

Approval Reference

Financial audit records are immutable.

---

# Financial Integrity Rules

Never:

Delete posted transactions.

Reuse receipt numbers.

Alter historical journals.

Modify reconciled bank records.

Allow negative fund balances unless configured.

Allow unbalanced journals.

Bypass approval workflows.

Always:

Validate permissions.

Maintain audit trails.

Preserve historical accuracy.

Support reversals instead of edits.

Ensure accounting remains balanced.

# END OF SECTION 3
# ============================================================================
# SECTION 4
# SECURITY, IDENTITY, PERMISSIONS, MULTI-TENANCY & COMPLIANCE
# ============================================================================

# Security Philosophy

Security is a first-class feature.

Every line of code must assume:

- Users make mistakes.
- Attackers exist.
- Sensitive data must be protected.
- Least privilege is the default.

Never trade security for convenience.

---

# Identity Management

Every authenticated user must have:

- Unique User ID
- Username
- Email Address
- Password Hash
- Status
- Organization
- Role
- Permission Set
- Last Login
- Last Password Change
- MFA Status
- Audit History

Never store passwords in plain text.

Passwords must always use Django's password hashing framework.

---

# Authentication

Support:

- Username/Password
- Email Login
- Multi-Factor Authentication (MFA)
- Password Reset
- Account Recovery
- Session Management
- Remember Me (configurable)
- API Token Authentication
- OAuth/OpenID (future-ready)

Never bypass authentication checks.

---

# Password Policy

Configurable password requirements:

- Minimum length
- Uppercase
- Lowercase
- Number
- Special character
- Password history
- Expiration period
- Lockout threshold

Prevent reuse of recently used passwords.

---

# Multi-Factor Authentication

Support:

- Authenticator Apps (TOTP)
- Email OTP
- SMS OTP (optional)
- Recovery Codes

High-privilege accounts should require MFA.

---

# Account Lockout

Automatically lock accounts after repeated failed login attempts.

Support:

- Temporary Lock
- Permanent Lock
- Administrator Unlock

Log every lockout event.

---

# Session Management

Support:

- Idle timeout
- Absolute timeout
- Force logout
- Logout from all devices
- Device tracking
- Active session list

Never allow unlimited session duration.

---

# Authorization

Always use Role-Based Access Control (RBAC).

Support:

- Roles
- Groups
- Permissions
- Permission Overrides
- Delegated Authority

Never rely on UI restrictions alone.

Always enforce permissions on the server.

---

# Organizational Permission Scope

Permissions must respect hierarchy.

Examples:

Church User

→ Church only

District User

→ District + Churches

Zone User

→ Zone + Districts + Churches

Conference User

→ Entire Conference

Union User

→ All Conferences

Division User

→ Entire Division

Super Administrator

→ Full System

Never expose data outside the authorized scope.

---

# Permission Categories

Support granular permissions.

Examples:

Members

Visitors

Attendance

Finance

Accounting

Budgets

Payroll

Assets

Inventory

Events

Departments

Reports

Documents

Settings

User Management

System Administration

Each permission should support:

View

Create

Edit

Delete (soft delete only)

Approve

Export

Audit

---

# Maker-Checker Workflow

Critical operations require approval.

Examples:

Financial Adjustments

Budget Approval

Payroll Processing

Member Deletion

Role Changes

Asset Disposal

Bulk Imports

Data Migration

Support:

Maker

Checker

Approval Date

Approval Notes

Rejection Reason

Audit Trail

---

# Multi-Tenancy

Every tenant must remain isolated.

Tenant examples:

Conference

District

Church

Never allow:

Cross-tenant queries

Cross-tenant reports

Cross-tenant exports

Tenant filtering must be enforced in:

Views

APIs

Reports

Background Tasks

Exports

Search

---

# Data Isolation Rules

Every business object belongs to an organization.

Examples:

Member

Attendance

Budget

Transaction

Meeting

Document

Asset

Inventory

Announcement

Organization filtering is mandatory.

---

# Audit Trail

Audit everything important.

Track:

Create

Update

Delete (soft)

Approve

Reject

Login

Logout

Export

Import

Password Reset

Permission Change

Role Assignment

Financial Posting

Asset Disposal

Member Transfer

Every audit record includes:

Timestamp

Business Date

User

Organization

Module

Record

Action

Old Values

New Values

IP Address

Device (if available)

Reason

Audit records are immutable.

---

# Soft Delete Policy

Never permanently delete business records.

Instead use:

is_deleted

deleted_at

deleted_by

Deletion Reason

Soft delete applies to:

Members

Transactions

Budgets

Assets

Inventory

Meetings

Documents

Announcements

Never hard delete audited data.

---

# File Upload Security

Validate:

File Type

Extension

Size

Virus Scan (future integration)

Allowed MIME Types

Rename uploaded files safely.

Never trust client-provided filenames.

---

# Sensitive Data Protection

Sensitive fields may include:

National ID

Passport

Phone Numbers

Email

Address

Salary

Bank Account

Medical Information

Emergency Contact

Apply encryption where appropriate.

Mask sensitive information unless permissions allow viewing.

---

# API Security

Every API must enforce:

Authentication

Authorization

Rate Limiting

CSRF Protection (where applicable)

Input Validation

Output Filtering

Versioning

Never expose internal implementation details.

---

# CSRF Protection

All browser forms must include CSRF protection.

Never disable CSRF globally.

---

# SQL Injection Prevention

Always use Django ORM.

Avoid raw SQL unless absolutely necessary.

Parameterized queries only.

Never concatenate SQL strings.

---

# XSS Protection

Escape user-generated content.

Sanitize HTML input.

Never trust user input.

---

# Input Validation

Validate:

Length

Required Fields

Formats

Dates

Numbers

Enums

Relationships

Never trust frontend validation alone.

---

# Rate Limiting

Protect:

Login

Password Reset

Public APIs

Search

Report Generation

Export Endpoints

Bulk Uploads

---

# Logging

Log:

Authentication

Permission Failures

Financial Changes

System Errors

Critical Warnings

Bulk Operations

Imports

Exports

Never log:

Passwords

Tokens

Sensitive Personal Data

Encryption Keys

---

# Encryption

Encrypt:

Passwords (hashed)

API Secrets

OAuth Tokens

Database Secrets

Sensitive Configuration

Support field-level encryption for highly sensitive information.

---

# Backup Policy

Support automated backups.

Backup:

Database

Media Files

Configuration

Uploaded Documents

Audit Logs

Retention policy should be configurable.

---

# Disaster Recovery

Support:

Restore Testing

Backup Verification

Recovery Procedures

Point-in-Time Recovery (PostgreSQL)

Recovery documentation must remain current.

---

# Compliance

Design with compliance in mind.

Support principles from:

GDPR (where applicable)

Data Minimization

Consent Tracking

Auditability

Retention Policies

Privacy by Design

---

# Data Retention

Retention periods should be configurable.

Support:

Archive

Restore

Legal Hold

Scheduled Purge (non-audited data only)

Never purge financial records without explicit policy.

---

# Notifications

Security notifications include:

Failed Login

Password Changed

New Device Login

Role Changed

Permission Granted

Sensitive Export

Large Data Import

Financial Approval

---

# Security Monitoring

Monitor:

Repeated Login Failures

Permission Abuse

Unusual Activity

Large Exports

Privilege Escalation Attempts

Unexpected Configuration Changes

Generate alerts for suspicious behavior.

---

# Development Security Rules

Never:

Disable authentication.

Disable permission checks.

Hardcode secrets.

Commit passwords.

Commit API keys.

Commit certificates.

Expose stack traces in production.

Ignore security warnings.

Store secrets in source code.

Always:

Use environment variables.

Validate permissions.

Review security implications.

Follow Django security best practices.

---

# Definition of Secure Code

Secure code:

✓ Validates all input

✓ Escapes output

✓ Uses least privilege

✓ Protects sensitive data

✓ Maintains audit history

✓ Uses secure defaults

✓ Fails safely

✓ Documents security assumptions

# END OF SECTION 4
# ============================================================================
# SECTION 5
# REPORTING, API, USER EXPERIENCE, PERFORMANCE, DEVOPS & TESTING
# ============================================================================

# Reporting Philosophy

Reporting is one of the most important capabilities of ChurchHub Enterprise.

Every report must be:

- Accurate
- Fast
- Auditable
- Permission-aware
- Filterable
- Exportable
- Printable
- Consistent

Reports should never expose data beyond the user's permission scope.

---

# Standard Reports

The system should support reporting across every business domain.

Core reports include:

Organization Reports

Membership Reports

Visitor Reports

Attendance Reports

Baptism Reports

Transfer Reports

Department Reports

Leadership Reports

Meeting Reports

Event Reports

Financial Reports

Budget Reports

Asset Reports

Inventory Reports

Payroll Reports

Audit Reports

Communication Reports

Document Reports

Analytics Dashboards

---

# Report Filters

Every report should support filtering by:

Division

Union

Conference

Zone

District

Church

Department

Ministry

Status

Member

Date Range

Business Date

Financial Year

Quarter

Month

Week

Custom Range

Reports should remember commonly used filters when appropriate.

---

# Export Formats

Support exporting reports as:

PDF

Excel (.xlsx)

CSV

Print-friendly HTML

Future support:

Power BI

Microsoft Excel Live

Google Sheets

JSON

---

# Dashboard Standards

Dashboards should present meaningful KPIs.

Support:

Summary Cards

Trend Charts

Bar Charts

Pie Charts

Line Charts

Heat Maps (future)

Forecasting Widgets (future)

Dashboard widgets should be configurable by role.

---

# Analytics

Support analytical insights such as:

Membership Growth

Attendance Trends

Giving Trends

Visitor Conversion

Department Performance

Budget Utilization

Asset Utilization

Volunteer Participation

Event Performance

Financial Health

Analytics should prioritize actionable information.

---

# Search

Global search should support:

Members

Organizations

Departments

Events

Meetings

Assets

Inventory

Transactions

Receipts

Documents

Announcements

Search should be indexed and optimized.

---

# API Philosophy

All APIs should follow RESTful principles.

API endpoints should be versioned.

Example:

/api/v1/

Future versions:

/api/v2/

/api/v3/

Never introduce breaking API changes without versioning.

---

# API Standards

Every endpoint should:

Require authentication unless explicitly public.

Validate permissions.

Validate input.

Return consistent responses.

Return appropriate HTTP status codes.

Use pagination where required.

Support filtering.

Support ordering.

Support searching.

---

# API Response Format

Success responses should follow a consistent structure.

Example fields:

success

message

data

pagination

metadata

Error responses should include:

error_code

message

details (when safe)

Never expose internal exceptions in production.

---

# API Documentation

Maintain OpenAPI / Swagger documentation.

Every endpoint should document:

Purpose

Permissions

Parameters

Request Body

Response Body

Status Codes

Examples

API documentation must remain synchronized with implementation.

---

# UI Philosophy

The interface should feel modern, professional, and approachable.

Design priorities:

Clarity

Consistency

Accessibility

Speed

Responsiveness

Simplicity

Avoid visual clutter.

---

# Bootstrap Standards

Use Bootstrap 5 components consistently.

Prefer reusable components over custom implementations.

Examples:

Cards

Tables

Modals

Offcanvas

Dropdowns

Badges

Alerts

Pagination

Breadcrumbs

Collapse

Forms

Avoid duplicated UI patterns.

---

# Responsive Design

Support:

Desktop

Laptop

Tablet

Mobile

No critical functionality should require desktop-only access.

---

# Accessibility

Meet WCAG best practices where practical.

Support:

Keyboard Navigation

Screen Readers

High Contrast

Visible Focus Indicators

Accessible Labels

Error Summaries

Never rely solely on color to convey information.

---

# Forms

Forms should provide:

Client-side validation

Server-side validation

Helpful error messages

Consistent layouts

Auto-save (where appropriate)

Confirmation for destructive actions

Never lose user-entered data unnecessarily.

---

# Tables

Large datasets should support:

Pagination

Sorting

Searching

Filtering

Column Selection (future)

Export

Sticky Headers (optional)

Avoid rendering thousands of rows at once.

---

# Performance Philosophy

Performance is a feature.

Every optimization should preserve correctness.

Measure before optimizing.

---

# ORM Optimization

Prefer:

select_related()

prefetch_related()

annotate()

aggregate()

bulk_create()

bulk_update()

Avoid:

N+1 queries

Repeated queries

Duplicate calculations

Unnecessary loops

---

# Caching

Cache where appropriate.

Suitable candidates:

Dashboard summaries

Reference data

Configuration

Frequently accessed reports

Lookup tables

Invalidate caches responsibly.

Never cache sensitive user-specific data without isolation.

---

# Database

Maintain:

Indexes

Unique Constraints

Check Constraints

Foreign Keys

Transactions

Atomic Operations

Review query plans for slow queries.

---

# Background Jobs

Long-running tasks should execute asynchronously.

Examples:

Email

SMS

PDF Generation

Large Imports

Large Exports

Report Generation

Backups

Audit Cleanup

Future recommendation:

Celery + Redis.

---

# File Storage

Support:

Local Storage (Development)

Cloud Storage (Production)

Version uploaded documents when appropriate.

Validate uploads before saving.

---

# Monitoring

Monitor:

Application Errors

Slow Queries

Background Jobs

API Performance

Disk Usage

Memory Usage

Database Health

Queue Length

Generate alerts for critical failures.

---

# Logging

Maintain structured logs.

Log levels:

DEBUG

INFO

WARNING

ERROR

CRITICAL

Avoid excessive logging in production.

---

# DevOps

Support:

Docker

Docker Compose

NGINX

Gunicorn

PostgreSQL

Redis

Object Storage

Environment Variables

Health Checks

---

# CI/CD

Every pull request should automatically run:

Formatting

Linting

Unit Tests

Integration Tests

Migration Checks

Security Checks

Static Analysis

Deployment should stop if critical checks fail.

---

# Testing Philosophy

Testing is mandatory.

Every significant feature requires tests.

Testing improves confidence and prevents regressions.

---

# Unit Tests

Test:

Models

Managers

Services

Validators

Utilities

Permissions

Business Rules

---

# Integration Tests

Verify interactions between:

Views

Services

Database

Permissions

Background Jobs

APIs

---

# UI Tests

Where practical, test:

Critical Forms

Authentication

Navigation

Approval Workflows

Financial Posting

Member Registration

---

# Regression Testing

Whenever a bug is fixed:

Create a regression test.

Prevent the same issue from returning.

---

# Test Coverage

Aim for:

80%+ coverage overall.

Higher coverage for:

Finance

Accounting

Permissions

Authentication

Member Management

---

# Release Quality Checklist

Before release verify:

✓ All tests pass

✓ No critical security issues

✓ Database migrations validated

✓ Reports verified

✓ APIs documented

✓ Performance acceptable

✓ UI reviewed

✓ Documentation updated

✓ Backup completed

✓ Rollback plan available

---

# Production Readiness

Production deployments must include:

HTTPS

Secure Cookies

Environment Variables

Debug Disabled

Database Backups

Monitoring

Centralized Logging

Disaster Recovery Plan

Health Check Endpoints

Performance Monitoring

Security Review

---

# Definition of Production Ready

A production-ready release is:

Reliable

Secure

Documented

Tested

Observable

Maintainable

Recoverable

Scalable

User-friendly

Auditable

# END OF SECTION 5
# ============================================================================
# SECTION 6
# AI WORKFLOW, DEVELOPMENT STANDARDS, GIT STRATEGY,
# MIGRATIONS, RELEASE MANAGEMENT & DEFINITION OF EXCELLENCE
# ============================================================================

# AI Mission

The AI is a Senior Enterprise Software Architect.

The objective is NOT to generate code quickly.

The objective is to continuously improve ChurchHub Enterprise
without compromising reliability, maintainability or security.

Every change should increase the quality of the system.

---

# Development Philosophy

Think before coding.

Read before modifying.

Understand before refactoring.

Measure before optimizing.

Document before releasing.

Never make assumptions.

---

# AI Workflow

For every task follow this process.

STEP 1

Understand the request.

↓

STEP 2

Locate the existing implementation.

↓

STEP 3

Search for reusable code.

↓

STEP 4

Identify dependencies.

↓

STEP 5

Identify risks.

↓

STEP 6

Explain the proposed implementation.

↓

STEP 7

Wait for approval for major changes.

↓

STEP 8

Implement incrementally.

↓

STEP 9

Run validation.

↓

STEP 10

Recommend future improvements.

Never skip steps for major work.

---

# Existing Code Policy

Always prefer improving existing code.

Never rewrite an entire module simply because a newer approach exists.

Refactor only when:

The existing implementation is difficult to maintain.

There are measurable performance issues.

Security requires redesign.

Business requirements require redesign.

The benefits outweigh migration costs.

---

# Backward Compatibility

Backward compatibility is extremely important.

Never:

Rename models.

Rename fields.

Rename URLs.

Rename APIs.

Rename templates.

Rename permissions.

Rename report identifiers.

Without explicit approval.

If breaking changes are required:

Document them.

Explain the impact.

Provide migration guidance.

---

# Database Migration Policy

Before generating migrations:

Explain:

Why the migration is required.

Which models are affected.

Whether data migration is required.

Whether downtime is expected.

Potential rollback strategy.

Never generate destructive migrations without approval.

Avoid:

Dropping columns.

Dropping tables.

Deleting historical data.

---

# Data Migration Rules

When changing data:

Prefer migration scripts.

Preserve existing records.

Maintain audit history.

Validate migrated data.

Generate verification reports.

Never silently discard information.

---

# Git Workflow

Recommended branching strategy:

main

↓

develop

↓

feature/<feature-name>

↓

release/<version>

↓

hotfix/<issue>

Every commit should be small, logical, and focused.

---

# Commit Message Convention

Use clear commit messages.

Examples:

feat(members): add visitor conversion workflow

fix(finance): correct journal balancing

refactor(attendance): extract attendance service

docs(api): update OpenAPI documentation

test(payroll): add approval workflow tests

Avoid vague commits such as:

update

fix

changes

misc

work

---

# Pull Request Checklist

Every pull request should include:

Purpose

Summary

Files changed

Screenshots (if UI)

Database changes

Testing performed

Risks

Rollback considerations

Future improvements

---

# Code Review Standards

Review for:

Correctness

Security

Performance

Readability

Maintainability

Scalability

Accessibility

Backward compatibility

Business rule compliance

Reject code that introduces technical debt without justification.

---

# Refactoring Guidelines

Refactor only when it provides measurable value.

Good reasons:

Duplicate logic

Poor readability

Performance bottlenecks

Security improvements

Testability

Maintainability

Avoid cosmetic refactoring that creates unnecessary churn.

---

# Dependency Management

Prefer mature, well-maintained libraries.

Before adding a dependency:

Evaluate:

Maintenance status

Security history

License

Community support

Long-term viability

Avoid unnecessary dependencies.

---

# Configuration Management

Store configuration in:

Environment variables

Configuration models

Settings modules

Never hardcode:

Passwords

API keys

Secrets

Database credentials

URLs that vary by environment

---

# Feature Flags

Major functionality should support feature flags where practical.

Examples:

AI Assistant

Experimental Reports

New Dashboard

New Attendance Workflow

This allows gradual rollout and safer deployments.

---

# Notifications

Important system events should generate notifications.

Examples:

Financial approvals

Member transfers

Failed backups

Permission changes

Budget exceeded

Inventory below threshold

Large donations

Critical system errors

Notifications should respect user preferences.

---

# Scheduled Tasks

Support scheduled background jobs for:

Daily backups

Reminder emails

Attendance summaries

Birthday notifications

Anniversary reminders

Audit maintenance

Report generation

Database optimization

Future recommendation:

Celery Beat or equivalent scheduler.

---

# Internationalization

Design for localization.

Support:

Multiple Languages

Multiple Date Formats

Multiple Time Zones

Multiple Currencies (future)

RTL Languages (future)

Avoid hardcoded text in templates.

---

# Coding Style

Prefer:

Small functions

Reusable services

Explicit code

Type hints

Meaningful names

Composition over inheritance

Avoid:

Deep nesting

Magic numbers

Magic strings

God classes

Massive views

Complex templates

Hidden side effects

---

# Documentation Rules

Every completed feature should update:

CHANGELOG.md

Developer Documentation

User Documentation

API Documentation

Architecture Documentation

Migration Notes

Documentation is not optional.

---

# Performance Review

Before completing major work review:

Database queries

Memory usage

Page load time

Report execution time

Background job duration

Caching opportunities

Indexes

---

# Security Review

Before release verify:

Authentication

Authorization

Input validation

CSRF protection

XSS protection

SQL injection prevention

Sensitive data handling

Audit logging

Session security

Secrets management

---

# Testing Checklist

Verify:

Unit Tests

Integration Tests

Permission Tests

Regression Tests

API Tests

Financial Accuracy

Report Accuracy

UI Validation

Cross-browser behaviour (where applicable)

No feature is complete without verification.

---

# Release Management

Each release should include:

Version Number

Release Notes

Database Migration Notes

Breaking Changes

New Features

Bug Fixes

Known Issues

Rollback Procedure

Deployment Instructions

---

# Versioning

Follow Semantic Versioning.

MAJOR

Breaking changes

MINOR

New backwards-compatible features

PATCH

Bug fixes

Example:

2.4.1

---

# Definition of Done

A task is complete only when:

✓ Business requirements satisfied

✓ Code reviewed

✓ Tests pass

✓ Security verified

✓ Performance acceptable

✓ Documentation updated

✓ UI reviewed

✓ Accessibility considered

✓ Backward compatibility preserved

✓ No unnecessary technical debt introduced

---

# Definition of Excellence

ChurchHub Enterprise should strive to be:

Reliable

Secure

Maintainable

Scalable

Auditable

Accessible

Fast

User-friendly

Financially accurate

Modular

Cloud-ready

API-first

Mobile-ready

AI-ready

Enterprise-grade

Every decision should move the platform closer to these goals.

---

# AI Final Reminder

Always think like an architect, not a code generator.

Protect existing functionality.

Respect business rules.

Respect financial integrity.

Respect organizational hierarchy.

Respect audit history.

Respect security.

Build software that will still be maintainable five to ten years from now.

If there is any uncertainty:

Stop.

Explain the concern.

Ask for clarification.

Never guess.

# ============================================================================
# END OF AGENTS.md
# ============================================================================