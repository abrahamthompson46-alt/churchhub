"""Platform settings, subscription entitlements, and tenant limits."""

from django.core.cache import cache
from django.utils import timezone

from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.models import PlatformPaymentMethod, SiteSettings, TenantSubscription

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
    "contribution_campaigns": "feature_contribution_campaigns",
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
    "contribution_campaigns": "global_enable_contributions",
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
    settings_obj = get_site_settings()
    has_smtp = bool(settings_obj.smtp_host and (settings_obj.default_from_email or settings_obj.smtp_username))
    has_logo = bool(settings_obj.logo)
    has_plan = selectors.active_plan_exists()
    has_default_plan = selectors.active_default_plan_exists()
    has_payment = selectors.active_payment_method_exists()
    has_denomination = selectors.active_denomination_exists()
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
            "done": selectors.churches_exist(),
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
    repo.create_platform_audit(
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
    announcement = selectors.active_platform_announcement_now(now)
    cache.set(ANNOUNCEMENT_CACHE_KEY, announcement, 120)
    return announcement


def ensure_default_payment_methods():
    """Create standard payment methods if none exist."""
    if selectors.any_payment_method_exists():
        return
    repo.bulk_create_payment_methods([
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


def run_church_seed_suite(church):
    """Re-run all church-scoped seeds (financials, catalogs, settlement policies)."""
    from members.lookups import ensure_member_form_catalogs
    from organization.services import provision_church
    from remittance.services import ensure_hierarchy_settlement_policies

    steps = []
    provision_church(church, force=True)
    steps.append({
        "id": "financials",
        "label": f"Financial & module seeds for {church.name}",
        "ok": True,
    })

    counts = ensure_member_form_catalogs(church)
    steps.append({
        "id": "member_catalogs",
        "label": f"Member form catalogs ({sum(counts.values())} items)",
        "ok": True,
    })

    ensure_hierarchy_settlement_policies(church)
    steps.append({
        "id": "settlement",
        "label": "Hierarchy settlement policies",
        "ok": True,
    })
    return {
        "steps": steps,
        "ok": True,
        "message": f"Church seed suite completed for {church.name}.",
    }


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
        church_result = run_church_seed_suite(church)
        steps.extend(church_result["steps"])

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
    if selectors.any_plan_exists():
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
        repo.create_subscription_plan(**data)


def get_default_plan():
    plan = selectors.default_active_plan()
    if plan:
        return plan
    return selectors.first_active_plan_by_sort()


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
    return repo.create_tenant_subscription(church=church, plan=plan, status="ACTIVE")


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
    if not hasattr(settings_obj, field):
        # Pre-migration column: treat as enabled until migrate adds the flag.
        return True
    return bool(getattr(settings_obj, field, True))


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
        if hasattr(denomination, field) and not getattr(denomination, field, True):
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
    plan = sub.plan
    if not hasattr(plan, field):
        return True
    return bool(getattr(plan, field, True))


def church_user_count(church):
    return selectors.church_user_count(church)


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
    churches = selectors.churches_in_district_with_subscription(district)
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
    repo.save_subscription(sub)
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
    repo.save_subscription(sub)
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
    repo.save_subscription(sub)

    repo.deactivate_institution_users_for_church(church)
    if hasattr(church, "is_active"):
        church.is_active = False
        repo.save_church(church, update_fields=["is_active"])
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


def platform_ip_allowlist_configured(settings_obj=None) -> bool:
    """True when at least one non-comment IP/CIDR line is configured."""
    settings_obj = settings_obj or get_site_settings()
    raw = (getattr(settings_obj, "platform_ip_allowlist", "") or "").strip()
    if not raw:
        return False
    return any(
        line.strip() and not line.strip().startswith("#")
        for line in raw.splitlines()
    )


def expire_due_subscriptions():
    """Mark ACTIVE/TRIAL subscriptions past expires_at as EXPIRED. Returns count."""
    today = timezone.now().date()
    qs = selectors.subscriptions_due_to_expire(today)
    count = 0
    for sub in qs:
        sub.status = "EXPIRED"
        repo.save_subscription(sub, update_fields=["status", "updated_at"])
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
    repo.save_subscription(sub, update_fields=["feature_overrides", "updated_at"])
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
    sub, _ = repo.update_or_create_tenant_subscription(
        church=church,
        defaults=defaults,
    )
    if hasattr(church, "__dict__") and "subscription" in church.__dict__:
        del church.__dict__["subscription"]
    clear_church_plan_cache(church)
    return sub


def record_subscription_payment(
    subscription,
    *,
    user=None,
    payment_method=None,
    payment_reference="",
    paid_at=None,
    reactivate=True,
    notes="",
):
    """Record payment against a tenant subscription and advance billing window."""
    from dateutil.relativedelta import relativedelta

    now = timezone.now()
    paid_at = paid_at or now
    if timezone.is_naive(paid_at):
        paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())

    subscription.last_payment_at = paid_at
    if payment_method is not None:
        subscription.payment_method = payment_method
    if payment_reference:
        subscription.payment_reference = payment_reference.strip()

    if subscription.billing_interval == "YEARLY":
        delta = relativedelta(years=1)
    else:
        delta = relativedelta(months=1)

    paid_date = paid_at.date()
    base = subscription.next_billing_at or paid_date
    if base < paid_date:
        base = paid_date
    subscription.next_billing_at = base + delta

    if subscription.expires_at:
        subscription.expires_at = max(subscription.expires_at, subscription.next_billing_at)
    else:
        subscription.expires_at = subscription.next_billing_at

    if reactivate and subscription.status in ("EXPIRED", "SUSPENDED", "TRIAL"):
        subscription.status = "ACTIVE"
        subscription.suspended_at = None
        subscription.suspended_by = None

    if notes:
        stamp = paid_at.strftime("%Y-%m-%d %H:%M")
        prior = (subscription.lifecycle_notes or "").strip()
        line = f"[{stamp}] Payment recorded"
        if payment_reference:
            line += f" ({payment_reference.strip()})"
        line += f": {notes.strip()}"
        subscription.lifecycle_notes = f"{prior}\n{line}".strip() if prior else line

    if user is not None:
        subscription.updated_by = user

    repo.save_subscription(subscription)
    clear_church_plan_cache(subscription.church)
    return subscription


def platform_stats():
    from sitecontrol.registration_services import pending_application_count

    return {
        "churches": selectors.church_count(),
        "conferences": selectors.conference_count(),
        "zones": selectors.zone_count(),
        "districts": selectors.district_count(),
        "active_subscriptions": selectors.active_subscription_count(),
        "suspended": selectors.subscription_status_count("SUSPENDED"),
        "users": selectors.active_institution_user_count(),
        "operators": selectors.active_operator_count(),
        "plans": selectors.active_plans_ordered().count(),
        "pending_applications": pending_application_count(),
    }


def tenant_health_alerts():
    alerts = []
    churches_without = selectors.churches_without_subscription_count()
    if churches_without:
        alerts.append({
            "level": "warning",
            "title": "Missing subscriptions",
            "detail": f"{churches_without} church(es) have no subscription assigned.",
            "url_name": "sitecontrol:subscription_seed",
        })

    suspended = selectors.subscription_status_count("SUSPENDED")
    if suspended:
        alerts.append({
            "level": "danger",
            "title": "Suspended tenants",
            "detail": f"{suspended} subscription(s) are suspended.",
            "url_name": "sitecontrol:subscription_list",
        })

    expired = selectors.subscription_status_count("EXPIRED")
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
        for sub in selectors.active_subscriptions_with_plan():
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
        "conferences": selectors.organization_tree_conferences(),
        "church_count": selectors.church_count(),
    }
