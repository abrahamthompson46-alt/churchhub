"""Permission matrix seeding, resolution, and audit services."""

import threading

from django.contrib.auth.models import Group
from django.db import OperationalError, ProgrammingError, transaction
from django.utils import timezone

from permissions.models import Permission, PermissionAuditLog, PermissionOverride, RolePermission
from permissions.registry import PERMISSION_REGISTRY, registry_conflicts, registry_default_roles, registry_implies
from permissions.roles import UserRole
from permissions.superadmin import is_superadmin

_request_local = threading.local()


def bind_request_permission_cache(request):
    """Attach per-request permission cache (called by middleware)."""
    _request_local.request = request
    _request_local.cache = {}


def clear_request_permission_cache():
    _request_local.request = None
    _request_local.cache = None


def _get_request_cache():
    return getattr(_request_local, "cache", None)


def _tables_ready():
    try:
        Permission.objects.exists()
        return True
    except (OperationalError, ProgrammingError):
        return False


def ensure_permission_matrix(force_defaults=False):
    """
    Sync Permission rows and RolePermission matrix from the registry.
    Safe to call on app startup; no-ops if tables are missing.
    """
    if not _tables_ready():
        return

    sort = 0
    for codename, meta in PERMISSION_REGISTRY.items():
        sort += 1
        perm, _ = Permission.objects.update_or_create(
            codename=codename,
            defaults={
                "name": meta["name"],
                "category": meta["category"],
                "description": meta.get("description", ""),
                "sort_order": sort,
                "is_active": True,
            },
        )
        for role, _label in UserRole.CHOICES:
            granted = role in meta.get("default_roles", set())
            RolePermission.objects.get_or_create(
                role=role,
                permission=perm,
                defaults={"granted": granted},
            )
            if force_defaults:
                RolePermission.objects.filter(role=role, permission=perm).update(granted=granted)


def reset_matrix_to_defaults(performed_by=None, ip_address=None):
    """Reset all matrix cells to registry defaults."""
    ensure_permission_matrix(force_defaults=True)
    log_permission_audit(
        "MATRIX_RESET",
        performed_by=performed_by,
        ip_address=ip_address,
        details={"message": "Role-permission matrix reset to defaults"},
    )


def log_permission_audit(action, performed_by=None, target_user=None, ip_address=None, details=None):
    return PermissionAuditLog.objects.create(
        action=action,
        performed_by=performed_by,
        target_user=target_user,
        ip_address=ip_address,
        details=details or {},
    )


def get_active_override(user, codename):
    """Return effective override for user+permission, or None."""
    if not user.is_authenticated:
        return None
    qs = PermissionOverride.objects.filter(
        user=user,
        permission__codename=codename,
        is_active=True,
    ).select_related("permission")
    for override in qs:
        if override.is_expired:
            continue
        return override
    return None


def _direct_matrix_grant(user, codename):
    if not _tables_ready():
        return registry_default_roles(codename) and user.role in registry_default_roles(codename)
    try:
        rp = RolePermission.objects.select_related("permission").get(
            role=user.role,
            permission__codename=codename,
            permission__is_active=True,
        )
        return rp.granted
    except RolePermission.DoesNotExist:
        return user.role in registry_default_roles(codename)


def _resolve_permission(user, codename, _stack=None):
    """Internal resolution without request cache."""
    if not user.is_authenticated:
        return False
    if is_superadmin(user):
        return True

    _stack = _stack or set()
    if codename in _stack:
        return False
    _stack.add(codename)

    override = get_active_override(user, codename)
    if override is not None:
        return override.granted

    if _direct_matrix_grant(user, codename):
        return True

    for other_codename, meta in PERMISSION_REGISTRY.items():
        implied = meta.get("implies", [])
        if codename in implied and _resolve_permission(user, other_codename, _stack):
            return True

    return False


def user_has_permission(user, codename):
    """
    Resolve permission: superuser → override → matrix → implied grants.
    Uses per-request cache when middleware is active.
    """
    cache = _get_request_cache()
    if cache is not None and user.is_authenticated:
        cache_key = (user.pk, codename)
        if cache_key in cache:
            return cache[cache_key]
        result = _resolve_permission(user, codename)
        cache[cache_key] = result
        return result
    return _resolve_permission(user, codename)


def get_effective_permissions(user):
    """Return dict codename → bool for all active permissions."""
    if not _tables_ready():
        return {codename: user_has_permission(user, codename) for codename in PERMISSION_REGISTRY}
    perms = Permission.objects.filter(is_active=True).order_by("category", "sort_order")
    return {p.codename: user_has_permission(user, p.codename) for p in perms}


def get_matrix_data():
    """Build role × permission matrix for templates."""
    if not _tables_ready():
        ensure_permission_matrix()
    permissions = list(Permission.objects.filter(is_active=True).order_by("category", "sort_order"))
    roles = UserRole.CHOICES
    cells = {}
    for rp in RolePermission.objects.select_related("permission"):
        cells[(rp.role, rp.permission_id)] = rp.granted
    categories = {}
    for perm in permissions:
        categories.setdefault(perm.category, []).append(perm)
    registry_meta = {
        p.codename: {
            "implies": registry_implies(p.codename),
            "conflicts_with": registry_conflicts(p.codename),
        }
        for p in permissions
    }
    return {
        "permissions": permissions,
        "roles": roles,
        "cells": cells,
        "categories": categories,
        "registry_meta": registry_meta,
    }


def _validate_no_conflicts(role, permission, granting):
    if not granting:
        return
    conflicts = registry_conflicts(permission.codename)
    if not conflicts:
        return
    conflict_names = list(
        RolePermission.objects.filter(
            role=role,
            permission__codename__in=conflicts,
            granted=True,
        ).values_list("permission__codename", flat=True)
    )
    if conflict_names:
        raise ValueError(
            f"Cannot grant {permission.codename} to {role}: conflicts with {', '.join(conflict_names)}."
        )


@transaction.atomic
def update_matrix_cell(role, permission_id, granted, updated_by=None, ip_address=None):
    permission = Permission.objects.get(pk=permission_id)
    _validate_no_conflicts(role, permission, granted)
    rp, _ = RolePermission.objects.get_or_create(
        role=role,
        permission_id=permission_id,
        defaults={"granted": granted},
    )
    if rp.granted != granted:
        rp.granted = granted
        rp.updated_by = updated_by
        rp.save(update_fields=["granted", "updated_by", "updated_at"])
        log_permission_audit(
            "MATRIX_UPDATE",
            performed_by=updated_by,
            ip_address=ip_address,
            details={
                "role": role,
                "permission_id": str(permission_id),
                "granted": granted,
            },
        )


@transaction.atomic
def bulk_update_matrix(updates, updated_by=None, ip_address=None):
    """updates: list of (role, permission_id, granted) tuples."""
    for role, permission_id, granted in updates:
        update_matrix_cell(role, permission_id, granted, updated_by=updated_by, ip_address=ip_address)


def create_override(user, permission, granted, reason="", expires_at=None, created_by=None, ip_address=None):
    override = PermissionOverride.objects.create(
        user=user,
        permission=permission,
        granted=granted,
        reason=reason,
        expires_at=expires_at,
        created_by=created_by,
    )
    log_permission_audit(
        "OVERRIDE_CREATE",
        performed_by=created_by,
        target_user=user,
        ip_address=ip_address,
        details={
            "permission": permission.codename,
            "granted": granted,
            "override_id": str(override.id),
        },
    )
    return override


def sync_role_groups(user):
    """
    Retired: Django auth groups are not used for ChurchHub authorization.
    Authorization is resolved via permissions.registry + RolePermission matrix.
    Kept as a no-op for backward compatibility with existing signal handlers.
    """
    return None


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
