"""Denomination billing and audit rollups for platform operators."""

from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from sitecontrol import selectors


def denomination_church_queryset(denomination):
    return selectors.churches_for_denomination(denomination)


def denomination_billing_summary(denomination):
    churches = denomination_church_queryset(denomination)
    subs = selectors.subscriptions_for_churches(churches)
    active = subs.filter(status="ACTIVE")
    trial = subs.filter(status="TRIAL")
    suspended = subs.filter(status__in=("SUSPENDED", "EXPIRED"))
    mrr = sum((s.plan.price_monthly for s in active), Decimal("0"))
    return {
        "church_count": churches.count(),
        "subscription_count": subs.count(),
        "active_count": active.count(),
        "trial_count": trial.count(),
        "suspended_count": suspended.count(),
        "churches_without_plan": churches.filter(subscription__isnull=True).count(),
        "mrr": mrr,
        "plans": (
            subs.values("plan__name", "plan__code")
            .annotate(count=Count("id"))
            .order_by("-count")
        ),
    }


def denomination_audit_log(denomination, *, limit=50):
    church_ids = list(denomination_church_queryset(denomination).values_list("pk", flat=True))
    church_id_strings = {str(pk) for pk in church_ids}
    return selectors.denomination_scoped_audit(
        denomination, church_id_strings, limit=limit
    )


def all_denominations_billing_rollups():
    rollups = []
    for denom in selectors.active_denominations_ordered():
        summary = denomination_billing_summary(denom)
        rollups.append({"denomination": denom, **summary})
    return rollups


def tenant_health_alerts_for_denomination(denomination):
    alerts = []
    summary = denomination_billing_summary(denomination)
    if summary["churches_without_plan"]:
        alerts.append({
            "level": "warning",
            "text": f"{summary['churches_without_plan']} church(es) without a subscription plan.",
        })
    if summary["suspended_count"]:
        alerts.append({
            "level": "danger",
            "text": f"{summary['suspended_count']} suspended or expired subscription(s).",
        })
    pending_apps = denomination.tenant_applications.filter(status="PENDING").count()
    if pending_apps:
        alerts.append({
            "level": "info",
            "text": f"{pending_apps} pending registration application(s).",
        })
    return alerts
