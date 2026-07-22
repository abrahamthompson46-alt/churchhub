"""Object-scoped permission checks — church and hierarchy aware."""

from permissions.org_scope import church_in_user_scope, church_q_for_scope
from permissions.services import user_has_permission
from permissions.superadmin import is_superadmin
from permissions.org_scope import OrgScopeLevel, infer_scope_level


def is_top_level_approver(user):
    """Denomination / GC / Union level admins may act across their full subtree."""
    if not user.is_authenticated:
        return False
    if is_superadmin(user):
        return True
    level = infer_scope_level(user)
    return level in {
        OrgScopeLevel.DENOMINATION,
        OrgScopeLevel.GENERAL_CONFERENCE,
        OrgScopeLevel.UNION,
    }


def can_act_on_church(user, church, permission_codename):
    """
    User holds the permission and may act on records for this church.
    Scope is the user's organization subtree (no sideways jumps).
    """
    if not user_has_permission(user, permission_codename):
        return False
    if not church:
        return False
    return church_in_user_scope(user, church)


def can_approve_for_church(user, church, permission_codename):
    """Alias for approval workflows (maker-checker checker step)."""
    return can_act_on_church(user, church, permission_codename)


def filter_queryset_for_church_scope(user, queryset, permission_codename, church_lookup="church"):
    """Return queryset rows the user may act on for the given permission."""
    from permissions import selectors

    if not user_has_permission(user, permission_codename):
        return queryset.none()

    church_ids = selectors.church_ids_matching_q(church_q_for_scope(user))
    return queryset.filter(**{f"{church_lookup}_id__in": church_ids})


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
