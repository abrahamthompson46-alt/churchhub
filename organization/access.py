"""Organization access control — denomination and district scoping."""

from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404

from church_system.denomination_scope import (
    assert_church_in_active_denomination,
    churches_for_denomination,
    conferences_for_denomination,
    get_active_denomination,
    get_user_denomination,
)
from permissions.checks import user_has_role
from permissions.roles import UserRole
from permissions.superadmin import is_superadmin

from organization.models import Church, Conference, District, GeneralConference, Union, Zone


def is_global_org_admin(user):
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


def _denomination_filter_path(prefix=""):
    if prefix:
        return f"{prefix}__district__zone__conference__denomination"
    return "district__zone__conference__denomination"


def scoped_conferences(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    denomination = get_active_denomination(request)
    qs = conferences_for_denomination(denomination) if denomination else Conference.objects.all()
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.CONFERENCE:
        conf_id = request.user.scope_conference_id or (
            request.user.church.district.zone.conference_id if request.user.church_id else None
        )
        if conf_id:
            qs = qs.filter(pk=conf_id)
    elif level in {OrgScopeLevel.ZONE, OrgScopeLevel.DISTRICT, OrgScopeLevel.CHURCH}:
        ids = get_manageable_churches(request.user).values_list(
            "district__zone__conference_id", flat=True
        )
        qs = qs.filter(pk__in=ids)
    elif level == OrgScopeLevel.UNION and request.user.scope_union_id:
        qs = qs.filter(union_id=request.user.scope_union_id)
    return qs


def scoped_zones(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    qs = Zone.objects.filter(conference__in=scoped_conferences(request))
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.ZONE:
        zone_id = request.user.scope_zone_id or (
            request.user.church.district.zone_id if request.user.church_id else None
        )
        if zone_id:
            qs = qs.filter(pk=zone_id)
    elif level in {OrgScopeLevel.DISTRICT, OrgScopeLevel.CHURCH}:
        ids = get_manageable_churches(request.user).values_list("district__zone_id", flat=True)
        qs = qs.filter(pk__in=ids)
    return qs


def scoped_districts(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    qs = District.objects.filter(zone__in=scoped_zones(request))
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.DISTRICT:
        district = user_district(request.user)
        if district:
            qs = qs.filter(pk=district.pk)
    elif level == OrgScopeLevel.CHURCH:
        ids = get_manageable_churches(request.user).values_list("district_id", flat=True)
        qs = qs.filter(pk__in=ids)
    return qs


def scoped_churches(request, active_only=False):
    from permissions.scoping import get_manageable_churches

    qs = get_manageable_churches(request.user)
    if not active_only:
        # Include inactive churches still in subtree for org admin views
        from permissions.org_scope import church_q_for_scope
        from organization.models import Church as ChurchModel

        qs = ChurchModel.objects.filter(church_q_for_scope(request.user)).select_related(
            "district__zone__conference__denomination"
        )
    return qs.order_by("name")


def scoped_unions(request):
    return Union.objects.filter(conferences__in=scoped_conferences(request)).distinct()


def scoped_general_conferences(request):
    return GeneralConference.objects.filter(unions__in=scoped_unions(request)).distinct()


def get_scoped_conference(request, pk):
    return get_object_or_404(scoped_conferences(request), pk=pk)


def get_scoped_zone(request, pk):
    return get_object_or_404(
        scoped_zones(request).select_related("conference"),
        pk=pk,
    )


def get_scoped_district(request, pk):
    return get_object_or_404(
        scoped_districts(request).select_related("zone__conference"),
        pk=pk,
    )


def get_scoped_church(request, pk):
    church = get_object_or_404(
        scoped_churches(request).select_related(
            "district__zone__conference__union__general_conference"
        ),
        pk=pk,
    )
    assert_church_in_active_denomination(request, church)
    return church


def get_scoped_union(request, pk):
    return get_object_or_404(
        scoped_unions(request).select_related("general_conference"),
        pk=pk,
    )


def get_scoped_general_conference(request, pk):
    return get_object_or_404(scoped_general_conferences(request), pk=pk)


def assert_can_manage_church(request, church):
    require_org_manage(request)
    get_scoped_church(request, church.pk)
    if is_district_scoped_user(request.user):
        home_district = user_district(request.user)
        if not home_district or church.district_id != home_district.pk:
            raise PermissionDenied("District administrators may only manage churches in their district.")


def assert_can_manage_district(request, district):
    require_org_manage(request)
    get_scoped_district(request, district.pk)
    if is_district_scoped_user(request.user):
        home_district = user_district(request.user)
        if not home_district or district.pk != home_district.pk:
            raise PermissionDenied("District administrators may only manage their assigned district.")


def assert_global_structure_manage(request):
    """Creating conferences/zones outside district scope requires global admin."""
    require_org_manage(request)
    if is_district_scoped_user(request.user):
        raise PermissionDenied("District pastors cannot modify conference or zone structure.")


def church_belongs_to_user_denomination(user, church):
    user_denom = get_user_denomination(user)
    if not user_denom or not church:
        return True
    church_denom = church.denomination
    return church_denom and church_denom.pk == user_denom.pk
