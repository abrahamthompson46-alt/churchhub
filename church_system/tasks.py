"""Celery background tasks."""

import logging
import subprocess
import sys
from pathlib import Path

from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger("churchhub.tasks")

User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invitation_email_task(self, invitation_id):
    from accounts.models import UserInvitation
    from church_system.email_service import send_user_invitation_email

    invitation = UserInvitation.objects.select_related("church", "invited_by").get(
        pk=invitation_id
    )
    if not invitation.is_valid:
        return {"status": "skipped", "reason": "invitation invalid"}
    sent = send_user_invitation_email(invitation, request=None, fail_silently=False)
    return {"status": "sent" if sent else "skipped", "email": invitation.email}


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def run_church_depreciation_task(self, church_id, year, month, user_id=None):
    from assets.services import run_monthly_depreciation
    from organization.models import Church
    from permissions.checks import can_manage_asset_policy
    from permissions.scoping import get_manageable_churches

    church = Church.objects.get(pk=church_id)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    if user and not can_manage_asset_policy(user):
        raise PermissionError("User may not run depreciation.")
    if user and not get_manageable_churches(user).filter(pk=church.pk).exists():
        raise PermissionError("Church is outside user scope.")
    result = run_monthly_depreciation(church, year, month, user)
    logger.info("Depreciation task %s %s-%s: %s", church.code, year, month, result)
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=90)
def generate_report_export_task(self, job_id):
    from django.core.files.base import ContentFile
    from django.test import RequestFactory

    from reports import repositories as repo
    from reports import selectors
    from reports.exporters import build_export_bytes
    from reports.models import ReportAccessAuditLog, ReportExportJob
    from reports.services import build_report, log_report_access, parse_report_date, user_may_access_report

    job = selectors.export_job_by_id(job_id)
    job.status = ReportExportJob.STATUS_RUNNING
    repo.save_export_job(job, update_fields=["status", "updated_at"])

    try:
        if not user_may_access_report(job.user, job.report_key):
            raise PermissionError(f"User may not export report '{job.report_key}'.")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = job.user
        request.session = {}
        params = job.params or {}
        hierarchy = {k: v for k, v in params.items() if k.endswith("_id")}
        start_date = parse_report_date(params.get("start_date"))
        end_date = parse_report_date(params.get("end_date"))
        data = build_report(
            job.report_key,
            request,
            period=params.get("period", "monthly"),
            start_date=start_date,
            end_date=end_date,
            **hierarchy,
        )
        content, content_type, filename = build_export_bytes(
            job.export_format,
            data["headers"],
            data["rows"],
            data["title"],
            f"{data['period_label']} — {data['start_date']} to {data['end_date']}",
            job.report_key,
        )
        job.export_file.save(filename, ContentFile(content), save=False)
        job.content_type = content_type
        job.status = ReportExportJob.STATUS_COMPLETE
        job.error_message = ""
        repo.save_export_job(job)
        log_report_access(
            user=job.user,
            report_key=job.report_key,
            action=ReportAccessAuditLog.ACTION_EXPORT,
            params={**params, "async": True, "job_id": str(job.pk)},
            row_count=len(data.get("rows") or []),
            export_format=job.export_format,
        )
        return {"status": "complete", "job_id": str(job.pk)}
    except Exception as exc:
        job.status = ReportExportJob.STATUS_FAILED
        job.error_message = str(exc)[:2000]
        repo.save_export_job(job, update_fields=["status", "error_message", "updated_at"])
        logger.exception("Report export failed for job %s", job_id)
        raise


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def purge_old_notifications_task(self, read_days=90, unread_days=180):
    """Celery Beat: purge aged dashboard notifications."""
    from dashboard import repositories as repo

    result = repo.purge_aged_notifications(
        read_days=read_days,
        unread_days=unread_days,
        dry_run=False,
    )
    logger.info("Purged notifications: %s", result)
    return result


@shared_task(bind=True, max_retries=1, default_retry_delay=600)
def backup_database_task(self, output_dir="backups", retention=30):
    """Celery Beat: invoke manage.py backup_database for PostgreSQL."""
    from django.conf import settings

    engine = settings.DATABASES["default"]["ENGINE"]
    if "postgresql" not in engine:
        logger.info("Skipping backup_database_task — not PostgreSQL (%s)", engine)
        return {"status": "skipped", "reason": "not postgresql"}

    manage = Path(settings.BASE_DIR) / "manage.py"
    cmd = [
        sys.executable,
        str(manage),
        "backup_database",
        "--output-dir",
        str(output_dir),
        "--retention",
        str(retention),
    ]
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(settings.BASE_DIR),
        )
        logger.info("Database backup complete: %s", completed.stdout[-500:])
        return {"status": "ok", "stdout": completed.stdout[-2000:]}
    except subprocess.CalledProcessError as exc:
        logger.error("Database backup failed: %s", exc.stderr)
        raise self.retry(exc=exc) from exc


@shared_task
def health_probe_task():
    """Celery Beat: run health checks and log degraded status."""
    from church_system.health import run_health_checks

    payload, status = run_health_checks()
    if status != 200:
        logger.warning("Health probe degraded: %s", payload)
    else:
        logger.info("Health probe ok duration_ms=%s", payload.get("duration_ms"))
    return {"http_status": status, "status": payload.get("status")}
