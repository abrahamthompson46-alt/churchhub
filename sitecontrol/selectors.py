"""
Read/query helpers for the sitecontrol / platform domain.

Services, views, and forms call selectors for denominations, plans,
subscriptions, applications, audit, and settings-related querysets.
Business rules stay in services; persistence stays in repositories.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User
from organization.models import Church, Conference, District, Zone
from sitecontrol.models import (
    Denomination,
    PlatformAnnouncement,
    PlatformAuditLog,
    PlatformPaymentMethod,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)


# ---------------------------------------------------------------------------
# Denominations
# ---------------------------------------------------------------------------


def active_denominations_ordered():
    return Denomination.objects.filter(is_active=True).order_by("name")


def public_registration_denominations():
    return Denomination.objects.filter(
        is_active=True, allow_public_registration=True
    ).order_by("name")


def active_denomination_exists() -> bool:
    return Denomination.objects.filter(is_active=True).exists()


def public_registration_denomination_exists() -> bool:
    return Denomination.objects.filter(
        is_active=True, allow_public_registration=True
    ).exists()


def denomination_by_pk(pk):
    return Denomination.objects.filter(pk=pk).first()


def denomination_by_code(*, code, active_only=True, allow_public_registration=None):
    qs = Denomination.objects.filter(code=code)
    if active_only:
        qs = qs.filter(is_active=True)
    if allow_public_registration is not None:
        qs = qs.filter(allow_public_registration=allow_public_registration)
    return qs.first()


def get_denomination_or_404(pk):
    return get_object_or_404(Denomination, pk=pk)


# ---------------------------------------------------------------------------
# Plans / payment methods
# ---------------------------------------------------------------------------


def active_plans_ordered():
    return SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order")


def all_plans():
    return SubscriptionPlan.objects.all()


def active_plan_exists() -> bool:
    return SubscriptionPlan.objects.filter(is_active=True).exists()


def active_default_plan_exists() -> bool:
    return SubscriptionPlan.objects.filter(is_active=True, is_default=True).exists()


def any_plan_exists() -> bool:
    return SubscriptionPlan.objects.exists()


def default_active_plan():
    return SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()


def first_active_plan_by_sort():
    return SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order").first()


def get_plan_or_404(pk):
    return get_object_or_404(SubscriptionPlan, pk=pk)


def active_payment_methods_ordered():
    return PlatformPaymentMethod.objects.filter(is_active=True).order_by("sort_order", "name")


def active_payment_method_exists() -> bool:
    return PlatformPaymentMethod.objects.filter(is_active=True).exists()


def any_payment_method_exists() -> bool:
    return PlatformPaymentMethod.objects.exists()


def get_payment_method_or_404(pk):
    return get_object_or_404(PlatformPaymentMethod, pk=pk)


def empty_plans():
    return SubscriptionPlan.objects.none()


def empty_payment_methods():
    return PlatformPaymentMethod.objects.none()


# ---------------------------------------------------------------------------
# Subscriptions / churches
# ---------------------------------------------------------------------------


def churches_exist() -> bool:
    return Church.objects.exists()


def church_count() -> int:
    return Church.objects.count()


def churches_without_subscription():
    return Church.objects.filter(subscription__isnull=True)


def churches_without_subscription_count() -> int:
    return Church.objects.filter(subscription__isnull=True).count()


def churches_ordered_with_district():
    return Church.objects.select_related("district").order_by("name")


def churches_tenant_list_base():
    return Church.objects.select_related(
        "district__zone__conference", "subscription__plan"
    ).order_by("name")


def church_detail_qs():
    return Church.objects.select_related(
        "district__zone__conference__denomination", "subscription__plan"
    )


def get_church_or_404(qs, pk):
    return get_object_or_404(qs, pk=pk)


def churches_for_denomination(denomination):
    return Church.objects.filter(
        district__zone__conference__denomination=denomination
    )


def churches_in_district_with_subscription(district):
    return Church.objects.filter(district=district).select_related("subscription__plan")


def church_code_exists_in_district(district, code) -> bool:
    return Church.objects.filter(district=district, code=code).exists()


def church_code_exists(code) -> bool:
    return Church.objects.filter(code=code).exists()


def conference_count_for_denomination(denomination) -> int:
    return Conference.objects.filter(denomination=denomination).count()


def church_count_for_denomination(denomination) -> int:
    return Church.objects.filter(
        district__zone__conference__denomination=denomination
    ).count()


def orphan_conferences_assign_count(default_denomination) -> int:
    return Conference.objects.filter(denomination__isnull=True).count()


def subscriptions_for_churches(churches):
    return TenantSubscription.objects.filter(church__in=churches).select_related(
        "plan", "church"
    )


def subscriptions_list_base():
    return TenantSubscription.objects.select_related(
        "church", "plan", "church__district"
    )


def subscription_detail_qs():
    return TenantSubscription.objects.select_related("church", "plan")


def get_subscription_or_404(pk):
    return get_object_or_404(
        TenantSubscription.objects.select_related("church", "plan"), pk=pk
    )


def subscriptions_due_to_expire(today):
    return TenantSubscription.objects.filter(
        status__in=("ACTIVE", "TRIAL"),
        expires_at__isnull=False,
        expires_at__lte=today,
    ).select_related("church")


def active_subscriptions_with_plan():
    return TenantSubscription.objects.select_related("church", "plan").filter(
        status="ACTIVE"
    )


def subscription_status_count(status) -> int:
    return TenantSubscription.objects.filter(status=status).count()


def active_subscription_count() -> int:
    return TenantSubscription.objects.filter(status="ACTIVE").count()


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


def pending_application_count() -> int:
    return TenantApplication.objects.filter(status="PENDING").count()


def pending_application_for_email(email) -> bool:
    return TenantApplication.objects.filter(
        status="PENDING", contact_email=email
    ).exists()


def approved_application_for_email(email) -> bool:
    return TenantApplication.objects.filter(
        status="APPROVED", contact_email__iexact=email
    ).exists()


def approved_application_for_username(username) -> bool:
    return TenantApplication.objects.filter(
        status="APPROVED", applicant_username__iexact=username
    ).exists()


def approved_application_for_normalized_phone(normalized_phone) -> bool:
    if not normalized_phone:
        return False
    return TenantApplication.objects.filter(
        status="APPROVED", contact_phone_normalized=normalized_phone
    ).exists()


def applications_list_base():
    return TenantApplication.objects.select_related(
        "district", "reviewed_by", "created_church", "denomination"
    ).order_by("-created_at")


def application_detail_qs():
    return TenantApplication.objects.select_related(
        "district",
        "district__zone__conference",
        "reviewed_by",
        "created_church",
        "invitation",
        "denomination",
    )


def get_application_or_404(pk):
    return get_object_or_404(application_detail_qs(), pk=pk)


# ---------------------------------------------------------------------------
# Audit / announcements
# ---------------------------------------------------------------------------


def platform_audit_list_base():
    return PlatformAuditLog.objects.select_related("user", "denomination").order_by(
        "-created_at"
    )


def recent_audit_since(since):
    return PlatformAuditLog.objects.filter(created_at__gte=since)


def denomination_scoped_audit(denomination, church_id_strings, *, limit=50):
    return (
        PlatformAuditLog.objects.select_related("user")
        .filter(
            Q(denomination=denomination)
            | Q(target_model="Denomination", target_id=str(denomination.pk))
            | Q(target_model="Church", target_id__in=church_id_strings)
            | Q(
                target_model="TenantApplication",
                details__denomination_id=str(denomination.pk),
            )
        )
        .order_by("-created_at")[:limit]
    )


def active_platform_announcement_now(now=None):
    now = now or timezone.now()
    return (
        PlatformAnnouncement.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .order_by("-created_at")
        .first()
    )


def get_announcement_or_404(pk):
    return get_object_or_404(PlatformAnnouncement, pk=pk)


# ---------------------------------------------------------------------------
# Users / org counts
# ---------------------------------------------------------------------------


def username_exists_iexact(username) -> bool:
    return User.objects.filter(username__iexact=username).exists()


def email_exists_iexact(email) -> bool:
    return User.objects.filter(email__iexact=email).exists()


def church_user_count(church) -> int:
    return User.objects.filter(
        church=church, is_active=True, is_platform_user=False
    ).count()


def institution_users_for_church(church, *, limit=20):
    return User.objects.filter(church=church, is_platform_user=False).order_by(
        "username"
    )[:limit]


def active_institution_user_count() -> int:
    return User.objects.filter(is_active=True, is_platform_user=False).count()


def active_operator_count() -> int:
    return User.objects.filter(is_active=True, is_platform_user=True).count()


def conference_count() -> int:
    return Conference.objects.count()


def zone_count() -> int:
    return Zone.objects.count()


def district_count() -> int:
    return District.objects.count()


def organization_tree_conferences(limit=50):
    return Conference.objects.annotate(
        zone_count=Count("zones", distinct=True),
    ).order_by("name")[:limit]


def districts_for_public_registration():
    return District.objects.select_related("zone__conference").order_by(
        "zone__conference__name", "zone__name", "name"
    )


def districts_for_denomination(denomination):
    return District.objects.filter(
        zone__conference__denomination=denomination
    ).select_related("zone__conference").order_by(
        "zone__conference__name", "zone__name", "name"
    )


def districts_with_parents_ordered():
    return District.objects.select_related("zone__conference").order_by(
        "zone__conference__name", "zone__name", "name"
    )


def empty_districts():
    return District.objects.none()


def empty_denominations():
    return Denomination.objects.none()


def all_payment_methods():
    return PlatformPaymentMethod.objects.all()


def announcements_list_base():
    return PlatformAnnouncement.objects.select_related("created_by").order_by(
        "-created_at"
    )


def platform_operators_ordered():
    return User.objects.filter(is_platform_user=True).prefetch_related(
        "managed_denominations"
    ).order_by("username")


def active_platform_operator_by_pk(pk):
    return User.objects.filter(
        pk=pk, is_platform_user=True, is_active=True
    ).first()


def get_platform_operator_or_404(pk):
    return get_object_or_404(User, pk=pk, is_platform_user=True)


def get_institution_user_or_404(pk):
    return get_object_or_404(User, pk=pk, is_platform_user=False, is_active=True)


def get_pending_application_or_404(pk):
    return get_object_or_404(TenantApplication, pk=pk, status="PENDING")


def church_tenant_access_qs():
    return Church.objects.select_related(
        "district__zone__conference__denomination"
    )


def churches_filter_by_pk(church_id):
    return Church.objects.filter(pk=church_id)


def get_active_denomination_or_404(pk):
    return get_object_or_404(Denomination, pk=pk, is_active=True)


def zones_hierarchy_global(*, limit=100):
    return Zone.objects.select_related("conference").order_by(
        "conference__name", "name"
    )[:limit]


def districts_hierarchy_global(*, limit=100):
    return District.objects.select_related("zone__conference").order_by(
        "zone__name", "name"
    )[:limit]


def conferences_for_denominations_annotated(denoms, *, limit=50):
    return (
        Conference.objects.filter(denomination__in=denoms)
        .annotate(zone_count=Count("zones", distinct=True))
        .order_by("name")[:limit]
    )


def church_count_for_denominations(denoms) -> int:
    return Church.objects.filter(
        district__zone__conference__denomination__in=denoms
    ).count()


def zones_for_denominations(denoms, *, limit=100):
    return (
        Zone.objects.filter(conference__denomination__in=denoms)
        .select_related("conference")
        .order_by("conference__name", "name")[:limit]
    )


def districts_for_denominations(denoms, *, limit=100):
    return (
        District.objects.filter(zone__conference__denomination__in=denoms)
        .select_related("zone__conference")
        .order_by("zone__name", "name")[:limit]
    )


def districts_for_denomination_limited(denomination, *, limit=500):
    return districts_for_denomination(denomination)[:limit]


def districts_with_parents_limited(*, limit=500):
    return districts_with_parents_ordered()[:limit]
