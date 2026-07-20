# ChurchHub Enterprise
# DATABASE_STANDARDS.md

Version: 2.0

---

# Purpose

This document defines database standards for ChurchHub Enterprise.

Every model, migration, and query must follow these standards.

Goals:

- Data Integrity
- Performance
- Scalability
- Auditability
- Maintainability
- Backward Compatibility

---

# Supported Databases

Development

- SQLite

Production

- PostgreSQL

Never use database-specific features unless they are safely isolated.

---

# Primary Keys

Preferred:

UUID primary keys for new core business entities.

Examples:

Member

Attendance

Visitor

Meeting

Budget

Asset

Inventory

Transaction

Document

AuditLog

Avoid integer IDs for new enterprise entities unless there is a compelling reason.

---

# Base Model

All business entities should inherit from a common abstract base model where appropriate.

Typical fields include:

- id
- created_at
- updated_at
- created_by
- updated_by
- is_active
- is_deleted
- deleted_at
- deleted_by

Financial records may have additional audit fields.

---

# Naming Standards

Model names:

Singular

Examples:

Member

AttendanceRecord

Budget

Asset

Department

Table names:

Plural and descriptive where customized.

Field names should be explicit.

Good:

member_status

attendance_date

business_date

budget_year

Poor:

status

date

year

---

# Foreign Keys

Always define:

related_name

on_delete

verbose_name (where useful)

Choose on_delete intentionally.

Avoid CASCADE for financial data.

Prefer:

PROTECT

RESTRICT

SET_NULL

where appropriate.

---

# Many-to-Many Relationships

Use explicit through models whenever additional metadata is required.

Example:

MemberDepartment

MemberMinistry

MemberRole

Include:

Created Date

Assigned By

Status

History

---

# Constraints

Use database constraints whenever possible.

Examples:

UniqueConstraint

CheckConstraint

Conditional UniqueConstraint

Do not rely solely on application validation.

---

# Unique Rules

Examples:

Member ID

Receipt Number

Journal Number

Asset Code

Organization Code

Account Code

must be unique within their defined scope.

---

# Indexing

Index frequently searched fields.

Examples:

Member ID

Last Name

Phone Number

Email

Receipt Number

Attendance Date

Business Date

Organization

Status

Foreign Keys

Review indexes periodically.

---

# Soft Delete

Never hard delete business data.

Use:

is_deleted

deleted_at

deleted_by

Queries should exclude deleted records by default.

Provide managers for:

active()

deleted()

all_records()

---

# Audit Fields

Critical models should record:

created_by

updated_by

deleted_by

approved_by

approved_at

business_date

---

# Business Date

Financial and operational modules should use Business Date rather than relying solely on server time.

Business Date should be configurable by organization where appropriate.

---

# Historical Records

Never overwrite historical information.

Examples:

Member transfers

Budget revisions

Financial postings

Leadership appointments

Maintain historical tables or audit trails where necessary.

---

# Migrations

Migration rules:

One logical change per migration.

Name migrations clearly.

Review generated SQL for major schema changes.

Never delete old migrations in shared environments.

Always test migrations on a copy of production data before major releases.

---

# Data Migrations

When transforming existing data:

Use Django data migrations.

Validate migrated records.

Generate summary reports.

Never silently discard data.

---

# Transactions

Wrap critical write operations in:

transaction.atomic()

Especially for:

Financial posting

Member transfers

Payroll

Inventory adjustments

Asset disposal

Approval workflows

---

# Query Standards

Prefer:

select_related()

prefetch_related()

annotate()

aggregate()

bulk_create()

bulk_update()

Avoid:

N+1 queries

Repeated ORM calls inside loops

Loading unnecessary fields

---

# Managers & QuerySets

Provide custom QuerySets for reusable filters.

Examples:

active()

inactive()

current()

approved()

pending()

archived()

Expose these through custom managers.

---

# Reporting Queries

Complex reporting logic belongs in selectors or dedicated reporting services.

Never duplicate reporting SQL across modules.

---

# Data Integrity

Always enforce:

Foreign key integrity

Required relationships

Valid status transitions

Business rules

Database constraints complement application validation.

---

# Backup & Recovery

Database backups must be:

Automated

Encrypted

Verified

Tested periodically

Support point-in-time recovery for PostgreSQL.

---

# Performance Monitoring

Monitor:

Slow queries

Missing indexes

Lock contention

Table growth

Connection usage

Review execution plans for expensive queries.

---

# Database Security

Use least-privilege database accounts.

Never expose credentials in source code.

Use environment variables for connection settings.

Restrict production database access.

---

# Archiving

Support archiving for historical records that are rarely accessed.

Archived data should remain searchable where business requirements demand it.

Never archive records that are still operationally active.

---

# Database Review Checklist

Before approving any schema change verify:

✓ Naming follows standards

✓ Constraints are defined

✓ Indexes reviewed

✓ Migrations tested

✓ Audit fields preserved

✓ Tenant isolation maintained

✓ Performance considered

✓ Backward compatibility preserved

✓ Documentation updated

---

# Guiding Principle

The database is the foundation of ChurchHub Enterprise.

Schema changes should be deliberate, documented, reversible where possible, and designed to support many years of growth without compromising data integrity.