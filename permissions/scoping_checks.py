"""Object-scoped permission checks — church and hierarchy aware."""

from django.db.models import Q

from permissions.roles import UserRole
from permissions.services import user_has_permission
from permissions.superadmin import is_superadmin


def is_top_level_approver(user):
    if not user.is_authenticated:
        return False
    if is_superadmin(user):
        return True
    return user.role == UserRole.GENERAL_OVERSEER


def can_act_on_church(user, church, permission_codename):
    """
    User holds the permission and may act on records for this church.
    Local pastors: same church. District pastors: same district. Overseers: all.
    """
    if not user_has_permission(user, permission_codename):
        return False
    if is_top_level_approver(user):
        return True
    if not church:
        return False
    from church_system.church_scope import get_user_church

    user_church = get_user_church(user)
    if not user_church:
        return False
    if user.role == UserRole.LOCAL_PASTOR:
        return church.pk == user_church.pk
    if user.role == UserRole.DISTRICT_PASTOR:
        return church.district_id == user_church.district_id
    return False


def can_approve_for_church(user, church, permission_codename):
    """Alias for approval workflows (maker-checker checker step)."""
    return can_act_on_church(user, church, permission_codename)


def filter_queryset_for_church_scope(user, queryset, permission_codename, church_lookup="church"):
    """Return queryset rows the user may act on for the given permission."""
    if not user_has_permission(user, permission_codename):
        return queryset.none()
    if is_top_level_approver(user):
        return queryset
    from church_system.church_scope import get_user_church

    user_church = get_user_church(user)
    if not user_church:
        return queryset.none()
    if user.role == UserRole.LOCAL_PASTOR:
        return queryset.filter(**{f"{church_lookup}_id": user_church.pk})
    if user.role == UserRole.DISTRICT_PASTOR:
        return queryset.filter(**{f"{church_lookup}__district_id": user_church.district_id})
    return queryset.none()


def exclude_self_submitted(user, queryset, submitter_field="minutes_submitted_by"):
    """Maker-checker: approver cannot review own submission."""
    if not user.is_authenticated:
        return queryset.none()
    return queryset.exclude(**{f"{submitter_field}_id": user.pk})


def pending_for_church_scope(user, queryset, permission_codename, church_lookup="church", submitter_field=None):
    """Scoped pending queue with optional self-submission exclusion."""
    qs = filter_queryset_for_church_scope(user, queryset, permission_codename, church_lookup=church_lookup)
    if submitter_field:
        qs = exclude_self_submitted(user, qs, submitter_field=submitter_field)
    return qs
