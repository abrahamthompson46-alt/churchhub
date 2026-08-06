# ChurchHub Production Deployment & Security Handover

## Project Overview

**Project Name:** ChurchHub
**Application Type:** Enterprise Church Management System
**Operating System:** Ubuntu 24.04 LTS
**Framework:** Django
**Database:** PostgreSQL 16
**Web Server:** Nginx
**Application Server:** Gunicorn
**Domain:** https://zreta.com
**SSL:** Let's Encrypt (via Certbot)
**DNS & CDN:** Cloudflare (Proxy Enabled)

---

# Purpose of this Document

This document serves as the official handover for the current production environment.

It summarizes:

* Infrastructure
* Deployment
* Security
* Backup strategy
* Monitoring
* Current production status
* Remaining work
* Outstanding issues
* Next engineering priorities

Any engineer or AI assistant taking over this project should read this document before making any changes.

---

# Current Infrastructure

## VPS

Ubuntu 24.04 LTS

Server has been successfully configured for production.

---

## Services

Current production services include:

* PostgreSQL
* Gunicorn
* Nginx
* Fail2Ban
* UFW Firewall
* Certbot
* Rclone
* Cron

---

# Deployment

Application location:

```text
/home/churchhub/apps/churchhub
```

Python virtual environment:

```text
/home/churchhub/apps/churchhub/venv
```

Gunicorn serves Django.

Nginx acts as reverse proxy.

Cloudflare proxies all external traffic.

---

# Domain

Primary:

```
https://zreta.com
```

Additional:

```
https://www.zreta.com
```

Cloudflare:

* Proxy Enabled
* SSL Mode = Full (Strict)

---

# SSL

Certificate issued by Let's Encrypt.

Certificate verified.

Dry-run renewal completed successfully.

Command:

```bash
sudo certbot renew --dry-run
```

Certificate renewal is functioning correctly.

---

# Firewall

UFW Status:

Active

Allowed services:

```
OpenSSH
Nginx Full
```

All unnecessary ports remain closed.

---

# Fail2Ban

Installed.

Running.

SSH jail enabled.

Brute-force attacks are automatically blocked.

Verified with:

```bash
sudo fail2ban-client status
```

---

# PostgreSQL

Database:

```
churchhub_db
```

Application user:

```
churchhub_user
```

Ownership has been corrected.

Database owner:

```
churchhub_user
```

Verified using:

```sql
\l
```

---

# Backup Strategy

Backups are fully automated.

Script:

```
/home/churchhub/scripts/churchhub_backup.sh
```

Backups include:

* PostgreSQL database
* Media files
* Environment file

Google Drive synchronization is operational.

Remote:

```
gdrive:
```

Destination:

```
ChurchHub-Backups
```

Backup folders:

```
database/
media/
env/
```

---

# Backup Schedule

Cron:

```cron
0 2 * * * /home/churchhub/scripts/churchhub_backup.sh
```

Runs every day at:

02:00 UTC

Backups upload automatically to Google Drive.

---

# Monitoring

Health script:

```
/home/churchhub/monitoring/churchhub_health_check.sh
```

Log:

```
/home/churchhub/monitoring/health.log
```

Checks:

* Disk usage
* Memory usage
* ChurchHub service
* PostgreSQL
* Nginx

Cron:

```cron
0 * * * * /home/churchhub/monitoring/churchhub_health_check.sh
```

Runs hourly.

---

# Current Security Status

Completed:

* HTTPS enabled
* Cloudflare proxy enabled
* Firewall enabled
* Fail2Ban enabled
* Automatic backups
* Monitoring
* PostgreSQL secured
* SSL certificate
* HSTS header visible from production

---

# Current Outstanding Issue

## Django Production Security Settings

This is the primary unresolved issue.

Environment file contains:

```
DJANGO_SETTINGS_MODULE=church_system.settings.production
```

However:

Running

```bash
python manage.py shell
```

then

```python
from django.conf import settings

print(settings.SECURE_SSL_REDIRECT)
print(settings.SESSION_COOKIE_SECURE)
print(settings.CSRF_COOKIE_SECURE)
print(settings.SECURE_HSTS_SECONDS)
```

returns:

```
False
False
False
0
```

Yet production.py contains:

```python
SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True

CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000

SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SECURE_HSTS_PRELOAD = True

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)
```

Therefore Django is not loading the expected production configuration or another settings module is overriding these values.

This issue must be resolved before any additional production hardening.

---

# Investigation Required

Determine exactly how settings are loaded.

Inspect:

```
church_system/settings/
```

Review:

* **init**.py
* base.py
* development.py
* production.py
* staging.py

Inspect:

```
manage.py
```

Inspect:

```
church_system/wsgi.py
```

Inspect:

```
church_system/asgi.py
```

Inspect systemd service.

Check:

```
Environment=
EnvironmentFile=
DJANGO_SETTINGS_MODULE=
```

Confirm Gunicorn is using production settings.

Identify which settings module is actually loaded.

---

# Deployment Goals

After fixing settings loading:

Run:

```bash
python manage.py check --deploy
```

Expected result:

```
System check identified no issues.
```

---

# Remaining Security Tasks

Complete:

* HTTPS redirect
* Secure cookies
* CSRF secure cookie
* Session secure cookie
* HSTS
* Additional security headers
* Content Security Policy review
* Cookie audit
* Session timeout review

---

# Infrastructure Improvements

Remaining tasks:

* Log rotation review
* PostgreSQL maintenance automation
* Backup restore verification
* Automatic Gunicorn restart policy
* Error reporting
* Performance profiling
* Health dashboard
* Alert notifications

---

# Website Roadmap

Improve the public website.

Tasks include:

* Landing page
* About page
* Features
* Pricing
* Contact page
* Documentation
* Demo request
* FAQ
* Testimonials
* Blog
* SEO improvements
* Performance optimization

---

# ChurchHub Application Roadmap

Continue improving:

* Dashboard
* Reports
* Financial analytics
* Member management
* Permissions
* Notifications
* Audit logs
* Mobile responsiveness
* Accessibility
* User onboarding

---

# Development Guidelines

Before making changes:

1. Understand the current architecture.
2. Avoid unnecessary refactoring.
3. Preserve production stability.
4. Verify changes locally.
5. Test on the VPS.
6. Restart affected services.
7. Confirm application functionality.
8. Verify backups still succeed.
9. Confirm SSL still functions.
10. Run Django deployment checks.

---

# Recommended Workflow

1. Review documentation.
2. Investigate the Django settings issue.
3. Produce a technical report.
4. Fix the root cause.
5. Verify production security.
6. Complete deployment hardening.
7. Improve the public website.
8. Continue feature development.

---

# Important Notes

The production server is stable and operational.

The following systems are functioning correctly:

* Domain
* HTTPS
* Nginx
* Gunicorn
* PostgreSQL
* Google Drive backups
* Cron jobs
* Monitoring
* Fail2Ban
* Firewall

Avoid changing infrastructure unless necessary.

The priority is to correct the Django production settings loading so that all security settings are applied consistently.

---

# Final Instruction for Cursor

Read this document completely before modifying any code.

Your first objective is **not** to implement new features.

Your first objective is to identify why the production security settings are not being applied despite the environment configuration indicating that `church_system.settings.production` should be in use.

Provide:

1. Root cause analysis.
2. Files requiring modification.
3. Proposed solution.
4. Risk assessment.

Do not implement changes until the analysis is complete and approved.

Once the settings issue is resolved, continue with full production hardening, then proceed to improving the ChurchHub website and application while preserving production stability.

