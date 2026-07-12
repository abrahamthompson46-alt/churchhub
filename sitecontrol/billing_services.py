"""Denomination billing and audit rollups for platform operators."""

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from organization.models import Church
from sitecontrol.models import Denomination, PlatformAuditLog, TenantSubscription


def denomination_church_queryset(denomination):
    return Church.objects.filter(district__zone__conference__denomination=denomination)


def denomination_billing_summary(denomination):
    churches = denomination_church_queryset(denomination)
    subs = TenantSubscription.objects.filter(church__in=churches).select_related("plan", "church")
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
    qs = PlatformAuditLog.objects.select_related("user").filter(
        Q(denomination=denomination)
        | Q(target_model="Denomination", target_id=str(denomination.pk))
        | Q(target_model="Church", target_id__in=church_id_strings)
        | Q(target_model="TenantApplication", details__denomination_id=str(denomination.pk))
    ).order_by("-created_at")[:limit]
    return qs


def all_denominations_billing_rollups():
    rollups = []
    for denom in Denomination.objects.filter(is_active=True).order_by("name"):
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
