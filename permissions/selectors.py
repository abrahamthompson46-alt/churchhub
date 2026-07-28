"""
Read/query helpers for the permissions / RBAC domain.

Services, views, scoping helpers, and forms call selectors for querysets and
existence checks. Authorization rules stay in services/checks; writes stay in
repositories.
"""

from __future__ import annotations

from django.db import OperationalError, ProgrammingError
from django.shortcuts import get_object_or_404

from permissions.models import Permission, PermissionAuditLog, PermissionOverride, RolePermission


# ---------------------------------------------------------------------------
# Permission catalog / matrix reads
# ---------------------------------------------------------------------------


def permission_tables_ready() -> bool:
    try:
        Permission.objects.exists()
        return True
    except (OperationalError, ProgrammingError):
        return False


def active_permissions_qs():
    return Permission.objects.filter(is_active=True)


def active_permissions_ordered():
    return active_permissions_qs().order_by("category", "sort_order")


def permission_by_pk(pk):
    return Permission.objects.get(pk=pk)


def role_permission_for(role, codename):
    return RolePermission.objects.select_related("permission").get(
        role=role,
        permission__codename=codename,
        permission__is_active=True,
    )


def all_role_permissions():
    return RolePermission.objects.select_related("permission")


def granted_conflict_codenames(role, conflict_codenames):
    return list(
        RolePermission.objects.filter(
            role=role,
            permission__codename__in=conflict_codenames,
            granted=True,
        ).values_list("permission__codename", flat=True)
    )


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


def active_overrides_for_user_codename(user, codename):
    return PermissionOverride.objects.filter(
        user=user,
        permission__codename=codename,
        is_active=True,
    ).select_related("permission")


def overrides_for_user_ids(user_ids, *, limit=200):
    return (
        PermissionOverride.objects.filter(user_id__in=user_ids)
        .select_related("user", "permission", "created_by")
        .order_by("-created_at")[:limit]
    )


def overrides_for_user(user):
    return PermissionOverride.objects.filter(user=user).select_related("permission")


def active_override_count_for_user_ids(user_ids):
    return PermissionOverride.objects.filter(is_active=True, user_id__in=user_ids).count()


def overrides_qs_for_user_ids(user_ids):
    return PermissionOverride.objects.filter(user_id__in=user_ids)


def get_override_for_manager_or_404(user_ids, pk):
    return get_object_or_404(overrides_qs_for_user_ids(user_ids), pk=pk)


# ---------------------------------------------------------------------------
# Audit history
# ---------------------------------------------------------------------------


def audit_count_for_target_user_ids(user_ids):
    return PermissionAuditLog.objects.filter(target_user_id__in=user_ids).count()


def audit_logs_for_target_user_ids(user_ids, *, limit=300):
    return (
        PermissionAuditLog.objects.filter(target_user_id__in=user_ids)
        .select_related("performed_by", "target_user")
        .order_by("-created_at")[:limit]
    )


# ---------------------------------------------------------------------------
# Users (admin / effective-permission UI)
# ---------------------------------------------------------------------------


def get_user_or_404(pk):
    from django.contrib.auth import get_user_model

    return get_object_or_404(get_user_model(), pk=pk)


def empty_users():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.none()


def institution_users_base_qs():
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        .objects.select_related(
            "church",
            "church__district__zone__conference",
            "denomination",
            "scope_district__zone__conference",
            "scope_zone__conference",
            "scope_conference",
            "scope_union",
            "scope_general_conference",
        )
        .filter(is_platform_user=False)
        .order_by("username")
    )


def users_matching_q(qs, q_filter):
    return qs.filter(q_filter)


def user_exists_in_qs(qs, pk) -> bool:
    return qs.filter(pk=pk).exists()


# ---------------------------------------------------------------------------
# Church / organization scope reads
# ---------------------------------------------------------------------------


def empty_churches():
    from organization.models import Church

    return Church.objects.none()


def active_churches_base_qs():
    from organization.models import Church

    return (
        Church.objects.select_related("district__zone__conference__denomination")
        .filter(is_active=True)
        .order_by("name")
    )


def all_churches_base_qs():
    """All churches (including inactive) for super-admin scope."""
    from organization.models import Church

    return Church.objects.select_related(
        "district__zone__conference__denomination"
    ).order_by("name")


def churches_for_denomination(qs, denomination):
    return qs.filter(district__zone__conference__denomination=denomination)


def churches_filtered_by_q(qs, church_q):
    return qs.filter(church_q)


def church_exists_with_q(church_q, church_pk) -> bool:
    from organization.models import Church

    return Church.objects.filter(church_q, pk=church_pk).exists()


def church_ids_matching_q(church_q):
    from organization.models import Church

    return Church.objects.filter(church_q).values("pk")


def churches_by_ids(ids):
    from organization.models import Church

    return Church.objects.filter(pk__in=ids)


def subtree_id_lists(manageable_church_ids):
    """Distinct district/zone/conference/union ids inside a church subtree."""
    subtree = churches_by_ids(manageable_church_ids)
    return {
        "district_ids": subtree.values_list("district_id", flat=True).distinct(),
        "zone_ids": subtree.values_list("district__zone_id", flat=True).distinct(),
        "conference_ids": subtree.values_list(
            "district__zone__conference_id", flat=True
        ).distinct(),
        "union_ids": subtree.values_list(
            "district__zone__conference__union_id", flat=True
        ).distinct(),
    }


def districts_by_ids(ids):
    from organization.models import District

    return District.objects.filter(pk__in=ids).select_related("zone__conference").order_by("name")


def zones_by_ids(ids):
    from organization.models import Zone

    return Zone.objects.filter(pk__in=ids).select_related("conference").order_by("name")


def conferences_by_ids(ids):
    from organization.models import Conference

    return Conference.objects.filter(pk__in=ids).order_by("name")


def unions_by_ids(ids):
    from organization.models import Union

    return Union.objects.filter(pk__in=ids).order_by("name")


def general_conferences_by_ids(ids):
    from organization.models import GeneralConference

    return GeneralConference.objects.filter(pk__in=ids).order_by("name")


def denominations_by_pk(pk):
    from sitecontrol.models import Denomination

    return Denomination.objects.filter(pk=pk)


def denominations_by_ids(ids):
    from sitecontrol.models import Denomination

    return Denomination.objects.filter(pk__in=ids).order_by("name")


def first_conference_for_union(union):
    """First conference under a union (with denomination), or None."""
    if union is None:
        return None
    return union.conferences.select_related("denomination").first()
