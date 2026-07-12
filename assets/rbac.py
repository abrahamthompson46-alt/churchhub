"""Fixed asset access control and hierarchy scoping."""

from django.core.exceptions import PermissionDenied

from organization.models import Conference, District, Zone
from permissions.checks import (
    can_approve_assets,
    can_manage_asset_policy,
    can_manage_assets,
    can_view_all_churches,
)
from permissions.scoping import get_manageable_churches


def user_may_view_assets(user):
    """Read access to the asset register (dashboard, detail, export)."""
    return (
        can_manage_assets(user)
        or can_approve_assets(user)
        or can_manage_asset_policy(user)
    )


def assert_segregation_of_duties(asset, user):
    """Preparer/submitter cannot approve their own asset."""
    if asset.submitted_by_id and asset.submitted_by_id == user.pk:
        raise PermissionDenied(
            "Segregation of duties: you cannot approve an asset you submitted."
        )
    if asset.created_by_id and asset.created_by_id == user.pk:
        raise PermissionDenied(
            "Segregation of duties: you cannot approve an asset you created."
        )


def churches_in_asset_scope(
    user,
    *,
    conference_id=None,
    zone_id=None,
    district_id=None,
    church_id=None,
):
    """
    Churches visible for asset roll-up and reports.

    Always intersects with get_manageable_churches(user). Out-of-scope filter IDs
    yield an empty queryset.
    """
    manageable = get_manageable_churches(user)
    qs = manageable

    if church_id:
        qs = qs.filter(pk=church_id)
    elif district_id:
        qs = qs.filter(district_id=district_id)
    elif zone_id:
        qs = qs.filter(district__zone_id=zone_id)
    elif conference_id:
        qs = qs.filter(district__zone__conference_id=conference_id)

    if church_id and not qs.exists():
        return manageable.none()
    if district_id and not manageable.filter(district_id=district_id).exists():
        return manageable.none()
    if zone_id and not manageable.filter(district__zone_id=zone_id).exists():
        return manageable.none()
    if conference_id and not manageable.filter(
        district__zone__conference_id=conference_id
    ).exists():
        return manageable.none()

    return qs


def get_hierarchy_context(user):
    """Dropdown options for hierarchy filters (manageable churches only)."""
    manageable = get_manageable_churches(user)
    ctx = {
        "conferences": Conference.objects.none(),
        "zones": Zone.objects.none(),
        "districts": District.objects.none(),
        "churches": manageable.none(),
        "can_filter_hierarchy": False,
    }
    if not can_view_all_churches(user):
        ctx["churches"] = manageable.select_related("district").order_by("name")
        return ctx

    conf_ids = manageable.values_list(
        "district__zone__conference_id", flat=True
    ).distinct()
    zone_ids = manageable.values_list("district__zone_id", flat=True).distinct()
    dist_ids = manageable.values_list("district_id", flat=True).distinct()
    ctx["can_filter_hierarchy"] = True
    ctx["conferences"] = Conference.objects.filter(pk__in=conf_ids).order_by("name")
    ctx["zones"] = Zone.objects.filter(pk__in=zone_ids).select_related(
        "conference"
    ).order_by("name")
    ctx["districts"] = District.objects.filter(pk__in=dist_ids).select_related(
        "zone"
    ).order_by("name")
    ctx["churches"] = manageable.select_related("district").order_by("name")
    return ctx
