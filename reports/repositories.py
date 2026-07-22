"""
Persistence helpers for the reports domain.

Services own access rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or formatting here.
"""

from __future__ import annotations

from .models import ReportAccessAuditLog, ReportExportJob


def create_access_audit(
    *,
    user,
    report_key,
    action,
    params=None,
    row_count=0,
    church=None,
    export_format="",
):
    return ReportAccessAuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        report_key=report_key,
        action=action,
        export_format=export_format or "",
        params=params or {},
        row_count=row_count or 0,
        church=church,
    )


def create_export_job(*, user, report_key, export_format, params=None):
    return ReportExportJob.objects.create(
        user=user,
        report_key=report_key,
        export_format=export_format,
        params=params or {},
    )


def save_export_job(job, *, update_fields=None):
    if update_fields is not None:
        job.save(update_fields=update_fields)
    else:
        job.save()
    return job
