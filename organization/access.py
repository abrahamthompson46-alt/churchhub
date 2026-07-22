"""Organization access control — denomination and subtree scoping."""

from django.core.exceptions import PermissionDenied

from church_system.denomination_scope import (
    assert_church_in_active_denomination,
    get_user_denomination,
)
from permissions.checks import user_has_role
from permissions.roles import UserRole
from permissions.superadmin import is_superadmin

from organization import selectors


def is_global_org_admin(user):
    """Union+ / denomination admins who may create conferences and transfer across wide trees."""
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    if is_superadmin(user):
        return True
    level = infer_scope_level(user)
    return level in {
        OrgScopeLevel.DENOMINATION,
        OrgScopeLevel.GENERAL_CONFERENCE,
        OrgScopeLevel.UNION,
    } or user_has_role(
        user, {UserRole.GENERAL_OVERSEER, UserRole.SUPER_ADMIN, UserRole.UNION_ADMIN}
    )


def can_manage_subtree_structure(user):
    """Conference/zone+ may create and edit zones/districts inside their scope."""
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    if is_superadmin(user):
        return True
    level = infer_scope_level(user)
    return level in {
        OrgScopeLevel.DENOMINATION,
        OrgScopeLevel.GENERAL_CONFERENCE,
        OrgScopeLevel.UNION,
        OrgScopeLevel.CONFERENCE,
        OrgScopeLevel.ZONE,
    }


def can_transfer_churches(user):
    """Church transfers require conference-level (or wider) administration."""
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    if is_superadmin(user):
        return True
    level = infer_scope_level(user)
    return level in {
        OrgScopeLevel.DENOMINATION,
        OrgScopeLevel.GENERAL_CONFERENCE,
        OrgScopeLevel.UNION,
        OrgScopeLevel.CONFERENCE,
    }


def is_district_scoped_user(user):
    """True when the user is limited to a single district subtree."""
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    if is_global_org_admin(user):
        return False
    return infer_scope_level(user) == OrgScopeLevel.DISTRICT


def user_district(user):
    if getattr(user, "scope_district_id", None):
        return user.scope_district
    if user.church_id:
        return user.church.district
    return None


def require_org_read(request):
    from permissions.checks import can_view_all_churches

    if not can_view_all_churches(request.user):
        raise PermissionDenied


def require_org_manage(request):
    from permissions.checks import can_manage_organization

    if not can_manage_organization(request.user):
        raise PermissionDenied


def org_capability_flags(user):
    """Template/view flags for consistent organization UI gating."""
    from permissions.checks import can_manage_organization

    manage = can_manage_organization(user)
    district = is_district_scoped_user(user)
    return {
        "can_manage": manage,
        "can_manage_churches": manage,
        "can_manage_structure": manage and can_manage_subtree_structure(user) and not district,
        "can_manage_union_structure": manage and is_global_org_admin(user),
        "can_transfer_churches": manage and can_transfer_churches(user),
        "is_global_admin": is_global_org_admin(user),
        "is_district_scoped": district,
    }


def scoped_conferences(request):
    return selectors.scoped_conferences(request)


def scoped_zones(request):
    return selectors.scoped_zones(request)


def scoped_districts(request):
    return selectors.scoped_districts(request)


def scoped_churches(request, active_only=False):
    return selectors.scoped_churches(request, active_only=active_only)


def scoped_unions(request):
    return selectors.scoped_unions(request)


def scoped_general_conferences(request):
    return selectors.scoped_general_conferences(request)


def get_scoped_conference(request, pk):
    return selectors.get_conference_or_404(scoped_conferences(request), pk)


def get_scoped_zone(request, pk):
    return selectors.get_zone_or_404(scoped_zones(request), pk)


def get_scoped_district(request, pk):
    return selectors.get_district_or_404(scoped_districts(request), pk)


def get_scoped_church(request, pk):
    church = selectors.get_church_or_404(scoped_churches(request), pk)
    assert_church_in_active_denomination(request, church)
    return church


def get_scoped_union(request, pk):
    return selectors.get_union_or_404(scoped_unions(request), pk)


def get_scoped_general_conference(request, pk):
    return selectors.get_general_conference_or_404(scoped_general_conferences(request), pk)


def assert_can_manage_church(request, church):
    require_org_manage(request)
    get_scoped_church(request, church.pk)
    if is_district_scoped_user(request.user):
        home_district = user_district(request.user)
        if not home_district or church.district_id != home_district.pk:
            raise PermissionDenied(
                "District administrators may only manage churches in their district."
            )


def assert_can_manage_district(request, district):
    require_org_manage(request)
    get_scoped_district(request, district.pk)
    if is_district_scoped_user(request.user):
        home_district = user_district(request.user)
        if not home_district or district.pk != home_district.pk:
            raise PermissionDenied(
                "District administrators may only manage their assigned district."
            )


def assert_global_structure_manage(request):
    """Union+ structure (GC/union/conference create) — not for district pastors."""
    require_org_manage(request)
    if not is_global_org_admin(request.user):
        raise PermissionDenied(
            "Creating conferences and unions requires union-level administration."
        )


def assert_subtree_structure_manage(request):
    """Zone/district create/edit inside conference/zone scope."""
    require_org_manage(request)
    if is_district_scoped_user(request.user):
        raise PermissionDenied(
            "District administrators cannot modify conference or zone structure."
        )
    if not can_manage_subtree_structure(request.user):
        raise PermissionDenied("You cannot modify organization structure at this level.")


def church_belongs_to_user_denomination(user, church):
    user_denom = get_user_denomination(user)
    if not user_denom or not church:
        return True
    church_denom = church.denomination
    return church_denom and church_denom.pk == user_denom.pk
