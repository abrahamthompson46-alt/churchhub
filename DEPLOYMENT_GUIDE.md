# ChurchHub Enterprise
# DEPLOYMENT_GUIDE.md

Version: 2.0

---

# Purpose

This document defines the deployment requirements for ChurchHub Enterprise.

The objective is to provide:

- Secure production deployment
- Reliable updates
- Data protection
- High availability
- Maintainable infrastructure

---

# Deployment Philosophy

Production systems must prioritize:

Security

Reliability

Monitoring

Backup

Recoverability

---

# Supported Environments

ChurchHub should maintain:

## Development

Purpose:

Local development

Testing new features

---

## Testing/Staging

Purpose:

Feature validation

User acceptance testing

Migration testing

---

## Production

Purpose:

Live church operations

---

# Recommended Production Stack

Application:

Django

Python 3.13+

---

Database:

PostgreSQL

---

Web Server:

Nginx

---

Application Server:

Gunicorn/Uvicorn

---

Cache:

Redis

---

Background Tasks:

Celery

---

Operating System:

Linux server

---

# Server Requirements

Minimum production server should provide:

Adequate CPU

Sufficient RAM

Fast storage

Reliable backup storage

Secure network access

---

# Environment Configuration

Never store production settings in code.

Use:

Environment variables

Secret managers

Deployment configuration

---

# Required Environment Variables

Example:

```
SECRET_KEY=

DEBUG=False

DATABASE_URL=

ALLOWED_HOSTS=

EMAIL_HOST=

SMS_API_KEY=

REDIS_URL=
```

---

# Security Settings

Production must have:

```
DEBUG=False
```

---

Enable:

HTTPS

Secure cookies

CSRF protection

Security headers

---

# Database Deployment

Production database:

PostgreSQL only.

---

# Database Requirements

Configure:

User authentication

Restricted access

Encrypted connections

Regular backups

---

# Database Migration Process

Before migration:

Backup database.

Review migration.

Test in staging.

Apply migration.

Verify application.

---

# Static Files

Production deployment requires:

Collect static files.

Configure storage.

Serve through optimized server.

---

# Media Files

Protect uploaded files.

Use:

Secure storage

Access validation

Backup strategy

---

# Web Server Configuration

Nginx should handle:

Static files

Media files

HTTPS termination

Request forwarding

---

# Application Server

Use:

Gunicorn/Uvicorn

Configure:

Workers

Timeouts

Logging

---

# Background Processing

Use task workers for:

Emails

SMS

Large reports

Imports

Analytics

---

# Redis Usage

Redis may support:

Caching

Task queues

Sessions

Temporary data

---

# Backup Strategy

Maintain:

Database backups (`manage.py backup_database` — streaming `pg_dump` → gzip; optional age encryption)

Media backups (filesystem / object storage snapshot — separate from DB dump)

Configuration backups (`.env` stored in a secrets vault — never in Git)

Automation:

- Celery Beat daily task `backup_database_task` (when Beat enabled), and/or
- systemd `churchhub-backup.timer` (`deploy/systemd/`)

Offsite: optional rclone hook — see `deploy/backup/README.md` (no upload without config).

---

# Backup Schedule

Recommended:

Daily database backup (03:00 Beat and/or 03:15 systemd timer — pick one primary)

Weekly full backup / media snapshot

Regular restore testing on staging with `restore_database`

---

# Backup Security

Protect backups with:

Encryption (optional age)

Access controls (`0600` files)

Separate storage (rclone Google Drive / S3 when configured)

Explicit restore confirmation (`DESTROY_LOCAL_DATA` + production flag)

---

# Monitoring

Monitor:

Application health

Database health

Server resources

Errors

Failed jobs

---

# Logging

Maintain logs for:

Application errors

Security events

User activity

Background jobs

---

# Error Tracking

Support:

Error monitoring

Alert notifications

Issue tracking

---

# Update Process

Before updating:

Backup database.

Review changes.

Test migrations.

Deploy.

Monitor.

---

# Release Process

Recommended:

1. Create release branch.

2. Run tests.

3. Deploy to staging.

4. Approve release.

5. Deploy production.

6. Monitor.

---

# Rollback Process

If deployment fails:

Stop release.

Restore previous version.

Rollback migrations if possible.

Restore database if required.

Investigate failure.

---

# Domain and HTTPS

Production should use:

Valid domain

SSL certificate

HTTPS only

---

# Email Configuration

Production email requires:

Verified sender

Secure credentials

Delivery monitoring

---

# SMS Configuration

Production SMS requires:

Provider account

API credentials

Usage monitoring

---

# Security Hardening

Server should have:

Firewall

Updated packages

Limited SSH access

Strong authentication

Regular updates

---

# Production Checklist

Before going live:

✓ DEBUG disabled

✓ HTTPS active

✓ Database secured

✓ Backups configured

✓ Monitoring active

✓ Permissions tested

✓ Migrations verified

✓ Static files configured

✓ Error tracking enabled

---

# Disaster Recovery

Maintain:

Recovery plan

Backup restoration procedure

Emergency contacts

---

# Scaling Strategy

Future scaling:

Vertical scaling

Database optimization

Caching

Background workers

Load balancing

Service separation

---

# High Availability Future

Support:

Multiple application servers

Database replication

Distributed workers

Failover systems

---

# Definition of Complete

Deployment is complete when:

✓ Application runs securely

✓ Data is protected

✓ Monitoring works

✓ Backups exist

✓ Recovery is possible

---

# Final Principle

Production deployment is not just making software available.

It is ensuring the organization can depend on it every day.

# END OF DEPLOYMENT_GUIDE.md