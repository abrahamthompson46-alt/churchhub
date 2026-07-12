"""Celery background tasks."""

import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

logger = logging.getLogger("churchhub.tasks")

User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invitation_email_task(self, invitation_id):
    from accounts.models import UserInvitation
    from church_system.email_service import send_user_invitation_email

    invitation = UserInvitation.objects.select_related("church", "invited_by").get(pk=invitation_id)
    if not invitation.is_valid:
        return {"status": "skipped", "reason": "invitation invalid"}
    sent = send_user_invitation_email(invitation, request=None, fail_silently=False)
    return {"status": "sent" if sent else "skipped", "email": invitation.email}


@shared_task(bind=True, max_retries=2)
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


@shared_task(bind=True, max_retries=2)
def generate_report_export_task(self, job_id):
    from django.test import RequestFactory

    from reports.exporters import build_export_bytes
    from reports.models import ReportAccessAuditLog, ReportExportJob
    from reports.services import build_report, log_report_access, parse_report_date, user_may_access_report

    job = ReportExportJob.objects.select_related("user").get(pk=job_id)
    job.status = ReportExportJob.STATUS_RUNNING
    job.save(update_fields=["status", "updated_at"])

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
        job.save()
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
        job.save(update_fields=["status", "error_message", "updated_at"])
        logger.exception("Report export failed for job %s", job_id)
        raise
