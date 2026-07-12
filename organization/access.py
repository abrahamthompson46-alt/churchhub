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
    return is_superadmin(user) or user_has_role(user, {UserRole.GENERAL_OVERSEER})


def is_district_scoped_user(user):
    return user_has_role(user, {UserRole.DISTRICT_PASTOR}) and not is_global_org_admin(user)


def user_district(user):
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
    denomination = get_active_denomination(request)
    qs = conferences_for_denomination(denomination) if denomination else Conference.objects.all()
    if is_district_scoped_user(request.user) and request.user.church_id:
        qs = qs.filter(pk=request.user.church.district.zone.conference_id)
    return qs


def scoped_zones(request):
    qs = Zone.objects.filter(conference__in=scoped_conferences(request))
    if is_district_scoped_user(request.user) and request.user.church_id:
        qs = qs.filter(pk=request.user.church.district.zone_id)
    return qs


def scoped_districts(request):
    qs = District.objects.filter(zone__in=scoped_zones(request))
    if is_district_scoped_user(request.user) and request.user.church_id:
        qs = qs.filter(pk=request.user.church.district_id)
    return qs


def scoped_churches(request, active_only=False):
    denomination = get_active_denomination(request)
    if denomination:
        qs = churches_for_denomination(denomination)
    else:
        qs = Church.objects.all()
    if is_district_scoped_user(request.user) and request.user.church_id:
        qs = qs.filter(district_id=request.user.church.district_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


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
        if church.district_id != request.user.church.district_id:
            raise PermissionDenied("District pastors may only manage churches in their district.")


def assert_can_manage_district(request, district):
    require_org_manage(request)
    get_scoped_district(request, district.pk)
    if is_district_scoped_user(request.user):
        if district.pk != request.user.church.district_id:
            raise PermissionDenied("District pastors may only manage their assigned district.")


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
