"""Platform operator access scoping per denomination."""

from sitecontrol import selectors
from sitecontrol.rbac import ROLE_OWNER


def operator_has_global_access(user):
    """Only break-glass superusers or platform Owners see all denominations."""
    return (
        user.is_authenticated
        and getattr(user, "is_platform_user", False)
        and (user.is_superuser or getattr(user, "platform_role", "") == ROLE_OWNER)
    )


def get_operator_denominations(user):
    if not user.is_authenticated or not getattr(user, "is_platform_user", False):
        return selectors.empty_denominations()
    if operator_has_global_access(user):
        return selectors.active_denominations_ordered()
    return user.managed_denominations.filter(is_active=True).order_by("name")


def operator_can_access_denomination(user, denomination):
    if not denomination:
        return operator_has_global_access(user)
    if not user.is_authenticated or not getattr(user, "is_platform_user", False):
        return False
    if operator_has_global_access(user):
        return True
    return user.managed_denominations.filter(pk=denomination.pk).exists()


def filter_platform_denomination(qs, user, field="denomination"):
    """Filter a queryset to denominations the operator may manage."""
    if operator_has_global_access(user):
        return qs
    return qs.filter(**{f"{field}__in": user.managed_denominations.all()})


def filter_churches_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(district__zone__conference__denomination__in=user.managed_denominations.all())


def filter_audit_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    managed = user.managed_denominations.all()
    return qs.filter(denomination__in=managed)


def filter_subscriptions_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(
        church__district__zone__conference__denomination__in=user.managed_denominations.all()
    )


def filter_applications_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(denomination__in=user.managed_denominations.all())


def filter_conferences_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(denomination__in=user.managed_denominations.all())


def filter_zones_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(conference__denomination__in=user.managed_denominations.all())


def filter_districts_for_operator(qs, user):
    if operator_has_global_access(user):
        return qs
    return qs.filter(zone__conference__denomination__in=user.managed_denominations.all())


def filter_institution_users_for_operator(qs, user):
    from django.db.models import Q

    if operator_has_global_access(user):
        return qs
    denoms = user.managed_denominations.all()
    return qs.filter(
        Q(denomination__in=denoms)
        | Q(church__district__zone__conference__denomination__in=denoms)
    )
