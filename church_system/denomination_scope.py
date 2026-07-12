"""Denomination-level data isolation for multi-tenant SaaS."""

from django.core.exceptions import PermissionDenied

from organization.models import Church, Conference


def get_church_denomination(church):
    if not church:
        return None
    conference = church.conference
    if not conference:
        return None
    return conference.denomination


def get_user_denomination(user):
    """Resolve the denomination boundary for an institution user."""
    if not user.is_authenticated or getattr(user, "is_platform_user", False):
        return None
    if user.church_id:
        return get_church_denomination(user.church)
    if getattr(user, "denomination_id", None):
        return user.denomination
    return None


def get_active_denomination(request):
    """
    Active denomination for the request.
    Institution users: derived from church / user assignment.
    Platform users: optional session filter for control room.
    Public: ?denomination=code or session from /apply/.
    """
    if not hasattr(request, "user"):
        return None

    session = getattr(request, "session", None)
    session_key = "active_denomination_id"

    if request.user.is_authenticated:
        if getattr(request.user, "is_platform_user", False):
            denom_id = request.GET.get("denomination_id") or (session.get(session_key) if session else None)
            if denom_id:
                from sitecontrol.models import Denomination
                from sitecontrol.platform_access import operator_can_access_denomination

                denom = Denomination.objects.filter(pk=denom_id, is_active=True).first()
                if denom and operator_can_access_denomination(request.user, denom):
                    return denom
                if session is not None and session_key in session:
                    del session[session_key]
            return None

        user_denom = get_user_denomination(request.user)
        if user_denom:
            if session is not None:
                session[session_key] = str(user_denom.pk)
            return user_denom

    code = request.GET.get("denomination")
    if code:
        from sitecontrol.models import Denomination

        return Denomination.objects.filter(code=code, is_active=True).first()

    if session and session.get(session_key):
        from sitecontrol.models import Denomination

        return Denomination.objects.filter(pk=session[session_key], is_active=True).first()

    from sitecontrol.models import Denomination

    return Denomination.get_default()


def churches_for_denomination(denomination):
    if not denomination:
        return Church.objects.none()
    return Church.objects.filter(district__zone__conference__denomination=denomination)


def conferences_for_denomination(denomination):
    if not denomination:
        return Conference.objects.none()
    return Conference.objects.filter(denomination=denomination)


def filter_by_denomination(queryset, request, path="district__zone__conference__denomination"):
    """Restrict queryset to the active denomination boundary."""
    denomination = get_active_denomination(request)
    if denomination:
        return queryset.filter(**{path: denomination})
    if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
        return queryset
    return queryset.none()


def require_denomination(request):
    denomination = get_active_denomination(request)
    if not denomination:
        raise PermissionDenied("No denomination context is available.")
    return denomination


def assert_same_denomination(user, church):
    """Raise PermissionDenied if church is outside the user's denomination."""
    if not church or getattr(user, "is_platform_user", False) or user.is_superuser:
        return
    user_denom = get_user_denomination(user)
    church_denom = get_church_denomination(church)
    if user_denom and church_denom and user_denom.pk != church_denom.pk:
        raise PermissionDenied("Cross-denomination access is not permitted.")


def assert_church_in_active_denomination(request, church):
    if not church:
        raise PermissionDenied("Church not found.")
    if getattr(request.user, "is_platform_user", False):
        active = get_active_denomination(request)
        if active:
            church_denom = get_church_denomination(church)
            if church_denom and church_denom.pk != active.pk:
                raise PermissionDenied("This church belongs to another denomination.")
        return
    assert_same_denomination(request.user, church)
