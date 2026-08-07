# Wave 1 — Production Observability & Monitoring Plan

**Status:** IMPLEMENTED  
**Date:** 6–7 August 2026  

## Shipped

| Area | Change |
|------|--------|
| Health | Safe `*_detail` when `DEBUG=False`; redis on `/health/`; errors logged server-side |
| Sentry | Optional DSN; `SENTRY_RELEASE` when set; `before_send` scrubber; `send_default_pii=False` |
| Logging | `SecretRedactFilter` on handlers; rotation defaults unchanged (10MB × 10) |
| Tests | `church_system/tests_observability.py` |
| Docs | SECURITY.md, DEPLOYMENT_GUIDE.md, OPERATIONS_RUNBOOK.md §6.0, DEPLOYMENT_NOTES |

## Verify

```bash
python manage.py test church_system.tests_observability church_system.tests_infra -v 2
curl -sH "X-Health-Token: $CHURCHHUB_HEALTH_TOKEN" https://zreta.com/health/ready/
```

Original design notes: health/Sentry/logging already existed; this area hardened them without redesigning endpoints.
