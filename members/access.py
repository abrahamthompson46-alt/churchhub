"""Member-module permission helpers — granular can_* gates for views.

Each check uses the permission matrix (including manage_members implies and
deny overrides). Do not OR with can_manage_members here — that would ignore
deny overrides on the granular codename.
"""

from django.core.exceptions import PermissionDenied

from permissions.checks import (
    can_add_members,
    can_edit_members,
    can_export_members,
    can_manage_baptisms,
    can_manage_departments,
    can_manage_families,
    can_manage_leadership,
    can_manage_member_configuration,
    can_manage_member_lookups,
    can_manage_member_records,
    can_manage_members,
    can_manage_occupations,
    can_manage_spiritual_gifts,
    can_process_transfers,
    can_transfer_members,
    can_view_member_records,
    can_view_members,
)


def require_any(request, *checkers):
    if not any(fn(request.user) for fn in checkers):
        raise PermissionDenied


def require_view_members(request):
    require_any(request, can_view_members, can_manage_members)


def require_add_members(request):
    if not can_add_members(request.user):
        raise PermissionDenied


def require_edit_members(request):
    if not can_edit_members(request.user):
        raise PermissionDenied


def require_export_members(request):
    if not can_export_members(request.user):
        raise PermissionDenied


def require_transfer_members(request):
    if not can_transfer_members(request.user):
        raise PermissionDenied


def require_process_transfers(request):
    if not can_process_transfers(request.user):
        raise PermissionDenied


def require_view_records(request):
    require_any(
        request,
        can_view_member_records,
        can_manage_member_records,
        can_view_members,
        can_manage_members,
    )


def require_manage_records(request):
    if not can_manage_member_records(request.user):
        raise PermissionDenied


def require_manage_departments(request):
    if not can_manage_departments(request.user):
        raise PermissionDenied


def require_manage_families(request):
    if not can_manage_families(request.user):
        raise PermissionDenied


def require_manage_leadership(request):
    if not can_manage_leadership(request.user):
        raise PermissionDenied


def require_manage_gifts(request):
    if not can_manage_spiritual_gifts(request.user):
        raise PermissionDenied


def require_manage_configuration(request):
    if not (
        can_manage_member_configuration(request.user)
        or can_manage_occupations(request.user)
        or can_manage_member_lookups(request.user)
        or can_manage_members(request.user)
    ):
        raise PermissionDenied


def require_manage_occupations(request):
    if not (can_manage_occupations(request.user) or can_manage_members(request.user)):
        raise PermissionDenied


def require_manage_member_lookups(request):
    if not (can_manage_member_lookups(request.user) or can_manage_members(request.user)):
        raise PermissionDenied


def require_baptism_register(request):
    require_any(
        request,
        can_view_members,
        can_manage_members,
        can_manage_baptisms,
        can_view_member_records,
    )


def require_view_visitors(request):
    """Visitors reuse member view permissions (no separate registry codename yet)."""
    require_view_members(request)


def require_manage_visitors(request):
    """Visitors reuse member manage/add/edit permissions for now."""
    require_any(request, can_manage_members, can_add_members, can_edit_members)
