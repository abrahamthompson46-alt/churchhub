"""
Persistence helpers for the permissions / RBAC domain.

Services and views own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or resolution rules here.
"""

from __future__ import annotations

from permissions.models import Permission, PermissionAuditLog, PermissionOverride, RolePermission


def update_or_create_permission(*, codename, defaults):
    return Permission.objects.update_or_create(codename=codename, defaults=defaults)


def get_or_create_role_permission(*, role, permission, defaults):
    return RolePermission.objects.get_or_create(
        role=role,
        permission=permission,
        defaults=defaults,
    )


def update_role_permissions_granted(*, role, permission, granted):
    return RolePermission.objects.filter(role=role, permission=permission).update(
        granted=granted
    )


def get_or_create_role_permission_by_ids(*, role, permission_id, defaults):
    return RolePermission.objects.get_or_create(
        role=role,
        permission_id=permission_id,
        defaults=defaults,
    )


def save_role_permission(role_permission, *, update_fields=None):
    if update_fields is not None:
        role_permission.save(update_fields=update_fields)
    else:
        role_permission.save()
    return role_permission


def create_permission_audit(
    *,
    action,
    performed_by=None,
    target_user=None,
    ip_address=None,
    details=None,
):
    return PermissionAuditLog.objects.create(
        action=action,
        performed_by=performed_by,
        target_user=target_user,
        ip_address=ip_address,
        details=details or {},
    )


def create_override(**fields):
    return PermissionOverride.objects.create(**fields)


def save_override(override, *, update_fields=None):
    if update_fields is not None:
        override.save(update_fields=update_fields)
    else:
        override.save()
    return override


def delete_override(override):
    override.delete()
