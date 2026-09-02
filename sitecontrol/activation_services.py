"""Full-version activation requests from expired churches (in-app, no email)."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from church_system.client_ip import get_client_ip
from dashboard.services import notify_user, notify_users
from sitecontrol import repositories as repo
from sitecontrol.models import SubscriptionActivationRequest, TenantSubscription

User = get_user_model()

EXPIRY_WARNING_DAYS = 7
SESSION_PAYMENT_CONFIRMED = "upgrade_payment_confirmed"
SESSION_BILLING_INTERVAL = "upgrade_billing_interval"
SESSION_PAY_CHURCH_ID = "upgrade_payment_church_id"
PAYMENT_REF_IN_USE = (
    "This payment reference was already used for another church."
)


def church_denomination(church):
    conference = getattr(church, "conference", None)
    if conference is None:
        return None
    return getattr(conference, "denomination", None)


def normalize_payment_reference(raw: str) -> str:
    return " ".join((raw or "").split()).upper()


def payment_reference_in_use(normalized: str, *, church) -> bool:
    if not normalized or church is None:
        return False
    return (
        SubscriptionActivationRequest.objects.exclude(church=church)
        .exclude(status="REJECTED")
        .filter(payment_reference_normalized=normalized)
        .exists()
    )


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


def days_until_expiry(subscription) -> int | None:
    if subscription is None or not subscription.expires_at:
        return None
    return (subscription.expires_at - timezone.now().date()).days


def is_within_expiry_warning(subscription) -> bool:
    days = days_until_expiry(subscription)
    return days is not None and 1 <= days <= EXPIRY_WARNING_DAYS


def can_use_upgrade_flow(subscription) -> bool:
    if subscription is None:
        return True
    if not subscription.is_operational:
        return True
    return is_within_expiry_warning(subscription)


def expiry_warning_context(subscription) -> dict | None:
    if not is_within_expiry_warning(subscription):
        return None
    days = days_until_expiry(subscription)
    return {
        "days": days,
        "expires_at": subscription.expires_at,
        "pay_url": reverse("subscription_pay"),
    }


def maybe_notify_expiry_warning(request, user, church, subscription) -> None:
    """Create one in-app notice per church expiry date (no email)."""
    if church is None or user is None or getattr(user, "is_platform_user", False):
        return
    info = expiry_warning_context(subscription)
    if not info:
        return
    session = getattr(request, "session", None)
    if session is None:
        return
    key = f"expiry_warn:{church.pk}:{subscription.expires_at.isoformat()}"
    if session.get(key):
        return
    notify_user(
        user,
        title="Subscription ending soon",
        message=(
            f"Access for {church.name} ends in {info['days']} day(s) "
            f"({subscription.expires_at.isoformat()}). Pay now, then send upgrade details."
        ),
        category="SYSTEM",
        action_url=info["pay_url"],
    )
    session[key] = True


def plan_price_for_interval(plan, interval: str) -> Decimal | None:
    if plan is None:
        return None
    if interval == "YEARLY":
        price = plan.effective_yearly_price
    else:
        price = plan.price_monthly
    if price is None:
        return None
    return Decimal(price)


def store_payment_confirmation(session, *, church, billing_interval: str) -> None:
    session[SESSION_PAYMENT_CONFIRMED] = True
    session[SESSION_BILLING_INTERVAL] = billing_interval
    session[SESSION_PAY_CHURCH_ID] = str(church.pk)


def payment_confirmation_for(session, church) -> str | None:
    """Return billing interval if this church completed the pay step."""
    if not session or church is None:
        return None
    if not session.get(SESSION_PAYMENT_CONFIRMED):
        return None
    if session.get(SESSION_PAY_CHURCH_ID) != str(church.pk):
        return None
    interval = session.get(SESSION_BILLING_INTERVAL) or "MONTHLY"
    if interval not in {choice[0] for choice in TenantSubscription.BILLING_INTERVALS}:
        return "MONTHLY"
    return interval


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
    amount_bit = ""
    if activation_request.amount is not None:
        amount_bit = (
            f" ({activation_request.currency} {activation_request.amount} "
            f"{activation_request.get_billing_interval_display()})"
        )
    notify_users(
        operators,
        title="Full version request",
        message=(
            f"{activation_request.church_name} submitted payment reference "
            f"{activation_request.payment_reference}{amount_bit} "
            f"and requested the full version."
        ),
        category="SYSTEM",
        action_url=action_url,
    )


def submit_activation_request(*, church, subscription, user, cleaned_data, request=None):
    """Create or update the pending request and notify every platform operator."""
    normalized = normalize_payment_reference(cleaned_data["payment_reference"])
    if payment_reference_in_use(normalized, church=church):
        raise ValueError(PAYMENT_REF_IN_USE)

    denomination = church_denomination(church)
    ip_address = get_client_ip(request) if request is not None else None
    interval = cleaned_data.get("billing_interval") or "MONTHLY"
    plan = subscription.plan if subscription else None
    amount = plan_price_for_interval(plan, interval)
    currency = ""
    if request is not None:
        from sitecontrol.services import get_site_settings

        currency = (get_site_settings().default_billing_currency or "").strip()
    if plan and getattr(plan, "currency", None):
        currency = plan.currency or currency

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
        "payment_reference_normalized": normalized,
        "billing_interval": interval,
        "amount": amount,
        "currency": currency,
        "plan_name": plan.name if plan else "",
        "notes": (cleaned_data.get("notes") or "").strip(),
        "ip_address": ip_address,
        "status": "PENDING",
    }
    receipt = cleaned_data.get("receipt")
    if receipt:
        payload["receipt"] = receipt

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
                    "billing_interval": interval,
                    "amount": str(amount) if amount is not None else "",
                },
            )

    _notify_platform_operators(activation_request)
    return activation_request
