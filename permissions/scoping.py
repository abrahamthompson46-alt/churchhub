"""Scoped querysets for user and church administration."""

from django.db import models

from church_system.denomination_scope import get_user_denomination
from permissions.org_scope import church_q_for_scope, infer_scope_level
from permissions.roles import UserRole
from permissions.superadmin import is_superadmin


def get_manageable_churches(user):
    """Churches inside the user's organization subtree (active only)."""
    from organization.models import Church

    if not user or not getattr(user, "is_authenticated", False):
        return Church.objects.none()

    qs = Church.objects.select_related(
        "district__zone__conference__denomination"
    ).filter(is_active=True).order_by("name")

    # Break-glass Django superuser sees all (still filtered later by denomination UI).
    if getattr(user, "is_superuser", False) and not getattr(user, "is_platform_user", False):
        user_denom = get_user_denomination(user)
        if user_denom:
            return qs.filter(district__zone__conference__denomination=user_denom)
        return qs

    return qs.filter(church_q_for_scope(user))


def get_manageable_users(user):
    """Return queryset of users this manager can administer.

    Institution managers never see platform operators. Users are visible when
    their home church (or scope node) falls inside the manager's subtree.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if not user or not getattr(user, "is_authenticated", False):
        return User.objects.none()

    qs = User.objects.select_related(
        "church",
        "church__district__zone__conference",
        "denomination",
        "scope_district__zone__conference",
        "scope_zone__conference",
        "scope_conference",
        "scope_union",
        "scope_general_conference",
    ).filter(is_platform_user=False).order_by("username")

    # Institution super-admins see all non-platform users (optionally
    # denomination-bounded when the actor has a denomination).
    if is_superadmin(user):
        user_denom = get_user_denomination(user)
        if user_denom:
            church_ids = list(
                get_manageable_churches(user).values_list("pk", flat=True)
            )
            return qs.filter(
                models.Q(church_id__in=church_ids)
                | models.Q(denomination=user_denom)
                | models.Q(pk=user.pk)
            )
        return qs

    manageable_church_ids = list(get_manageable_churches(user).values_list("pk", flat=True))
    user_denom = get_user_denomination(user)

    # Users whose home church is in subtree
    church_q = models.Q(church_id__in=manageable_church_ids)

    # Hierarchy admins without home church: match overlapping scope FKs in subtree
    from organization.models import Church

    subtree = Church.objects.filter(pk__in=manageable_church_ids)
    district_ids = subtree.values_list("district_id", flat=True).distinct()
    zone_ids = subtree.values_list("district__zone_id", flat=True).distinct()
    conference_ids = subtree.values_list("district__zone__conference_id", flat=True).distinct()
    union_ids = subtree.values_list(
        "district__zone__conference__union_id", flat=True
    ).distinct()

    scope_q = (
        models.Q(scope_district_id__in=district_ids)
        | models.Q(scope_zone_id__in=zone_ids)
        | models.Q(scope_conference_id__in=conference_ids)
        | models.Q(scope_union_id__in=union_ids)
    )
    if user_denom:
        scope_q |= models.Q(
            denomination=user_denom,
            church__isnull=True,
            scope_level="DENOMINATION",
        )

    return qs.filter(church_q | scope_q)


def user_may_manage_target(actor, target_user) -> bool:
    """Whether actor may edit/invite-equivalent manage target_user."""
    if not actor or not target_user:
        return False
    if getattr(target_user, "is_platform_user", False):
        return False
    return get_manageable_users(actor).filter(pk=target_user.pk).exists()
