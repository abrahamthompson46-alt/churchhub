"""Full-version activation requests from expired churches (in-app, no email)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from church_system.client_ip import get_client_ip
from dashboard.services import notify_users
from sitecontrol import repositories as repo
from sitecontrol.models import SubscriptionActivationRequest

User = get_user_model()


def church_denomination(church):
    conference = getattr(church, "conference", None)
    if conference is None:
        return None
    return getattr(conference, "denomination", None)


def pending_request_for_church(church):
    if church is None:
        return None
    return (
        SubscriptionActivationRequest.objects.filter(church=church, status="PENDING")
        .order_by("-updated_at")
        .first()
    )


def pending_activation_count_for_operator(user):
    from sitecontrol.platform_access import filter_platform_denomination

    qs = SubscriptionActivationRequest.objects.filter(status="PENDING")
    qs = filter_platform_denomination(qs, user)
    return qs.count()


def mark_activation_requests_activated(church, *, reviewer=None):
    if church is None:
        return 0
    now = timezone.now()
    return SubscriptionActivationRequest.objects.filter(
        church=church,
        status__in=("PENDING", "ACKNOWLEDGED"),
    ).update(
        status="ACTIVATED",
        reviewed_by=reviewer,
        reviewed_at=now,
    )


def _notify_platform_operators(activation_request):
    operators = User.objects.filter(is_platform_user=True, is_active=True)
    action_url = reverse(
        "sitecontrol:activation_request_detail",
        args=[activation_request.pk],
    )
    notify_users(
        operators,
        title="Full version request",
        message=(
            f"{activation_request.church_name} submitted payment reference "
            f"{activation_request.payment_reference} and requested the full version."
        ),
        category="SYSTEM",
        action_url=action_url,
    )


def submit_activation_request(*, church, subscription, user, cleaned_data, request=None):
    """Create or update the pending request and notify every platform operator."""
    denomination = church_denomination(church)
    ip_address = get_client_ip(request) if request is not None else None
    payload = {
        "subscription": subscription,
        "denomination": denomination,
        "submitted_by": user if getattr(user, "is_authenticated", False) else None,
        "church_name": cleaned_data["church_name"].strip(),
        "church_code": (cleaned_data.get("church_code") or "").strip(),
        "church_address": (cleaned_data.get("church_address") or "").strip(),
        "contact_name": cleaned_data["contact_name"].strip(),
        "contact_email": cleaned_data["contact_email"].strip(),
        "contact_phone": (cleaned_data.get("contact_phone") or "").strip(),
        "payment_reference": cleaned_data["payment_reference"].strip(),
        "notes": (cleaned_data.get("notes") or "").strip(),
        "ip_address": ip_address,
        "status": "PENDING",
    }

    with transaction.atomic():
        existing = pending_request_for_church(church)
        if existing:
            for field, value in payload.items():
                setattr(existing, field, value)
            repo.save_model(existing)
            activation_request = existing
        else:
            activation_request = repo.create_activation_request(church=church, **payload)

        from sitecontrol.services import log_platform_action

        if request is not None:
            log_platform_action(
                request,
                "ACTIVATION_REQUEST",
                f"Full version requested for {activation_request.church_name}",
                target_model="SubscriptionActivationRequest",
                target_id=activation_request.pk,
                denomination=denomination,
                details={
                    "church_id": str(church.pk),
                    "payment_reference": activation_request.payment_reference,
                },
            )

    _notify_platform_operators(activation_request)
    return activation_request
