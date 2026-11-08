"""Email the platform owner when a demo is requested or a tenant reports payment."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from church_system.email_service import get_email_branding_context, send_platform_email
from church_system.public_urls import build_public_absolute_uri
from sitecontrol import repositories as platform_repo
from sitecontrol.marketing_services import get_marketing_settings
from sitecontrol.models import SubscriptionActivationRequest, TenantApplication
from sitecontrol.services import get_site_settings

logger = logging.getLogger("churchhub.commercial")

User = get_user_model()

PLACEHOLDER_EMAIL_SUFFIXES = (".local",)


def owner_notification_emails() -> list[str]:
    """Sales inbox first, then support, then active platform operator emails."""
    emails: list[str] = []
    marketing = get_marketing_settings()
    sales = (getattr(marketing, "sales_notification_email", None) or "").strip().lower()
    if sales:
        emails.append(sales)
        return emails

    site = get_site_settings()
    support = (getattr(site, "support_email", None) or "").strip().lower()
    if support and not any(support.endswith(suffix) for suffix in PLACEHOLDER_EMAIL_SUFFIXES):
        emails.append(support)
        return emails

    for user in User.objects.filter(is_platform_user=True, is_active=True).exclude(email=""):
        address = (user.email or "").strip().lower()
        if address and address not in emails:
            emails.append(address)
    return emails


def dispatch_demo_request_notification(application_id: str) -> bool:
    return _dispatch("demo", application_id)


def dispatch_payment_request_notification(request_id: str) -> bool:
    return _dispatch("payment", request_id)


def schedule_demo_request_notification(application) -> None:
    pk = str(application.pk)
    transaction.on_commit(lambda: dispatch_demo_request_notification(pk))


def schedule_payment_request_notification(activation_request) -> None:
    pk = str(activation_request.pk)
    transaction.on_commit(lambda: dispatch_payment_request_notification(pk))


def _dispatch(kind: str, record_id: str) -> bool:
    use_async = getattr(settings, "CHURCHHUB_ASYNC_EMAIL", False) and not getattr(
        settings, "CELERY_TASK_ALWAYS_EAGER", False
    )
    if use_async:
        try:
            from church_system.tasks import send_commercial_notification_task

            send_commercial_notification_task.delay(kind, str(record_id))
            return True
        except Exception:
            logger.warning(
                "Could not enqueue commercial notification %s %s; sending now.",
                kind,
                record_id,
            )
    return deliver_commercial_notification(kind, record_id)


def deliver_commercial_notification(kind: str, record_id: str, *, raise_on_error: bool = False) -> bool:
    recipients = owner_notification_emails()
    if not recipients:
        logger.warning("No owner email configured; skipped %s notification %s.", kind, record_id)
        return False

    if kind == "demo":
        target_model = "TenantApplication"
        sender = _send_demo_email
    elif kind == "payment":
        target_model = "SubscriptionActivationRequest"
        sender = _send_payment_email
    else:
        logger.warning("Unknown commercial notification kind %s.", kind)
        return False
    try:
        sent = sender(record_id, recipients)
    except Exception as exc:
        logger.warning("Commercial %s notification failed for %s (%s).", kind, record_id, type(exc).__name__)
        _audit(kind, record_id, target_model=target_model, sent=False)
        if raise_on_error:
            raise
        return False

    _audit(kind, record_id, target_model=target_model, sent=bool(sent))
    return bool(sent)


def _send_demo_email(application_id, recipients) -> bool:
    application = (
        TenantApplication.objects.select_related("denomination", "created_church")
        .filter(pk=application_id)
        .first()
    )
    if application is None:
        return False
    detail_path = reverse("sitecontrol:application_detail", args=[application.pk])
    context = {
        **get_email_branding_context(None, preheader="A church started or requested a demo."),
        "application": application,
        "detail_url": build_public_absolute_uri(None, detail_path),
        "auto_provisioned": application.status == "APPROVED" and application.created_church_id is not None,
    }
    return send_platform_email(
        subject=f"[{context['site_name']}] Demo request — {application.church_name}",
        to=recipients,
        text_body=render_to_string("emails/commercial_demo_request.txt", context),
        html_body=render_to_string("emails/commercial_demo_request.html", context),
        fail_silently=False,
    )


def _send_payment_email(request_id, recipients) -> bool:
    activation = (
        SubscriptionActivationRequest.objects.select_related("church", "requested_plan")
        .filter(pk=request_id)
        .first()
    )
    if activation is None:
        return False
    detail_path = reverse("sitecontrol:activation_request_detail", args=[activation.pk])
    context = {
        **get_email_branding_context(None, preheader="A tenant reported a subscription payment."),
        "activation": activation,
        "detail_url": build_public_absolute_uri(None, detail_path),
    }
    return send_platform_email(
        subject=f"[{context['site_name']}] Payment reported — {activation.church_name}",
        to=recipients,
        text_body=render_to_string("emails/commercial_payment_request.txt", context),
        html_body=render_to_string("emails/commercial_payment_request.html", context),
        fail_silently=False,
    )


def _audit(kind, record_id, *, target_model, sent):
    platform_repo.create_platform_audit(
        user=None,
        denomination=None,
        action="COMMERCIAL_NOTIFY",
        target_model=target_model,
        target_id=str(record_id),
        summary="Owner commercial email updated",
        details={"kind": kind, "sent": bool(sent)},
    )
