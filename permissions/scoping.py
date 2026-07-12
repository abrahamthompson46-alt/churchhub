"""Scoped querysets for user and church administration."""

from django.db import models

from church_system.denomination_scope import get_user_denomination
from permissions.checks import user_has_role
from permissions.roles import UserRole
from permissions.superadmin import is_superadmin


def _denomination_church_filter(user_denom):
    if not user_denom:
        return models.Q()
    return models.Q(district__zone__conference__denomination=user_denom)


def get_manageable_churches(user):
    """Churches this user may assign when inviting or editing users."""
    from organization.models import Church

    user_denom = get_user_denomination(user)
    denom_filter = _denomination_church_filter(user_denom)
    qs = Church.objects.select_related("district__zone__conference__denomination").filter(
        is_active=True
    ).order_by("name")
    if user_denom:
        qs = qs.filter(denom_filter)

    if is_superadmin(user) or user_has_role(user, {UserRole.GENERAL_OVERSEER}):
        return qs
    if user_has_role(user, {UserRole.DISTRICT_PASTOR}) and user.church_id:
        return qs.filter(district_id=user.church.district_id)
    if user.church_id:
        return qs.filter(pk=user.church_id)
    return Church.objects.none()


def get_manageable_users(user):
    """Return queryset of users this manager can administer.

    Institution managers never see platform operators. Superuser / break-glass
    may still view institution users (platform users remain excluded unless
    the caller is a platform operator browsing via other tools).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user_denom = get_user_denomination(user)
    qs = User.objects.select_related("church", "denomination").filter(
        is_platform_user=False,
    ).order_by("username")
    if user_denom:
        qs = qs.filter(
            models.Q(church__district__zone__conference__denomination=user_denom)
            | models.Q(denomination=user_denom, church__isnull=True)
        )
    if is_superadmin(user) or user_has_role(user, {UserRole.GENERAL_OVERSEER}):
        return qs
    if user_has_role(user, {UserRole.DISTRICT_PASTOR}) and user.church_id:
        return qs.filter(church__district_id=user.church.district_id)
    if user.church_id:
        return qs.filter(church_id=user.church_id)
    return qs.none()
