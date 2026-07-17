"""Site owner control panel views."""

import csv
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from church_system.flash import flash_success
from organization.models import Church, Conference, District, Zone
from sitecontrol.checks import can_access_django_admin, platform_required, require_platform_capability
from sitecontrol.forms import (
    BillingSettingsForm,
    BrandingSettingsForm,
    EmailSettingsForm,
    FeatureRegistryForm,
    PlatformAnnouncementForm,
    PlatformOperatorForm,
    PlatformPaymentMethodForm,
    PlatformTenantSetupForm,
    SecuritySettingsForm,
    SiteSettingsForm,
    SubscriptionPlanForm,
    TenantChurchForm,
    TenantSubscriptionForm,
)
from sitecontrol.models import (
    PlatformAnnouncement,
    PlatformAuditLog,
    PlatformPaymentMethod,
    SiteSettings,
    SubscriptionPlan,
    TenantSubscription,
)
from sitecontrol.platform_access import (
    filter_audit_for_operator,
    filter_churches_for_operator,
    filter_subscriptions_for_operator,
    operator_can_access_denomination,
)
from sitecontrol.rbac import (
    CAP_EXPORT_AUDIT,
    CAP_IMPERSONATE,
    CAP_MANAGE_ANNOUNCEMENTS,
    CAP_MANAGE_EMAIL,
    CAP_MANAGE_FEATURES,
    CAP_MANAGE_OPERATORS,
    CAP_MANAGE_PLANS,
    CAP_MANAGE_SECURITY,
    CAP_MANAGE_SETTINGS,
    CAP_MANAGE_SUBSCRIPTIONS,
    CAP_MANAGE_TENANTS,
    CAP_OPS,
    CAP_VIEW,
    CAP_VIEW_AUDIT,
    operator_has_capability,
)
from sitecontrol.services import (
    assign_subscription,
    build_platform_setup_checklist,
    build_price_snapshot,
    clear_church_plan_cache,
    clear_settings_cache,
    ensure_default_payment_methods,
    expire_due_subscriptions,
    get_site_settings,
    log_platform_action,
    offboard_tenant,
    organization_tree_summary,
    platform_stats,
    reactivate_tenant,
    suspend_tenant,
    tenant_detail_stats,
    tenant_health_alerts,
)

IMPERSONATE_SESSION_KEY = "platform_impersonator_id"


def _breadcrumbs(*crumbs):
    return [{"label": c[0], **({"url": c[1]} if len(c) > 1 else {})} for c in crumbs]


def _require_tenant_access(request, church):
    church_denom = None
    if church.district_id:
        church_denom = church.district.zone.conference.denomination
    if church_denom and not operator_can_access_denomination(request.user, church_denom):
        raise PermissionDenied("You do not have access to this tenant.")


@platform_required
@require_platform_capability(CAP_VIEW)
def dashboard(request):
    stats = platform_stats()
    alerts = tenant_health_alerts()
    recent = filter_subscriptions_for_operator(
        TenantSubscription.objects.select_related("church", "plan"),
        request.user,
    ).order_by("-updated_at")[:8]
    recent_audit = filter_audit_for_operator(
        PlatformAuditLog.objects.select_related("user"),
        request.user,
    ).order_by("-created_at")[:6]
    churches_without = filter_churches_for_operator(
        Church.objects.filter(subscription__isnull=True),
        request.user,
    ).count()
    since = timezone.now() - timedelta(hours=24)
    audit_24h = filter_audit_for_operator(
        PlatformAuditLog.objects.filter(created_at__gte=since),
        request.user,
    ).count()
    settings_obj = get_site_settings()
    setup = build_platform_setup_checklist()
    return render(request, "sitecontrol/dashboard.html", {
        "stats": stats,
        "alerts": alerts,
        "recent_subscriptions": recent,
        "recent_audit": recent_audit,
        "churches_without_sub": churches_without,
        "audit_24h": audit_24h,
        "maintenance_mode": settings_obj.maintenance_mode,
        "can_breakglass_admin": can_access_django_admin(request.user),
        "setup": setup,
        "breadcrumbs": _breadcrumbs(("Control Room",)),
    })


@platform_required
@require_platform_capability(CAP_VIEW)
def setup_checklist(request):
    if request.method == "POST" and request.POST.get("action") == "run_seed_suite":
        if not operator_has_capability(request.user, CAP_OPS):
            raise PermissionDenied
        from sitecontrol.services import run_platform_seed_suite

        result = run_platform_seed_suite(
            reset_permissions=bool(request.POST.get("reset_permissions")),
        )
        log_platform_action(
            request,
            "PLATFORM_SEED_SUITE",
            result["message"],
            target_model="SiteSettings",
            details={"steps": [s["id"] for s in result["steps"]]},
        )
        flash_success(request, result["message"] + " No CLI required.")
        return redirect("sitecontrol:setup")

    setup = build_platform_setup_checklist()
    return render(request, "sitecontrol/setup.html", {
        "setup": setup,
        "can_run_seeds": operator_has_capability(request.user, CAP_OPS),
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Setup Guide",)),
    })


@platform_required
@require_platform_capability(CAP_VIEW)
def health(request):
    alerts = tenant_health_alerts()
    stats = platform_stats()
    ops_signals = _ops_signals()
    return render(request, "sitecontrol/health.html", {
        "alerts": alerts,
        "stats": stats,
        "ops_signals": ops_signals,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Tenant Health",)),
    })


def _ops_signals():
    signals = {"db_ok": False, "cache_ok": False, "settings_loaded": False}
    try:
        connection.ensure_connection()
        signals["db_ok"] = True
    except Exception:
        signals["db_ok"] = False
    try:
        from django.core.cache import cache

        cache.set("platform:ops_ping", "1", 10)
        signals["cache_ok"] = cache.get("platform:ops_ping") == "1"
    except Exception:
        signals["cache_ok"] = False
    try:
        get_site_settings()
        signals["settings_loaded"] = True
    except Exception:
        signals["settings_loaded"] = False
    return signals


@platform_required
@require_platform_capability(CAP_OPS)
def ops_health(request):
    settings_obj = SiteSettings.load()
    signals = _ops_signals()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "email_test":
            if not operator_has_capability(request.user, CAP_MANAGE_EMAIL) and not operator_has_capability(
                request.user, CAP_OPS
            ):
                raise PermissionDenied
            recipient = request.POST.get("recipient") or settings_obj.support_email or request.user.email
            try:
                from church_system.email_service import send_test_email

                send_test_email(recipient)
                log_platform_action(
                    request, "OPS_EMAIL_TEST", f"Test email sent to {recipient}",
                    target_model="SiteSettings",
                )
                flash_success(request, f"Test email sent to {recipient}.")
            except Exception as exc:
                messages.error(request, f"Email test failed: {exc}")
            return redirect("sitecontrol:ops_health")
        if action == "expire_subscriptions":
            count = expire_due_subscriptions()
            log_platform_action(
                request,
                "SUBSCRIPTIONS_EXPIRED",
                f"Expired {count} subscription(s) past due date",
                target_model="TenantSubscription",
                details={"count": count},
            )
            flash_success(request, f"Marked {count} subscription(s) as expired.")
            return redirect("sitecontrol:ops_health")
        if action == "run_seed_suite":
            from sitecontrol.services import run_platform_seed_suite

            church = None
            church_id = (request.POST.get("church_id") or "").strip()
            if church_id:
                church = filter_churches_for_operator(
                    Church.objects.filter(pk=church_id),
                    request.user,
                ).first()
            result = run_platform_seed_suite(
                church=church,
                reset_permissions=bool(request.POST.get("reset_permissions")),
            )
            log_platform_action(
                request,
                "PLATFORM_SEED_SUITE",
                result["message"],
                target_model="Church" if church else "SiteSettings",
                target_id=str(church.pk) if church else "",
                details={"steps": [s["id"] for s in result["steps"]]},
            )
            flash_success(request, result["message"] + " No CLI required.")
            return redirect("sitecontrol:ops_health")
    churches = filter_churches_for_operator(
        Church.objects.select_related("district").order_by("name"),
        request.user,
    )[:200]
    return render(request, "sitecontrol/ops.html", {
        "signals": signals,
        "settings_obj": settings_obj,
        "seed_churches": churches,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Operations",)),
    })


@platform_required
@require_platform_capability(CAP_VIEW_AUDIT)
def audit_log(request):
    qs = PlatformAuditLog.objects.select_related("user", "denomination").order_by("-created_at")
    qs = filter_audit_for_operator(qs, request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(summary__icontains=q) | Q(action__icontains=q) | Q(user__username__icontains=q))
    paginator = Paginator(qs, 40)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "sitecontrol/audit_log.html", {
        "page_obj": page,
        "query": q,
        "can_export_audit": operator_has_capability(request.user, CAP_EXPORT_AUDIT),
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Audit Log",)),
    })


@platform_required
@require_platform_capability(CAP_EXPORT_AUDIT)
def audit_export(request):
    qs = PlatformAuditLog.objects.select_related("user", "denomination").order_by("-created_at")
    qs = filter_audit_for_operator(qs, request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(summary__icontains=q) | Q(action__icontains=q) | Q(user__username__icontains=q))
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="platform-audit.csv"'
    writer = csv.writer(response)
    writer.writerow(["timestamp", "operator", "action", "summary", "denomination", "ip"])
    for entry in qs[:5000]:
        writer.writerow([
            entry.created_at.isoformat(),
            entry.user.username if entry.user_id else "",
            entry.action,
            entry.summary,
            entry.denomination.code if entry.denomination_id else "",
            entry.ip_address or "",
        ])
    log_platform_action(request, "AUDIT_EXPORT", "Audit log exported to CSV", target_model="PlatformAuditLog")
    return response


@platform_required
@require_platform_capability(CAP_MANAGE_SETTINGS)
def site_settings(request):
    settings_obj = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_settings_cache()
        log_platform_action(request, "SETTINGS_UPDATE", "General site settings updated", target_model="SiteSettings")
        flash_success(request, "Site settings saved.")
        return redirect("sitecontrol:settings")
    return render(request, "sitecontrol/settings.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("General Settings",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_SETTINGS)
def branding_settings(request):
    settings_obj = SiteSettings.load()
    form = BrandingSettingsForm(request.POST or None, request.FILES or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_settings_cache()
        log_platform_action(request, "SETTINGS_UPDATE", "Branding settings updated", target_model="SiteSettings")
        flash_success(request, "Branding saved.")
        return redirect("sitecontrol:branding")
    return render(request, "sitecontrol/branding.html", {
        "form": form,
        "settings_obj": settings_obj,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Branding",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_EMAIL)
def email_settings(request):
    from church_system.email_service import send_test_email, smtp_status

    settings_obj = SiteSettings.load()
    form = EmailSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST":
        action = request.POST.get("action") or "save"
        if action == "email_test":
            recipient = (
                request.POST.get("recipient")
                or settings_obj.support_email
                or request.user.email
            )
            if not recipient:
                messages.error(request, "Enter a recipient email address for the test.")
            else:
                try:
                    send_test_email(recipient)
                    log_platform_action(
                        request,
                        "OPS_EMAIL_TEST",
                        f"Test email sent to {recipient}",
                        target_model="SiteSettings",
                    )
                    flash_success(request, f"Test email sent to {recipient}.")
                except Exception as exc:
                    messages.error(request, f"Email test failed: {exc}")
            return redirect("sitecontrol:email_settings")

        if form.is_valid():
            form.save()
            clear_settings_cache()
            log_platform_action(request, "SETTINGS_UPDATE", "Email settings updated", target_model="SiteSettings")
            flash_success(request, "Email settings saved.")
            return redirect("sitecontrol:email_settings")
    return render(request, "sitecontrol/email_settings.html", {
        "form": form,
        "smtp_status": smtp_status(),
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Email",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_SECURITY)
def security_settings(request):
    settings_obj = SiteSettings.load()
    form = SecuritySettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_settings_cache()
        log_platform_action(request, "SETTINGS_UPDATE", "Security settings updated", target_model="SiteSettings")
        flash_success(request, "Security settings saved.")
        return redirect("sitecontrol:security_settings")
    return render(request, "sitecontrol/security_settings.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Security",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_FEATURES)
def feature_registry(request):
    settings_obj = SiteSettings.load()
    form = FeatureRegistryForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_settings_cache()
        log_platform_action(request, "FEATURE_UPDATE", "Global feature registry updated", target_model="SiteSettings")
        flash_success(request, "Feature registry saved.")
        return redirect("sitecontrol:features")
    return render(request, "sitecontrol/features.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Feature Registry",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_PLANS)
def plan_list(request):
    plans = SubscriptionPlan.objects.all()
    return render(request, "sitecontrol/plan_list.html", {
        "plans": plans,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Plans",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_PLANS)
def plan_edit(request, pk=None):
    plan = get_object_or_404(SubscriptionPlan, pk=pk) if pk else None
    form = SubscriptionPlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_platform_action(
            request, "PLAN_UPDATE", f"Plan '{form.instance.name}' saved",
            target_model="SubscriptionPlan", target_id=form.instance.pk,
        )
        flash_success(request, f"Plan '{form.instance.name}' saved.")
        return redirect("sitecontrol:plan_list")
    return render(request, "sitecontrol/plan_form.html", {
        "form": form,
        "plan": plan,
        "title": "Edit Plan" if plan else "New Plan",
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Plans", "/platform/plans/"), ("Edit" if plan else "New",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_SUBSCRIPTIONS)
def subscription_list(request):
    subs = filter_subscriptions_for_operator(
        TenantSubscription.objects.select_related("church", "plan", "church__district"),
        request.user,
    ).order_by("church__name")
    return render(request, "sitecontrol/subscription_list.html", {
        "subscriptions": subs,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Subscriptions",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_SUBSCRIPTIONS)
def subscription_edit(request, pk=None):
    sub = get_object_or_404(TenantSubscription, pk=pk) if pk else None
    if sub:
        _require_tenant_access(request, sub.church)
    form = TenantSubscriptionForm(request.POST or None, instance=sub)
    if not operator_has_global_access_safe(request.user):
        form.fields["church"].queryset = filter_churches_for_operator(
            form.fields["church"].queryset, request.user
        )
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        _require_tenant_access(request, instance.church)
        instance.updated_by = request.user
        if sub is None or "plan" in form.changed_data or "billing_interval" in form.changed_data:
            instance.price_snapshot = build_price_snapshot(
                instance.plan,
                instance.billing_interval,
            )
        instance.save()
        clear_church_plan_cache(instance.church)
        log_platform_action(
            request, "SUBSCRIPTION_UPDATE", f"Subscription for {instance.church.name} updated",
            target_model="TenantSubscription", target_id=instance.pk,
        )
        flash_success(request, f"Subscription for {instance.church.name} updated.")
        return redirect("sitecontrol:subscription_list")
    return render(request, "sitecontrol/subscription_form.html", {
        "form": form,
        "subscription": sub,
        "title": "Edit Subscription" if sub else "Assign Subscription",
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Subscriptions", "/platform/subscriptions/"), ("Edit" if sub else "Assign",)),
    })


def operator_has_global_access_safe(user):
    from sitecontrol.platform_access import operator_has_global_access

    return operator_has_global_access(user)


@platform_required
@require_platform_capability(CAP_MANAGE_SUBSCRIPTIONS)
def subscription_bulk_seed(request):
    from sitecontrol.services import get_default_plan

    plan = get_default_plan()
    if not plan:
        messages.error(request, "No subscription plan available.")
        return redirect("sitecontrol:subscription_list")

    count = 0
    churches = filter_churches_for_operator(
        Church.objects.filter(subscription__isnull=True),
        request.user,
    )
    for church in churches:
        assign_subscription(church, plan, user=request.user)
        count += 1
    log_platform_action(request, "SUBSCRIPTION_UPDATE", f"Default plan assigned to {count} church(es)")
    flash_success(request, f"Assigned '{plan.name}' to {count} church(es).")
    return redirect("sitecontrol:subscription_list")


@platform_required
@require_platform_capability(CAP_VIEW)
def tenant_list(request):
    qs = Church.objects.select_related("district__zone__conference", "subscription__plan").order_by("name")
    qs = filter_churches_for_operator(qs, request.user)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(district__name__icontains=q))
    if status:
        qs = qs.filter(subscription__status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "sitecontrol/tenant_list.html", {
        "page_obj": page,
        "query": q,
        "status_filter": status,
        "can_manage_tenants": operator_has_capability(request.user, CAP_MANAGE_TENANTS),
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Tenants",)),
    })


@platform_required
@require_platform_capability(CAP_VIEW)
def tenant_detail(request, pk):
    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination", "subscription__plan"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    stats = tenant_detail_stats(church)
    users = User.objects.filter(church=church, is_platform_user=False).order_by("username")[:20]
    return render(request, "sitecontrol/tenant_detail.html", {
        "church": church,
        "stats": stats,
        "users": users,
        "can_manage_lifecycle": operator_has_capability(request.user, CAP_MANAGE_TENANTS),
        "can_impersonate": operator_has_capability(request.user, CAP_IMPERSONATE),
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Tenants", "/platform/tenants/"), (church.name,)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
def tenant_edit(request, pk):
    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    form = TenantChurchForm(request.POST or None, instance=church)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_platform_action(
            request, "TENANT_UPDATE", f"Tenant '{church.name}' updated",
            target_model="Church", target_id=church.pk,
        )
        flash_success(request, f"Tenant '{church.name}' updated.")
        return redirect("sitecontrol:tenant_detail", pk=church.pk)
    return render(request, "sitecontrol/tenant_form.html", {
        "form": form,
        "church": church,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Tenants", "/platform/tenants/"), (church.name, f"/platform/tenants/{church.pk}/"), ("Edit",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
@require_POST
def tenant_suspend(request, pk):
    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    reason = request.POST.get("reason", "").strip()
    suspend_tenant(church, request.user, reason=reason)
    log_platform_action(
        request, "TENANT_SUSPEND", f"Tenant '{church.name}' suspended",
        target_model="Church", target_id=church.pk, details={"reason": reason},
    )
    flash_success(request, f"Tenant '{church.name}' suspended.")
    return redirect("sitecontrol:tenant_detail", pk=church.pk)


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
@require_POST
def tenant_reactivate(request, pk):
    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    reactivate_tenant(church, request.user)
    log_platform_action(
        request, "TENANT_REACTIVATE", f"Tenant '{church.name}' reactivated",
        target_model="Church", target_id=church.pk,
    )
    flash_success(request, f"Tenant '{church.name}' reactivated.")
    return redirect("sitecontrol:tenant_detail", pk=church.pk)


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
@require_POST
def tenant_offboard(request, pk):
    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    reason = request.POST.get("reason", "").strip()
    confirm = request.POST.get("confirm", "").strip().upper()
    if confirm != "OFFBOARD":
        messages.error(request, 'Type OFFBOARD in the confirmation field to proceed.')
        return redirect("sitecontrol:tenant_detail", pk=church.pk)
    offboard_tenant(church, request.user, reason=reason)
    log_platform_action(
        request, "TENANT_OFFBOARD", f"Tenant '{church.name}' offboarded",
        target_model="Church", target_id=church.pk, details={"reason": reason},
    )
    flash_success(request, f"Tenant '{church.name}' offboarded. Institution users deactivated; data retained.")
    return redirect("sitecontrol:tenant_detail", pk=church.pk)


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
@require_POST
def tenant_reprovision_financials(request, pk):
    from sitecontrol.provisioning_services import reprovision_tenant_financials

    church = get_object_or_404(
        Church.objects.select_related("district__zone__conference__denomination"),
        pk=pk,
    )
    _require_tenant_access(request, church)
    reprovision_tenant_financials(church, reviewer=request.user)
    log_platform_action(
        request,
        "TENANT_REPROVISION",
        f"Re-provisioned financials for '{church.name}'",
        target_model="Church",
        target_id=church.pk,
    )
    flash_success(request, f"Financial defaults re-provisioned for '{church.name}'.")
    return redirect("sitecontrol:tenant_detail", pk=church.pk)


@platform_required
@require_platform_capability(CAP_MANAGE_TENANTS)
def tenant_provision(request):
    from church_system.flash import flash_error
    from sitecontrol.provisioning_services import provision_tenant

    ensure_default_payment_methods()
    form = PlatformTenantSetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            church, sub, invitation = provision_tenant(
                setup_mode=data["setup_mode"],
                denomination=data["denomination"],
                district=data.get("district"),
                conference_name=data.get("conference_name", ""),
                conference_code=data.get("conference_code", ""),
                zone_name=data.get("zone_name", ""),
                zone_code=data.get("zone_code", ""),
                district_name=data.get("district_name", ""),
                district_code=data.get("district_code", ""),
                church_name=data["church_name"],
                church_code=data["church_code"],
                address=data.get("address", ""),
                admin_email=data["admin_email"],
                admin_username=data["admin_username"],
                admin_first_name=data.get("admin_first_name", ""),
                plan=data["plan"],
                status=data["status"],
                billing_interval=data["billing_interval"],
                payment_method=data.get("payment_method"),
                payment_reference=data.get("payment_reference", ""),
                trial_days=data.get("trial_days"),
                admin_role=data.get("admin_role"),
                send_invite=data.get("send_invite", True),
                reviewer=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            log_platform_action(
                request,
                "TENANT_PROVISION",
                f"Provisioned tenant '{church.name}'",
                target_model="Church",
                target_id=church.pk,
                denomination=data["denomination"],
                details={
                    "subscription_id": str(sub.pk),
                    "plan": sub.plan.code,
                    "invitation_id": str(invitation.pk) if invitation else "",
                },
            )
            flash_success(
                request,
                f"Tenant “{church.name}” provisioned with plan {sub.plan.name}."
                + (f" Invite sent to {data['admin_email']}." if invitation else ""),
                title="Tenant provisioned",
            )
            return redirect("sitecontrol:tenant_detail", pk=church.pk)
        except ValueError as exc:
            flash_error(request, str(exc), title="Provisioning failed")
    return render(request, "sitecontrol/tenant_provision.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Tenants", "/platform/tenants/"), ("Provision Tenant",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_PLANS)
def billing_settings(request):
    settings_obj = SiteSettings.load()
    form = BillingSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_settings_cache()
        log_platform_action(request, "SETTINGS_UPDATE", "Billing settings updated", target_model="SiteSettings")
        flash_success(request, "Billing settings saved.")
        return redirect("sitecontrol:billing_settings")
    return render(request, "sitecontrol/billing_settings.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Billing Settings",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_PLANS)
def payment_method_list(request):
    ensure_default_payment_methods()
    methods = PlatformPaymentMethod.objects.all()
    return render(request, "sitecontrol/payment_method_list.html", {
        "methods": methods,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Payment Methods",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_PLANS)
def payment_method_edit(request, pk=None):
    method = get_object_or_404(PlatformPaymentMethod, pk=pk) if pk else None
    form = PlatformPaymentMethodForm(request.POST or None, instance=method)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_platform_action(
            request,
            "PAYMENT_METHOD_UPDATE",
            f"Payment method '{form.instance.name}' saved",
            target_model="PlatformPaymentMethod",
            target_id=form.instance.pk,
        )
        flash_success(request, f"Payment method '{form.instance.name}' saved.")
        return redirect("sitecontrol:payment_method_list")
    return render(request, "sitecontrol/payment_method_form.html", {
        "form": form,
        "method": method,
        "title": "Edit Payment Method" if method else "New Payment Method",
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Payment Methods", "/platform/payment-methods/"),
            ("Edit" if method else "New",),
        ),
    })


@platform_required
@require_platform_capability(CAP_IMPERSONATE)
@require_POST
def impersonate_start(request, user_id):
    """Support operators may temporarily act as an institution user (audited)."""
    from django.contrib.auth import login

    target = get_object_or_404(User, pk=user_id, is_platform_user=False, is_active=True)
    if not target.church_id:
        messages.error(request, "Target user has no church assignment.")
        return redirect("sitecontrol:tenant_list")
    _require_tenant_access(request, target.church)
    if request.session.get(IMPERSONATE_SESSION_KEY):
        messages.error(request, "End the current impersonation session first.")
        return redirect("sitecontrol:tenant_detail", pk=target.church_id)

    request.session[IMPERSONATE_SESSION_KEY] = str(request.user.pk)
    log_platform_action(
        request,
        "IMPERSONATE_START",
        f"Impersonation started for '{target.username}'",
        target_model="User",
        target_id=target.pk,
        details={"church_id": str(target.church_id)},
        denomination=getattr(target.church, "denomination", None),
    )
    login(request, target, backend="django.contrib.auth.backends.ModelBackend")
    messages.warning(
        request,
        f"You are impersonating {target.username}. All actions are audited. Use End Impersonation when finished.",
    )
    return redirect("dashboard:home")


@require_POST
def impersonate_end(request):
    """
    Restore the original platform operator after support impersonation.

    Accessible while authenticated as the institution user (session key required).
    """
    from django.contrib.auth import login

    if not request.user.is_authenticated:
        return redirect("login")

    operator_id = request.session.pop(IMPERSONATE_SESSION_KEY, None)
    if not operator_id:
        messages.info(request, "No active impersonation session.")
        if getattr(request.user, "is_platform_user", False):
            return redirect("sitecontrol:dashboard")
        return redirect("dashboard:home")

    operator = User.objects.filter(pk=operator_id, is_platform_user=True, is_active=True).first()
    if not operator:
        messages.error(request, "Original platform operator could not be restored.")
        return redirect("login")

    target_username = request.user.username
    login(request, operator, backend="django.contrib.auth.backends.ModelBackend")
    log_platform_action(
        request,
        "IMPERSONATE_END",
        f"Impersonation ended for '{target_username}'",
        target_model="User",
        details={"restored_operator": operator.username},
    )
    flash_success(request, "Impersonation ended. You are back in the control room.")
    return redirect("sitecontrol:dashboard")


@platform_required
@require_platform_capability(CAP_VIEW)
def hierarchy(request):
    from django.db.models import Count
    from sitecontrol.platform_access import operator_has_global_access

    if operator_has_global_access(request.user):
        tree = organization_tree_summary()
        zones = Zone.objects.select_related("conference").order_by("conference__name", "name")[:100]
        districts = District.objects.select_related("zone__conference").order_by("zone__name", "name")[:100]
    else:
        denoms = request.user.managed_denominations.all()
        conferences = Conference.objects.filter(denomination__in=denoms).annotate(
            zone_count=Count("zones", distinct=True),
        ).order_by("name")[:50]
        tree = {
            "conferences": conferences,
            "church_count": Church.objects.filter(
                district__zone__conference__denomination__in=denoms
            ).count(),
        }
        zones = Zone.objects.filter(conference__denomination__in=denoms).select_related("conference").order_by(
            "conference__name", "name"
        )[:100]
        districts = District.objects.filter(zone__conference__denomination__in=denoms).select_related(
            "zone__conference"
        ).order_by("zone__name", "name")[:100]
    return render(request, "sitecontrol/hierarchy.html", {
        "tree": tree,
        "zones": zones,
        "districts": districts,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Organization",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_OPERATORS)
def operator_list(request):
    operators = User.objects.filter(is_platform_user=True).prefetch_related("managed_denominations").order_by("username")
    return render(request, "sitecontrol/operator_list.html", {
        "operators": operators,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Platform Operators",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_OPERATORS)
def operator_create(request):
    form = PlatformOperatorForm(request.POST or None, is_create=True, actor=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        action = "OPERATOR_CREATE"
        if user.is_superuser:
            log_platform_action(
                request, "BREAKGLASS_GRANT", f"Break-glass granted to '{user.username}'",
                target_model="User", target_id=user.pk,
            )
        log_platform_action(
            request, action, f"Platform operator '{user.username}' created",
            target_model="User", target_id=user.pk,
        )
        flash_success(request, f"Operator '{user.username}' created.")
        return redirect("sitecontrol:operator_list")
    return render(request, "sitecontrol/operator_form.html", {
        "form": form,
        "title": "New Platform Operator",
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Operators", "/platform/operators/"), ("New",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_OPERATORS)
def operator_edit(request, pk):
    operator = get_object_or_404(User, pk=pk, is_platform_user=True)
    form = PlatformOperatorForm(request.POST or None, instance=operator, actor=request.user)
    if request.method == "POST" and form.is_valid():
        was_super = operator.is_superuser
        user = form.save()
        if user.is_superuser and not was_super:
            log_platform_action(
                request, "BREAKGLASS_GRANT", f"Break-glass granted to '{user.username}'",
                target_model="User", target_id=user.pk,
            )
        log_platform_action(
            request, "OPERATOR_UPDATE", f"Platform operator '{user.username}' updated",
            target_model="User", target_id=user.pk,
        )
        flash_success(request, f"Operator '{user.username}' updated.")
        return redirect("sitecontrol:operator_list")
    return render(request, "sitecontrol/operator_form.html", {
        "form": form,
        "operator": operator,
        "title": f"Edit {operator.username}",
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Operators", "/platform/operators/"), (operator.username,)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_OPERATORS)
@require_POST
def operator_deactivate(request, pk):
    operator = get_object_or_404(User, pk=pk, is_platform_user=True)
    if operator.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("sitecontrol:operator_list")
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    log_platform_action(
        request, "OPERATOR_DEACTIVATE", f"Platform operator '{operator.username}' deactivated",
        target_model="User", target_id=operator.pk,
    )
    flash_success(request, f"Operator '{operator.username}' deactivated.")
    return redirect("sitecontrol:operator_list")


@platform_required
@require_platform_capability(CAP_MANAGE_ANNOUNCEMENTS)
def announcement_list(request):
    items = PlatformAnnouncement.objects.select_related("created_by").order_by("-created_at")
    return render(request, "sitecontrol/announcement_list.html", {
        "announcements": items,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Announcements",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_ANNOUNCEMENTS)
def announcement_edit(request, pk=None):
    item = get_object_or_404(PlatformAnnouncement, pk=pk) if pk else None
    form = PlatformAnnouncementForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        if not instance.created_by_id:
            instance.created_by = request.user
        instance.save()
        clear_settings_cache()
        log_platform_action(
            request, "ANNOUNCEMENT_UPDATE", f"Announcement '{instance.title}' saved",
            target_model="PlatformAnnouncement", target_id=instance.pk,
        )
        flash_success(request, "Announcement saved.")
        return redirect("sitecontrol:announcement_list")
    return render(request, "sitecontrol/announcement_form.html", {
        "form": form,
        "announcement": item,
        "title": "Edit Announcement" if item else "New Announcement",
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Announcements", "/platform/announcements/"), ("Edit" if item else "New",)),
    })
