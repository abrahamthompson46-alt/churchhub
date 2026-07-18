"""Church-scoping utilities for multi-tenant data isolation."""

from django.core.exceptions import PermissionDenied

from permissions.checks import can_view_all_churches
from permissions.scoping import get_manageable_churches
from organization.models import Church
from church_system.denomination_scope import assert_church_in_active_denomination


def get_user_church(user):
    """Return the church assigned to the user, or None."""
    if not user.is_authenticated:
        return None
    return getattr(user, "church", None)


def _church_from_id(church_id, manageable):
    if not church_id:
        return None
    return manageable.filter(pk=church_id).first()


def get_active_church(request):
    """
    Resolve the church context for the current request.
    Hierarchy users may switch via session within their manageable churches.
    """
    if not request.user.is_authenticated:
        return None

    manageable = get_manageable_churches(request.user)
    church_id = request.GET.get("church")
    if not church_id:
        session = getattr(request, "session", None)
        if session is not None:
            church_id = session.get("current_church_id")

    if church_id:
        church = _church_from_id(church_id, manageable)
        if church:
            assert_church_in_active_denomination(request, church)
            return church
        # Invalid or out-of-scope church ids must not fall through to an unscoped lookup.
        # (Previously DISTRICT_PASTOR / view_all_churches could open any church via ?church=.)
        return None

    user_church = get_user_church(request.user)
    if user_church:
        return user_church

    if manageable.count() == 1:
        return manageable.first()

    return None


def filter_by_church(queryset, request, field="church"):
    """Filter a queryset to the user's active church scope."""
    church = get_active_church(request)
    if church:
        return queryset.filter(**{field: church})
    if can_view_all_churches(request.user):
        manageable_ids = get_manageable_churches(request.user).values_list("pk", flat=True)
        if not manageable_ids.exists():
            return queryset.none()
        return queryset.filter(**{f"{field}__in": manageable_ids})
    return queryset.none()


def require_church(request):
    """Return active church or raise PermissionDenied."""
    church = get_active_church(request)
    if not church:
        raise PermissionDenied(
            "No church context is available. Select a church or contact your administrator."
        )
    return church


def get_available_churches(user):
    """Churches the user may switch to in the toolbar."""
    if not user.is_authenticated:
        return Church.objects.none()
    qs = get_manageable_churches(user).select_related(
        "district__zone__conference__denomination"
    ).order_by("name")
    user_denom = None
    from church_system.denomination_scope import get_user_denomination

    user_denom = get_user_denomination(user)
    if user_denom:
        qs = qs.filter(district__zone__conference__denomination=user_denom)
    return qs
