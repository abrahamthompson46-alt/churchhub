"""Platform settings, subscription entitlements, and tenant limits."""

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from organization.models import Church, Conference, District, Zone

from .models import PlatformAnnouncement, PlatformAuditLog, PlatformPaymentMethod, SiteSettings, SubscriptionPlan, TenantSubscription

SETTINGS_CACHE_KEY = "platform:site_settings"
PLAN_CACHE_PREFIX = "platform:church_plan:"
ANNOUNCEMENT_CACHE_KEY = "platform:active_announcement"

FEATURE_FIELDS = {
    "payroll": "feature_payroll",
    "remittance": "feature_remittance",
    "ledger": "feature_ledger",
    "meetings": "feature_meetings",
    "advanced_reports": "feature_advanced_reports",
    "budgets": "feature_budgets",
    "giving_portal": "feature_giving_portal",
    "assets": "feature_assets",
}

GLOBAL_FEATURE_FIELDS = {
    "payroll": "global_enable_payroll",
    "remittance": "global_enable_remittance",
    "ledger": "global_enable_ledger",
    "meetings": "global_enable_meetings",
    "advanced_reports": "global_enable_advanced_reports",
    "budgets": "global_enable_budgets",
    "giving_portal": "global_enable_giving",
    "assets": "global_enable_assets",
}


def get_site_settings():
    cached = cache.get(SETTINGS_CACHE_KEY)
    if cached:
        return cached
    settings_obj = SiteSettings.load()
    cache.set(SETTINGS_CACHE_KEY, settings_obj, 300)
    return settings_obj


def clear_settings_cache():
    cache.delete(SETTINGS_CACHE_KEY)
    cache.delete(ANNOUNCEMENT_CACHE_KEY)


def build_platform_setup_checklist():
    """Guided platform setup items with done/pending status for Control Room."""
    from sitecontrol.models import Denomination

    settings_obj = get_site_settings()
    has_smtp = bool(settings_obj.smtp_host and (settings_obj.default_from_email or settings_obj.smtp_username))
    has_logo = bool(settings_obj.logo)
    has_plan = SubscriptionPlan.objects.filter(is_active=True).exists()
    has_default_plan = SubscriptionPlan.objects.filter(is_active=True, is_default=True).exists()
    has_payment = PlatformPaymentMethod.objects.filter(is_active=True).exists()
    has_denomination = Denomination.objects.filter(is_active=True).exists()
    has_support = bool(settings_obj.support_email)
    has_billing_copy = bool(settings_obj.billing_payment_instructions.strip())
    registration_configured = True  # always present; surface toggles as informational

    items = [
        {
            "id": "branding",
            "label": "Platform branding",
            "detail": "Upload a logo and set brand colors.",
            "done": has_logo,
            "url_name": "sitecontrol:branding",
            "icon": "bi-palette",
        },
        {
            "id": "email",
            "label": "Email / SMTP",
            "detail": "Configure host and from-address for invites and receipts.",
            "done": has_smtp,
            "url_name": "sitecontrol:email_settings",
            "icon": "bi-envelope-at",
        },
        {
            "id": "security",
            "label": "Security baseline",
            "detail": "Review password rules and platform IP allowlist.",
            "done": settings_obj.password_min_length >= 8,
            "url_name": "sitecontrol:security_settings",
            "icon": "bi-lock",
        },
        {
            "id": "plans",
            "label": "Subscription plans",
            "detail": "Create at least one active plan (mark a default).",
            "done": has_plan and has_default_plan,
            "url_name": "sitecontrol:plan_list",
            "icon": "bi-box-seam",
        },
        {
            "id": "payment_methods",
            "label": "Payment methods",
            "detail": "Add bank transfer or mobile money instructions.",
            "done": has_payment,
            "url_name": "sitecontrol:payment_method_list",
            "icon": "bi-wallet2",
        },
        {
            "id": "billing",
            "label": "Billing instructions",
            "detail": "Set default currency and payment copy for provisioning.",
            "done": has_billing_copy,
            "url_name": "sitecontrol:billing_settings",
            "icon": "bi-currency-exchange",
        },
        {
            "id": "denomination",
            "label": "Denomination / tenant",
            "detail": "Create an institution with terminology and branding.",
            "done": has_denomination,
            "url_name": "sitecontrol:denomination_list",
            "icon": "bi-layers",
        },
        {
            "id": "registration",
            "label": "Registration controls",
            "detail": "Decide public apply, invites, and church onboarding gates.",
            "done": registration_configured and has_support,
            "url_name": "sitecontrol:registration_settings",
            "icon": "bi-door-open",
        },
        {
            "id": "provision",
            "label": "Provision first church",
            "detail": "Create a live church tenant with admin invite.",
            "done": Church.objects.exists(),
            "url_name": "sitecontrol:tenant_provision",
            "icon": "bi-magic",
        },
    ]
    done_count = sum(1 for item in items if item["done"])
    return {
        "items": items,
        "done_count": done_count,
        "total_count": len(items),
        "percent": int(round((done_count / len(items)) * 100)) if items else 100,
        "is_complete": done_count == len(items),
    }


def log_platform_action(request, action, summary, *, target_model="", target_id="", details=None, denomination=None):
    ip = request.META.get("REMOTE_ADDR")
    if denomination is None:
        denomination = getattr(request, "denomination", None)
    PlatformAuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        denomination=denomination,
        action=action,
        target_model=target_model,
        target_id=str(target_id) if target_id else "",
        summary=summary,
        details=details or {},
        ip_address=ip,
    )


def get_active_platform_announcement():
    cached = cache.get(ANNOUNCEMENT_CACHE_KEY)
    if cached is not None:
        return cached
    now = timezone.now()
    announcement = (
        PlatformAnnouncement.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .order_by("-created_at")
        .first()
    )
    cache.set(ANNOUNCEMENT_CACHE_KEY, announcement, 120)
    return announcement


def ensure_default_payment_methods():
    """Create standard payment methods if none exist."""
    if PlatformPaymentMethod.objects.exists():
        return
    PlatformPaymentMethod.objects.bulk_create([
        PlatformPaymentMethod(
            name="Bank Transfer",
            method_type="BANK_TRANSFER",
            instructions="Pay via bank transfer and include your church code as reference.",
            is_default=True,
            sort_order=1,
        ),
        PlatformPaymentMethod(
            name="Mobile Money",
            method_type="MOBILE_MONEY",
            instructions="Send payment via mobile money and record the transaction ID.",
            sort_order=2,
        ),
    ])


def run_platform_seed_suite(*, church=None, reset_permissions=False):
    """
    One-click setup suite for platform owners: migrate + seed matrix/plans/payments/denominations.
    Optionally re-provision financial seeds for a church.
    """
    from django.core.management import call_command
    from io import StringIO

    from sitecontrol.denomination_services import ensure_builtin_denominations

    steps = []
    buf = StringIO()

    call_command("migrate", "--noinput", stdout=buf, verbosity=0)
    steps.append({"id": "migrate", "label": "Database migrations", "ok": True})

    seed_args = ["seed_permissions"]
    if reset_permissions:
        seed_args.append("--reset")
    call_command(*seed_args, stdout=buf, verbosity=0)
    steps.append({
        "id": "permissions",
        "label": "Permission matrix seeded" + (" (reset)" if reset_permissions else ""),
        "ok": True,
    })

    ensure_default_plans()
    steps.append({"id": "plans", "label": "Subscription plans ensured", "ok": True})

    ensure_default_payment_methods()
    steps.append({"id": "payments", "label": "Payment methods ensured", "ok": True})

    created = ensure_builtin_denominations() or []
    steps.append({
        "id": "denominations",
        "label": f"Built-in denominations updated ({len(created)} created)",
        "ok": True,
    })

    if church is not None:
        from sitecontrol.provisioning_services import reprovision_tenant_financials

        reprovision_tenant_financials(church)
        steps.append({
            "id": "church_financials",
            "label": f"Financial seeds re-provisioned for {church.name}",
            "ok": True,
        })

    return {
        "steps": steps,
        "ok": all(s["ok"] for s in steps),
        "message": f"Completed {len(steps)} setup step(s).",
    }


def build_price_snapshot(plan, billing_interval="MONTHLY"):
    return {
        "plan_id": str(plan.pk),
        "plan_code": plan.code,
        "plan_name": plan.name,
        "currency": plan.currency,
        "billing_interval": billing_interval,
        "price_monthly": str(plan.price_monthly),
        "price_yearly": str(plan.effective_yearly_price),
        "setup_fee": str(plan.setup_fee),
        "captured_at": timezone.now().isoformat(),
    }


def ensure_default_plans():
    """Create standard plans if none exist."""
    if SubscriptionPlan.objects.exists():
        return
    plans = [
        {
            "code": "starter",
            "name": "Starter",
            "description": "Core membership and basic finance for a single church.",
            "max_users": 5,
            "max_branches": 1,
            "feature_payroll": False,
            "feature_remittance": True,
            "feature_advanced_reports": False,
            "feature_assets": False,
            "is_default": False,
            "sort_order": 1,
        },
        {
            "code": "standard",
            "name": "Standard",
            "description": "Full finance, ledger, remittance, and meetings for growing churches.",
            "max_users": 25,
            "max_branches": 3,
            "feature_payroll": False,
            "feature_remittance": True,
            "feature_advanced_reports": True,
            "feature_assets": True,
            "is_default": False,
            "sort_order": 2,
        },
        {
            "code": "enterprise",
            "name": "Enterprise",
            "description": "Unlimited modules including payroll for multi-branch deployments.",
            "max_users": 100,
            "max_branches": 50,
            "feature_payroll": True,
            "feature_remittance": True,
            "feature_advanced_reports": True,
            "feature_assets": True,
            "is_default": True,
            "sort_order": 3,
        },
    ]
    for data in plans:
        SubscriptionPlan.objects.create(**data)


def get_default_plan():
    plan = SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()
    if plan:
        return plan
    return SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order").first()


def get_church_subscription(church):
    if not church:
        return None
    try:
        return church.subscription
    except TenantSubscription.DoesNotExist:
        return None


def ensure_church_subscription(church):
    sub = get_church_subscription(church)
    if sub:
        return sub
    plan = get_default_plan()
    if not plan:
        ensure_default_plans()
        plan = get_default_plan()
    return TenantSubscription.objects.create(church=church, plan=plan, status="ACTIVE")


def _plan_for_church(church):
    cache_key = f"{PLAN_CACHE_PREFIX}{church.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    sub = get_church_subscription(church)
    if not sub:
        sub = ensure_church_subscription(church)
    plan = sub.plan if sub and sub.is_operational else get_default_plan()
    cache.set(cache_key, plan, 300)
    return plan


def clear_church_plan_cache(church):
    if church:
        cache.delete(f"{PLAN_CACHE_PREFIX}{church.pk}")


def subscription_enforced():
    return get_site_settings().enforce_subscription_limits


def _global_feature_enabled(feature):
    field = GLOBAL_FEATURE_FIELDS.get(feature)
    if not field:
        return False
    settings_obj = get_site_settings()
    return bool(getattr(settings_obj, field, False))


def church_has_feature(church, feature):
    """Fail-closed feature entitlement check for a church tenant."""
    if not church:
        return False
    if feature not in FEATURE_FIELDS:
        return False
    if not _global_feature_enabled(feature):
        return False

    denomination = church.denomination
    if denomination:
        field = FEATURE_FIELDS[feature]
        if not getattr(denomination, field, True):
            return False

    sub = get_church_subscription(church)
    if not sub:
        sub = ensure_church_subscription(church)
    if not sub or not sub.is_operational:
        return False

    overrides = sub.feature_overrides or {}
    if feature in overrides:
        return bool(overrides[feature])

    if not subscription_enforced():
        return True

    field = FEATURE_FIELDS[feature]
    return bool(getattr(sub.plan, field, False))


def church_user_count(church):
    return User.objects.filter(church=church, is_active=True, is_platform_user=False).count()


def can_add_user_to_church(church):
    if not church:
        return False, "No church selected."
    if not subscription_enforced():
        return True, ""
    sub = get_church_subscription(church) or ensure_church_subscription(church)
    if not sub.is_operational:
        return False, "This church subscription is not active."
    limit = sub.effective_max_users()
    current = church_user_count(church)
    if current >= limit:
        return False, f"User limit reached ({current}/{limit}). Upgrade the subscription plan."
    return True, ""


def can_add_branch_to_district(district):
    if not district:
        return False, "No district selected."
    if not subscription_enforced():
        return True, ""
    churches = Church.objects.filter(district=district).select_related("subscription__plan")
    count = churches.count()
    if count == 0:
        return True, ""

    max_branches = 0
    has_operational = False
    for church in churches:
        sub = get_church_subscription(church)
        if not sub:
            continue
        if not sub.is_operational:
            continue
        has_operational = True
        max_branches = max(max_branches, sub.effective_max_branches())

    if not has_operational:
        return False, "Subscription is not active for this district."
    if count >= max_branches:
        return False, f"Branch limit reached ({count}/{max_branches}). Upgrade the subscription plan."
    return True, ""


def suspend_tenant(church, user, reason=""):
    """Suspend a church subscription and record lifecycle metadata."""
    sub = get_church_subscription(church) or ensure_church_subscription(church)
    sub.status = "SUSPENDED"
    sub.suspended_at = timezone.now()
    sub.suspended_by = user
    if reason:
        note = (sub.lifecycle_notes or "").strip()
        stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
        line = f"[{stamp}] Suspended: {reason}"
        sub.lifecycle_notes = f"{note}\n{line}".strip() if note else line
    sub.updated_by = user
    sub.save()
    clear_church_plan_cache(church)
    return sub


def reactivate_tenant(church, user):
    """Reactivate a suspended church subscription."""
    sub = get_church_subscription(church) or ensure_church_subscription(church)
    sub.status = "ACTIVE"
    sub.suspended_at = None
    sub.suspended_by = None
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    note = (sub.lifecycle_notes or "").strip()
    line = f"[{stamp}] Reactivated"
    sub.lifecycle_notes = f"{note}\n{line}".strip() if note else line
    sub.updated_by = user
    sub.save()
    clear_church_plan_cache(church)
    return sub


def offboard_tenant(church, user, reason=""):
    """
    Offboard a church tenant: expire subscription, deactivate institution users,
    and mark the church inactive. Data is retained for compliance (no hard delete).
    """
    sub = get_church_subscription(church) or ensure_church_subscription(church)
    sub.status = "EXPIRED"
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    note = (sub.lifecycle_notes or "").strip()
    detail = reason or "Offboarded by platform operator"
    line = f"[{stamp}] Offboarded: {detail}"
    sub.lifecycle_notes = f"{note}\n{line}".strip() if note else line
    sub.updated_by = user
    sub.save()

    User.objects.filter(church=church, is_platform_user=False, is_active=True).update(is_active=False)
    if hasattr(church, "is_active"):
        church.is_active = False
        church.save(update_fields=["is_active"])
    clear_church_plan_cache(church)
    return sub


def ip_allowed_for_platform(ip_address, settings_obj=None):
    """Return True when platform_ip_allowlist is empty or IP is listed."""
    settings_obj = settings_obj or get_site_settings()
    raw = (getattr(settings_obj, "platform_ip_allowlist", "") or "").strip()
    if not raw:
        return True
    allowed = {line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")}
    if not allowed:
        return True
    return (ip_address or "") in allowed


def expire_due_subscriptions():
    """Mark ACTIVE/TRIAL subscriptions past expires_at as EXPIRED. Returns count."""
    today = timezone.now().date()
    qs = TenantSubscription.objects.filter(
        status__in=("ACTIVE", "TRIAL"),
        expires_at__isnull=False,
        expires_at__lt=today,
    )
    count = 0
    for sub in qs.select_related("church"):
        sub.status = "EXPIRED"
        sub.save(update_fields=["status", "updated_at"])
        clear_church_plan_cache(sub.church)
        count += 1
    return count


def set_tenant_feature_overrides(sub, overrides):
    """Store feature override dict on a TenantSubscription."""
    cleaned = {}
    for key, value in (overrides or {}).items():
        if key in FEATURE_FIELDS:
            cleaned[key] = bool(value)
    sub.feature_overrides = cleaned
    sub.save(update_fields=["feature_overrides", "updated_at"])
    clear_church_plan_cache(sub.church)
    return sub


def assign_subscription(
    church,
    plan,
    status="ACTIVE",
    user=None,
    expires_at=None,
    billing_interval="MONTHLY",
    payment_method=None,
    payment_reference="",
    price_snapshot=None,
    started_at=None,
    next_billing_at=None,
):
    defaults = {
        "plan": plan,
        "status": status,
        "expires_at": expires_at,
        "updated_by": user,
        "billing_interval": billing_interval,
        "payment_method": payment_method,
        "payment_reference": payment_reference or "",
        "price_snapshot": price_snapshot or build_price_snapshot(plan, billing_interval),
    }
    if started_at is not None:
        defaults["started_at"] = started_at
    if next_billing_at is not None:
        defaults["next_billing_at"] = next_billing_at
    sub, _ = TenantSubscription.objects.update_or_create(
        church=church,
        defaults=defaults,
    )
    if hasattr(church, "__dict__") and "subscription" in church.__dict__:
        del church.__dict__["subscription"]
    clear_church_plan_cache(church)
    return sub


def platform_stats():
    from sitecontrol.registration_services import pending_application_count

    return {
        "churches": Church.objects.count(),
        "conferences": Conference.objects.count(),
        "zones": Zone.objects.count(),
        "districts": District.objects.count(),
        "active_subscriptions": TenantSubscription.objects.filter(status="ACTIVE").count(),
        "suspended": TenantSubscription.objects.filter(status="SUSPENDED").count(),
        "users": User.objects.filter(is_active=True, is_platform_user=False).count(),
        "operators": User.objects.filter(is_active=True, is_platform_user=True).count(),
        "plans": SubscriptionPlan.objects.filter(is_active=True).count(),
        "pending_applications": pending_application_count(),
    }


def tenant_health_alerts():
    alerts = []
    churches_without = Church.objects.filter(subscription__isnull=True).count()
    if churches_without:
        alerts.append({
            "level": "warning",
            "title": "Missing subscriptions",
            "detail": f"{churches_without} church(es) have no subscription assigned.",
            "url_name": "sitecontrol:subscription_seed",
        })

    suspended = TenantSubscription.objects.filter(status="SUSPENDED").count()
    if suspended:
        alerts.append({
            "level": "danger",
            "title": "Suspended tenants",
            "detail": f"{suspended} subscription(s) are suspended.",
            "url_name": "sitecontrol:subscription_list",
        })

    expired = TenantSubscription.objects.filter(status="EXPIRED").count()
    if expired:
        alerts.append({
            "level": "danger",
            "title": "Expired subscriptions",
            "detail": f"{expired} subscription(s) are marked expired.",
            "url_name": "sitecontrol:subscription_list",
        })

    if get_site_settings().maintenance_mode:
        alerts.append({
            "level": "info",
            "title": "Maintenance mode active",
            "detail": "Institution users cannot sign in.",
            "url_name": "sitecontrol:settings",
        })

    from sitecontrol.registration_services import pending_application_count

    pending_apps = pending_application_count()
    if pending_apps:
        alerts.append({
            "level": "warning",
            "title": "Pending registration applications",
            "detail": f"{pending_apps} church application(s) awaiting review.",
            "url_name": "sitecontrol:application_list",
        })

    over_limit = []
    if subscription_enforced():
        for sub in TenantSubscription.objects.select_related("church", "plan").filter(status="ACTIVE"):
            count = church_user_count(sub.church)
            limit = sub.effective_max_users()
            if count > limit:
                over_limit.append(sub.church.name)
    if over_limit:
        alerts.append({
            "level": "warning",
            "title": "User limit exceeded",
            "detail": ", ".join(over_limit[:5]) + ("…" if len(over_limit) > 5 else ""),
            "url_name": "sitecontrol:tenant_list",
        })

    return alerts


def tenant_detail_stats(church):
    sub = get_church_subscription(church) or ensure_church_subscription(church)
    member_count = getattr(church, "members", None)
    members = member_count.count() if member_count is not None else 0
    users = church_user_count(church)
    tx_count = church.transactions.count() if hasattr(church, "transactions") else 0
    return {
        "subscription": sub,
        "members": members,
        "users": users,
        "user_limit": sub.effective_max_users(),
        "transactions": tx_count,
        "district": church.district,
        "zone": church.zone,
        "conference": church.conference,
    }


def organization_tree_summary():
    return {
        "conferences": Conference.objects.annotate(
            zone_count=Count("zones", distinct=True),
        ).order_by("name")[:50],
        "church_count": Church.objects.count(),
    }
