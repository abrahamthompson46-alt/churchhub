# ChurchHub Enterprise
# SECURITY.md

Version: 2.0

---

# Purpose

Security is a foundational requirement of ChurchHub Enterprise.

The system manages sensitive information including:

- Member records
- Financial transactions
- Giving information
- Employee information
- Leadership records
- Documents
- Organizational data

Security must be considered in every feature.

---

# Security Principles

Follow these principles:

## Defense in Depth

Use multiple security layers.

Never depend on a single protection mechanism.

---

## Least Privilege

Users receive only the permissions required for their responsibilities.

Never grant excessive access by default.

---

## Secure by Default

New features must begin with secure settings.

Do not add security later.

---

## Privacy by Design

Collect only required information.

Protect personal information throughout its lifecycle.

---

# Threat Model

Consider these threats:

Unauthorized access

Privilege escalation

Data leakage

Account compromise

Malicious uploads

SQL injection

Cross-tenant data exposure

Session hijacking

Password attacks

Insider misuse

Data corruption

---

# Authentication Security

Authentication must provide:

- Secure password storage
- Account protection
- Session security
- Login monitoring
- Password recovery

---

# Password Storage

Never store passwords directly.

Always use Django password hashing.

Allowed:

PBKDF2

Argon2

Other approved password hashers

Never:

Plain text passwords

MD5

SHA1 without proper password hashing

---

# Password Policy

Support:

Minimum password length

Password complexity

Password history

Password expiration (optional)

Failed login protection

---

# Account Protection

Support:

Account lockout

Login attempt tracking

Suspicious login detection

Administrator unlock

---

# Multi-Factor Authentication

MFA should be available for all users.

Mandatory MFA recommended for:

Super Administrators

Financial Officers

System Administrators

Auditors

---

# Session Security

Configure:

Secure cookies

HTTPOnly cookies

SameSite protection

Session timeout

Session invalidation after password change

---

# Authorization Security

Never trust the frontend.

Buttons hidden in the UI are not security.

Every action requires backend permission checks.

---

# Permission Verification

Before allowing an operation:

Check user identity.

Check role.

Check organization scope.

Check record ownership.

Check approval requirements.

---

# Multi-Tenant Security

This is critical.

Never allow:

Church A users to view Church B data.

District users to access unauthorized districts.

Conference users to access unrelated conferences.

---

# Tenant Enforcement

Apply tenant filtering in:

Views

APIs

Selectors

Reports

Exports

Background tasks

Scheduled jobs

Search

---

# Database Security

Production database must:

Require authentication.

Use encrypted connections where possible.

Restrict network access.

Use separate database users.

Apply least privilege.

---

# Database Credentials

Never store:

Database passwords

API keys

Secrets

inside:

Source code

Git repositories

Documentation

---

# Environment Variables

Sensitive configuration belongs in:

.env files

Secret managers

Deployment configuration

---

# Secret Management

Protect:

SECRET_KEY

Database passwords

Email credentials

SMS credentials

Payment credentials

API tokens

Encryption keys

Never expose secrets in logs.

---

# Encryption

Use encryption for:

Sensitive personal fields

API credentials

Stored tokens

Backups

Document storage where required

---

# Data Protection

Protect:

Names

Addresses

Phone numbers

Emails

Financial information

Identification documents

Payroll information

Emergency contacts

---

# Data Masking

Sensitive information should be masked where appropriate.

Example:

Phone number:

********1234

Bank account:

****5678

---

# Audit Security

Audit logs must be protected.

Never allow normal users to:

Edit audit logs.

Delete audit logs.

Modify history.

---

# Audit Requirements

Record:

Who

What

When

Where

Why

Old value

New value

New value

---

# File Security

All uploads must be validated.

Check:

Extension

MIME type

Size

Storage location

---

# File Upload Restrictions

Prevent:

Executable uploads

Malicious scripts

Unsafe file types

Path traversal

---

# Web Security

Protect against:

SQL Injection

XSS

CSRF

Clickjacking

Session attacks

---

# SQL Injection Prevention

Use:

Django ORM

Parameterized queries

Safe database APIs

Avoid raw SQL unless necessary.

---

# XSS Prevention

Always escape user content.

Sanitize rich text input.

Never render unsafe HTML.

---

# CSRF Protection

All state-changing browser requests require CSRF protection.

Never disable CSRF globally.

---

# Security Headers

Production should support:

Content Security Policy

X-Frame-Options

X-Content-Type-Options

Referrer Policy

Secure Transport headers

---

# API Security

APIs require:

Authentication

Authorization

Validation

Rate limiting

Logging

Version control

---

# Rate Limiting

Protect:

Login endpoints

Password reset

Search

Reports

Exports

SMS

Email sending

Public APIs

---

# Background Job Security

Background tasks must:

Validate permissions.

Avoid exposing sensitive data.

Handle failures safely.

Log execution.

---

# Backup Security

Backups must be:

Encrypted (optional age — `CHURCHHUB_BACKUP_ENCRYPT` + `CHURCHHUB_BACKUP_AGE_RECIPIENT`)

Access-controlled (directory mode `0700`, files `0600`; not world-readable)

Verified (`manage.py backup_database --verify` + sibling `.sha256`)

Stored securely (local `CHURCHHUB_BACKUP_DIR`; optional rclone offsite — opt-in only)

Regularly tested (`manage.py restore_database` on **staging**, never casually on production)

## Backup & restore commands (Current)

```bash
python manage.py backup_database --verify
python manage.py restore_database \
  --input /var/backups/churchhub/churchhub_YYYYMMDD_HHMMSS.sql.gz \
  --confirm DESTROY_LOCAL_DATA
# Production target also requires: --i-understand-production --no-input
```

Offsite upload never runs unless `CHURCHHUB_BACKUP_POST_HOOK` / rclone remote is configured.
See `deploy/backup/README.md` and `docs/WAVE1_BACKUP_RECOVERY_PLAN.md`.

---

# Disaster Recovery Security

Maintain:

Recovery procedures

Backup restoration tests

Emergency contacts

Access procedures

---

# Production Security Checklist

Before deployment:

✓ DEBUG disabled

✓ HTTPS enabled

✓ Secure cookies enabled

✓ Secrets protected

✓ Database secured

✓ Backups configured

✓ Monitoring enabled

✓ Logs reviewed

✓ Permissions tested

✓ Security scan completed

---

# Security Testing

Perform:

Authentication testing

Permission testing

Tenant isolation testing

Input validation testing

API security testing

File upload testing

---

# Incident Response

Security incidents must follow:

1. Detect

2. Contain

3. Investigate

4. Recover

5. Document

6. Improve

---

# Incident Documentation

Record:

Date

Affected systems

Impact

Cause

Resolution

Preventive actions

---

# Security Review Process

Major features require security review before release.

Especially:

Finance

Payroll

Permissions

Member data

Documents

APIs

---

# Security Golden Rule

Never assume a user is trustworthy.

Verify every request.

Protect every record.

Audit every important action.

Security is everyone's responsibility.

# END OF SECURITY.md