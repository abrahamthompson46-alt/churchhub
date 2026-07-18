"""User Control Center — shared navigation context for accounts + permissions."""

from permissions.checks import (
    can_invite_users,
    can_manage_overrides,
    can_manage_permissions,
    can_manage_users,
    can_view_activity_logs,
    can_view_permission_audit,
)


def user_control_center_tabs(user, active="directory"):
    """
    Return tab descriptors for the User Control Center shell.
    Only includes tabs the current user may open.
    """
    from sitecontrol.registration_services import institution_invites_allowed

    tabs = []
    if can_manage_users(user):
        tabs.append({
            "key": "directory",
            "label": "Directory",
            "icon": "bi-people",
            "url_name": "accounts:user_list",
        })
    if can_invite_users(user) and institution_invites_allowed():
        tabs.append({
            "key": "invite",
            "label": "Invite",
            "icon": "bi-envelope-plus",
            "url_name": "accounts:invite_user",
        })
    if can_view_activity_logs(user):
        tabs.append({
            "key": "activity",
            "label": "Activity",
            "icon": "bi-journal-text",
            "url_name": "accounts:activity_log",
        })
    if can_manage_permissions(user):
        tabs.append({
            "key": "access",
            "label": "Access overview",
            "icon": "bi-shield-lock",
            "url_name": "permissions:index",
        })
        tabs.append({
            "key": "matrix",
            "label": "Role matrix",
            "icon": "bi-grid-3x3-gap",
            "url_name": "permissions:matrix",
        })
        tabs.append({
            "key": "roles",
            "label": "Roles",
            "icon": "bi-person-badge",
            "url_name": "permissions:role_list",
        })
    if can_manage_overrides(user):
        tabs.append({
            "key": "overrides",
            "label": "Overrides",
            "icon": "bi-sliders",
            "url_name": "permissions:override_list",
        })
    if can_view_permission_audit(user):
        tabs.append({
            "key": "audit",
            "label": "Audit",
            "icon": "bi-journal-check",
            "url_name": "permissions:audit_log",
        })

    for tab in tabs:
        tab["active"] = tab["key"] == active
    return tabs


def ucc_context(user, active="directory", **extra):
    return {
        "ucc_tabs": user_control_center_tabs(user, active=active),
        "ucc_active": active,
        **extra,
    }
