"""
Persistence helpers for the sitecontrol / platform domain.

Services and forms own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put SaaS entitlement or approval rules here.
"""

from __future__ import annotations

from accounts.models import User
from organization.models import Church, Conference
from sitecontrol.models import (
    Denomination,
    PlatformAnnouncement,
    PlatformAuditLog,
    PlatformPaymentMethod,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)


def create_platform_audit(**fields):
    return PlatformAuditLog.objects.create(**fields)


def save_model(instance, *, update_fields=None):
    """
    Persist a model instance.

    Church rows always run full_clean() so INV-TEN-05 denomination rules cannot be
    bypassed by repository callers (CH-SEC-004).
    """
    from organization.models import Church

    if isinstance(instance, Church):
        instance.full_clean()
    if update_fields is not None:
        instance.save(update_fields=update_fields)
    else:
        instance.save()
    return instance


def bulk_create_payment_methods(methods):
    return PlatformPaymentMethod.objects.bulk_create(methods)


def create_subscription_plan(**fields):
    return SubscriptionPlan.objects.create(**fields)


def create_tenant_subscription(**fields):
    return TenantSubscription.objects.create(**fields)


def update_or_create_tenant_subscription(*, church, defaults):
    return TenantSubscription.objects.update_or_create(church=church, defaults=defaults)


def save_subscription(sub, *, update_fields=None):
    return save_model(sub, update_fields=update_fields)


def deactivate_institution_users_for_church(church):
    return User.objects.filter(
        church=church, is_platform_user=False, is_active=True
    ).update(is_active=False)


def save_church(church, *, update_fields=None):
    return save_model(church, update_fields=update_fields)


def create_tenant_application(**fields):
    return TenantApplication.objects.create(**fields)


def save_application(application, *, update_fields=None):
    return save_model(application, update_fields=update_fields)


def update_or_create_denomination(*, code, defaults):
    return Denomination.objects.update_or_create(code=code, defaults=defaults)


def assign_orphan_conferences_to_denomination(denomination):
    return Conference.objects.filter(denomination__isnull=True).update(
        denomination=denomination
    )


def update_offering_category_names(*, church, code, name):
    from transactions.models import OfferingCategory

    return OfferingCategory.objects.filter(church=church, code=code).update(name=name)
