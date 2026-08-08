"""Business workflows for the Platform Owner Marketing Hub."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from church_system.email_service import get_email_branding_context, send_platform_email
from church_system.public_urls import build_public_absolute_uri
from sitecontrol import marketing_repositories as marketing_repo
from sitecontrol import marketing_selectors
from sitecontrol import repositories as platform_repo

logger = logging.getLogger("churchhub.marketing")

INQUIRY_RATE_LIMIT = 5
INQUIRY_RATE_WINDOW_SECONDS = 60 * 60
INQUIRY_EMAIL_LIMIT = 3
INQUIRY_EMAIL_WINDOW_SECONDS = 24 * 60 * 60
INQUIRY_GLOBAL_LIMIT = 200
INQUIRY_CAMPAIGN_LIMIT = 50


def get_marketing_settings():
    settings_obj = marketing_selectors.marketing_settings()
    if settings_obj is not None:
        return settings_obj
    settings_obj, _ = marketing_repo.get_or_create_marketing_settings()
    return settings_obj


def build_campaign_inquiry_url(campaign, request=None):
    query = {
        "campaign": campaign.slug,
        "utm_source": campaign.source,
        "utm_medium": campaign.medium,
        "utm_campaign": campaign.campaign_tag or campaign.slug,
    }
    query = {key: value for key, value in query.items() if value}
    path = reverse("marketing_inquiry")
    return f"{build_public_absolute_uri(request, path)}?{urlencode(query)}"


def build_inquiry_url(request=None):
    return build_public_absolute_uri(request, reverse("marketing_inquiry"))


def build_registration_url(request=None):
    return build_public_absolute_uri(request, reverse("church_apply"))


def marketing_inquiry_is_ready(settings_obj=None):
    settings_obj = settings_obj or get_marketing_settings()
    return bool(
        settings_obj.public_inquiry_enabled
        and settings_obj.privacy_policy_url.startswith("https://")
        and (settings_obj.consent_text or "").strip()
        and (
            not settings_obj.notify_on_new_lead
            or settings_obj.sales_notification_email
        )
    )


def _increment_limit(key, *, limit, timeout):
    if cache.add(key, 1, timeout=timeout):
        return True
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return True
    return count <= limit


def inquiry_rate_limits_allow(ip_address, email, campaign_slug=""):
    if not ip_address or not email:
        return False
    ip_digest = hashlib.sha256(ip_address.encode("utf-8")).hexdigest()
    email_digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    checks = (
        _increment_limit(
            f"marketing-inquiry:ip:{ip_digest}",
            limit=INQUIRY_RATE_LIMIT,
            timeout=INQUIRY_RATE_WINDOW_SECONDS,
        ),
        _increment_limit(
            f"marketing-inquiry:email:{email_digest}",
            limit=INQUIRY_EMAIL_LIMIT,
            timeout=INQUIRY_EMAIL_WINDOW_SECONDS,
        ),
        _increment_limit(
            "marketing-inquiry:global",
            limit=INQUIRY_GLOBAL_LIMIT,
            timeout=INQUIRY_RATE_WINDOW_SECONDS,
        ),
    )
    if campaign_slug:
        campaign_digest = hashlib.sha256(campaign_slug.encode("utf-8")).hexdigest()
        checks += (
            _increment_limit(
                f"marketing-inquiry:campaign:{campaign_digest}",
                limit=INQUIRY_CAMPAIGN_LIMIT,
                timeout=INQUIRY_RATE_WINDOW_SECONDS,
            ),
        )
    return all(checks)


def inquiry_rate_limit_allows(ip_address):
    """Backward-compatible IP-only helper for existing callers."""
    if not ip_address:
        return False
    digest = hashlib.sha256(ip_address.encode("utf-8")).hexdigest()
    return _increment_limit(
        f"marketing-inquiry:ip:{digest}",
        limit=INQUIRY_RATE_LIMIT,
        timeout=INQUIRY_RATE_WINDOW_SECONDS,
    )


def _campaign_for_submission(slug):
    if not slug:
        return None
    campaign = marketing_selectors.campaign_by_slug(slug)
    if not campaign or not campaign.is_live:
        return None
    return campaign


@transaction.atomic
def create_public_lead(cleaned_data, *, ip_address=None):
    settings_obj = get_marketing_settings()
    if not marketing_inquiry_is_ready(settings_obj):
        raise ValueError("Marketing inquiries are currently closed.")
    if not cleaned_data.get("consent"):
        raise ValueError("Consent is required before submitting an inquiry.")

    campaign = _campaign_for_submission(cleaned_data.get("campaign_slug", ""))
    source = campaign.source if campaign else cleaned_data.get("utm_source", "")
    medium = campaign.medium if campaign else cleaned_data.get("utm_medium", "")
    campaign_tag = (
        (campaign.campaign_tag or campaign.slug)
        if campaign
        else cleaned_data.get("utm_campaign", "")
    )
    repeat = marketing_selectors.prior_leads_for_email(
        cleaned_data["contact_email"]
    ).exists()
    denomination = cleaned_data.get("denomination")
    if denomination and not marketing_selectors.public_denomination_exists(
        denomination.pk
    ):
        raise ValueError("Select an active denomination accepting public inquiries.")

    lead = marketing_repo.create_lead(
        contact_name=cleaned_data["contact_name"].strip(),
        contact_email=cleaned_data["contact_email"].strip().lower(),
        contact_phone=cleaned_data.get("contact_phone", "").strip(),
        organization_name=cleaned_data.get("organization_name", "").strip(),
        denomination=denomination,
        message=cleaned_data.get("message", "").strip(),
        campaign=campaign,
        utm_source=source,
        utm_medium=medium,
        utm_campaign=campaign_tag,
        consent_given=True,
        consent_text=settings_obj.consent_text,
        consented_at=timezone.now(),
        ip_address=ip_address,
        notification_status=(
            "PENDING"
            if settings_obj.notify_on_new_lead
            and settings_obj.sales_notification_email
            else "DISABLED"
        ),
    )
    platform_repo.create_platform_audit(
        user=None,
        denomination=lead.denomination,
        action="MARKETING_LEAD_SUBMIT",
        target_model="MarketingLead",
        target_id=str(lead.pk),
        summary="Public marketing inquiry submitted",
        details={
            "campaign_id": str(campaign.pk) if campaign else "",
            "repeat_inquiry": repeat,
        },
        ip_address=ip_address,
    )

    if lead.notification_status == "PENDING":
        transaction.on_commit(lambda: dispatch_lead_notification(lead.pk))
    return lead, repeat


def send_lead_notification(lead, recipient):
    context = {
        **get_email_branding_context(
            None,
            preheader="A new marketing inquiry needs review.",
        ),
        "lead": lead,
    }
    return send_platform_email(
        subject="New ChurchHub marketing inquiry",
        to=recipient,
        text_body=render_to_string("emails/marketing_lead_notification.txt", context),
        html_body=render_to_string("emails/marketing_lead_notification.html", context),
        fail_silently=False,
    )


def dispatch_lead_notification(lead_id):
    """Queue after commit when configured; otherwise deliver synchronously."""
    use_async = getattr(settings, "CHURCHHUB_ASYNC_EMAIL", False) and not getattr(
        settings, "CELERY_TASK_ALWAYS_EAGER", False
    )
    if use_async:
        try:
            from church_system.tasks import send_marketing_lead_notification_task

            send_marketing_lead_notification_task.delay(str(lead_id))
            return True
        except Exception:
            logger.warning(
                "Could not enqueue marketing lead notification %s; using synchronous fallback.",
                lead_id,
            )
    return deliver_lead_notification(lead_id)


def deliver_lead_notification(lead_id, *, raise_on_error=False):
    lead = marketing_selectors.lead_by_pk(lead_id)
    if not lead or lead.notification_status == "SENT":
        return bool(lead)
    settings_obj = get_marketing_settings()
    if not settings_obj.notify_on_new_lead or not settings_obj.sales_notification_email:
        lead.notification_status = "DISABLED"
        marketing_repo.save(
            lead,
            update_fields=["notification_status", "updated_at"],
        )
        return False

    lead.notification_attempts += 1
    try:
        sent = send_lead_notification(lead, settings_obj.sales_notification_email)
    except Exception as exc:
        lead.notification_status = "FAILED"
        lead.notification_error_code = type(exc).__name__[:80]
        marketing_repo.save(
            lead,
            update_fields=[
                "notification_status",
                "notification_attempts",
                "notification_error_code",
                "updated_at",
            ],
        )
        platform_repo.create_platform_audit(
            user=None,
            denomination=lead.denomination,
            action="MARKETING_LEAD_NOTIFY",
            target_model="MarketingLead",
            target_id=str(lead.pk),
            summary="Marketing lead notification failed",
            details={"status": "FAILED", "error_code": lead.notification_error_code},
        )
        logger.warning(
            "Marketing lead notification failed for lead %s (%s).",
            lead.pk,
            lead.notification_error_code,
        )
        if raise_on_error:
            raise
        return False

    lead.notification_status = "SENT" if sent else "FAILED"
    lead.notification_error_code = "" if sent else "NotSent"
    lead.notified_at = timezone.now() if sent else None
    marketing_repo.save(
        lead,
        update_fields=[
            "notification_status",
            "notification_attempts",
            "notification_error_code",
            "notified_at",
            "updated_at",
        ],
    )
    platform_repo.create_platform_audit(
        user=None,
        denomination=lead.denomination,
        action="MARKETING_LEAD_NOTIFY",
        target_model="MarketingLead",
        target_id=str(lead.pk),
        summary="Marketing lead notification updated",
        details={"status": lead.notification_status},
    )
    return sent


def anonymize_lead(lead, *, actor):
    if lead.status != "CLOSED":
        raise ValueError("Only closed leads may be anonymized.")
    if lead.anonymized_at:
        return lead
    lead.contact_name = "Anonymized lead"
    lead.contact_email = f"anonymized-{lead.pk}@redacted.invalid"
    lead.contact_phone = ""
    lead.organization_name = ""
    lead.message = ""
    lead.internal_notes = ""
    lead.ip_address = None
    lead.assigned_to = None
    lead.anonymized_at = timezone.now()
    lead.anonymized_by = actor
    return marketing_repo.save(lead)


def anonymize_expired_leads(*, actor):
    settings_obj = get_marketing_settings()
    cutoff = timezone.now() - timedelta(days=settings_obj.lead_retention_days)
    count = 0
    for lead in marketing_selectors.closed_leads_before(cutoff).iterator():
        anonymize_lead(lead, actor=actor)
        count += 1
    return count


def save_campaign(form, *, actor):
    campaign = form.save(commit=False)
    if not campaign.pk:
        campaign.created_by = actor
    return marketing_repo.save(campaign)


def archive_campaign(campaign):
    campaign.status = "ARCHIVED"
    return marketing_repo.save(campaign, update_fields=["status", "updated_at"])


def save_asset(form, *, actor):
    asset = form.save(commit=False)
    if not asset.pk:
        asset.created_by = actor
    return marketing_repo.save(asset)


def archive_asset(asset):
    asset.status = "ARCHIVED"
    return marketing_repo.save(asset, update_fields=["status", "updated_at"])


def update_lead(form):
    return marketing_repo.save(form.save(commit=False))


def save_marketing_settings(form):
    return marketing_repo.save(form.save(commit=False))
