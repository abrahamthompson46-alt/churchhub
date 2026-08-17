"""Scoped querysets for user and church administration."""

from django.db import models

from church_system.denomination_scope import get_user_denomination
from permissions import selectors
from permissions.org_scope import church_q_for_scope
from permissions.superadmin import is_superadmin


def get_manageable_churches(user):
    """Churches inside the user's organization subtree (active only, except super-admins).

    INV-TEN-02 / INV-TEN-18 / CH-SEC-L1: unanchored institution superadmins and
    break-glass superusers MUST receive an empty queryset — never all churches.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return selectors.empty_churches()

    # Institution super-admins see every church in their denomination (incl. inactive).
    if is_superadmin(user):
        user_denom = get_user_denomination(user)
        if not user_denom:
            return selectors.empty_churches()
        qs = selectors.all_churches_base_qs()
        return selectors.churches_for_denomination(qs, user_denom)

    qs = selectors.active_churches_base_qs()

    # Break-glass Django superuser: denomination-bounded only (INV-TEN-18).
    if getattr(user, "is_superuser", False) and not getattr(user, "is_platform_user", False):
        user_denom = get_user_denomination(user)
        if not user_denom:
            return selectors.empty_churches()
        return selectors.churches_for_denomination(qs, user_denom)

    return selectors.churches_filtered_by_q(qs, church_q_for_scope(user))


def get_manageable_users(user):
    """Return queryset of users this manager can administer.

    Institution managers never see platform operators. Users are visible when
    their home church (or scope node) falls inside the manager's subtree.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return selectors.empty_users()

    qs = selectors.institution_users_base_qs()

    # Institution super-admins see all non-platform users in their denomination.
    if is_superadmin(user):
        user_denom = get_user_denomination(user)
        if not user_denom:
            # CH-SEC-L1: unanchored — self only (never all institution users).
            return selectors.users_matching_q(qs, models.Q(pk=user.pk))
        church_ids = list(
            get_manageable_churches(user).values_list("pk", flat=True)
        )
        return selectors.users_matching_q(
            qs,
            models.Q(church_id__in=church_ids)
            | models.Q(denomination=user_denom)
            | models.Q(pk=user.pk),
        )

    manageable_church_ids = list(get_manageable_churches(user).values_list("pk", flat=True))
    user_denom = get_user_denomination(user)

    # Users whose home church is in subtree
    church_q = models.Q(church_id__in=manageable_church_ids)

    ids = selectors.subtree_id_lists(manageable_church_ids)

    scope_q = (
        models.Q(scope_district_id__in=ids["district_ids"])
        | models.Q(scope_zone_id__in=ids["zone_ids"])
        | models.Q(scope_conference_id__in=ids["conference_ids"])
        | models.Q(scope_union_id__in=ids["union_ids"])
    )
    if user_denom:
        scope_q |= models.Q(
            denomination=user_denom,
            church__isnull=True,
            scope_level="DENOMINATION",
        )

    return selectors.users_matching_q(qs, church_q | scope_q)


def user_may_manage_target(actor, target_user) -> bool:
    """Whether actor may edit/invite-equivalent manage target_user."""
    if not actor or not target_user:
        return False
    if getattr(target_user, "is_platform_user", False):
        return False
    return selectors.user_exists_in_qs(get_manageable_users(actor), target_user.pk)
