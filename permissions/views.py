from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from church_system.flash import flash_info, flash_success

from accounts.control_center import ucc_context
from permissions.checks import can_manage_permissions
from permissions.forms import PermissionMatrixForm, PermissionOverrideForm
from permissions.models import PermissionAuditLog, PermissionOverride
from permissions.scoping import get_manageable_users, user_may_manage_target
from permissions.services import (
    bulk_update_matrix,
    create_override,
    get_client_ip,
    get_effective_permissions,
    get_matrix_data,
    log_permission_audit,
    reset_matrix_to_defaults,
)
from permissions.roles import UserRole


def _require_permissions_admin(request):
    if not can_manage_permissions(request.user):
        raise PermissionDenied


def _manageable_user_ids(user):
    return get_manageable_users(user).values_list("pk", flat=True)


@login_required
def index(request):
    _require_permissions_admin(request)
    matrix = get_matrix_data()
    user_ids = _manageable_user_ids(request.user)
    override_count = PermissionOverride.objects.filter(is_active=True, user_id__in=user_ids).count()
    audit_count = PermissionAuditLog.objects.filter(target_user_id__in=user_ids).count()
    return render(request, "permissions/index.html", {
        "matrix_summary": matrix,
        "override_count": override_count,
        "audit_count": audit_count,
        "role_count": len(UserRole.CHOICES),
        "permission_count": len(matrix["permissions"]),
        **ucc_context(request.user, active="access"),
    })


@login_required
def role_matrix(request):
    _require_permissions_admin(request)
    data = get_matrix_data()
    matrix_rows = []
    for category, perms in data["categories"].items():
        rows = []
        for perm in perms:
            cells = []
            for role, _label in data["roles"]:
                cells.append({
                    "role": role,
                    "granted": data["cells"].get((role, perm.id), False),
                    "field_name": f"cell_{role}_{perm.id}",
                })
            meta = data["registry_meta"].get(perm.codename, {})
            rows.append({
                "permission": perm,
                "cells": cells,
                "implies": meta.get("implies", []),
                "conflicts_with": meta.get("conflicts_with", []),
            })
        matrix_rows.append({"category": category, "rows": rows})

    form = PermissionMatrixForm(
        permissions=data["permissions"],
        roles=data["roles"],
        cells=data["cells"],
    )

    if request.method == "POST":
        if "reset_defaults" in request.POST:
            reset_matrix_to_defaults(
                performed_by=request.user,
                ip_address=get_client_ip(request),
            )
            flash_success(request, "Permission matrix reset to defaults.")
            return redirect("permissions:matrix")

        form = PermissionMatrixForm(
            request.POST,
            permissions=data["permissions"],
            roles=data["roles"],
            cells=data["cells"],
        )
        updates = []
        for role, _label in data["roles"]:
            for perm in data["permissions"]:
                key = f"cell_{role}_{perm.id}"
                granted = form.data.get(key) == "on"
                current = data["cells"].get((role, perm.id), False)
                if granted != current:
                    updates.append((role, perm.id, granted))
        if updates:
            bulk_update_matrix(
                updates,
                updated_by=request.user,
                ip_address=get_client_ip(request),
            )
            flash_success(request, f"Updated {len(updates)} permission cell(s).")
        else:
            flash_info(request, "No changes to save.")
        return redirect("permissions:matrix")

    return render(request, "permissions/matrix.html", {
        "form": form,
        "roles": data["roles"],
        "matrix_rows": matrix_rows,
        "registry_meta": data["registry_meta"],
        **ucc_context(request.user, active="matrix"),
    })


@login_required
def role_list(request):
    _require_permissions_admin(request)
    data = get_matrix_data()
    role_summaries = []
    for role, label in UserRole.CHOICES:
        granted = sum(
            1 for perm in data["permissions"]
            if data["cells"].get((role, perm.id), False)
        )
        role_summaries.append({
            "role": role,
            "label": label,
            "granted_count": granted,
            "total": len(data["permissions"]),
        })
    return render(request, "permissions/role_list.html", {
        "roles": role_summaries,
        **ucc_context(request.user, active="roles"),
    })


@login_required
def role_detail(request, role):
    _require_permissions_admin(request)
    valid_roles = {r for r, _ in UserRole.CHOICES}
    if role not in valid_roles:
        raise PermissionDenied
    data = get_matrix_data()
    permissions_by_category = {}
    for perm in data["permissions"]:
        permissions_by_category.setdefault(perm.category, []).append({
            "permission": perm,
            "granted": data["cells"].get((role, perm.id), False),
        })
    return render(request, "permissions/role_detail.html", {
        "role": role,
        "role_label": UserRole.label(role),
        "permissions_by_category": permissions_by_category,
        **ucc_context(request.user, active="roles"),
    })


@login_required
def override_list(request):
    _require_permissions_admin(request)
    user_ids = _manageable_user_ids(request.user)
    overrides = PermissionOverride.objects.filter(user_id__in=user_ids).select_related(
        "user", "permission", "created_by"
    ).order_by("-created_at")[:200]
    return render(request, "permissions/override_list.html", {
        "overrides": overrides,
        **ucc_context(request.user, active="overrides"),
    })


@login_required
def override_create(request):
    _require_permissions_admin(request)
    if request.method == "POST":
        form = PermissionOverrideForm(request.POST, manager=request.user)
        if form.is_valid():
            override = form.save(commit=False)
            override.created_by = request.user
            override.save()
            log_permission_audit(
                "OVERRIDE_CREATE",
                performed_by=request.user,
                target_user=override.user,
                ip_address=get_client_ip(request),
                details={
                    "permission": override.permission.codename,
                    "granted": override.granted,
                    "override_id": str(override.id),
                },
            )
            flash_success(request, f"Override saved for {override.user.username}.")
            return redirect("permissions:override_list")
    else:
        form = PermissionOverrideForm(manager=request.user)
    return render(request, "permissions/override_form.html", {
        "form": form,
        "title": "Add Permission Override",
        **ucc_context(request.user, active="overrides"),
    })


@login_required
def override_edit(request, pk):
    _require_permissions_admin(request)
    override = get_object_or_404(
        PermissionOverride.objects.filter(user_id__in=_manageable_user_ids(request.user)),
        pk=pk,
    )
    if request.method == "POST":
        form = PermissionOverrideForm(request.POST, instance=override, manager=request.user)
        if form.is_valid():
            form.save()
            log_permission_audit(
                "OVERRIDE_UPDATE",
                performed_by=request.user,
                target_user=override.user,
                ip_address=get_client_ip(request),
                details={"override_id": str(override.id)},
            )
            flash_success(request, "Override updated.")
            return redirect("permissions:override_list")
    else:
        form = PermissionOverrideForm(instance=override, manager=request.user)
    return render(request, "permissions/override_form.html", {
        "form": form,
        "title": "Edit Permission Override",
        "override": override,
        **ucc_context(request.user, active="overrides"),
    })


@login_required
def override_delete(request, pk):
    _require_permissions_admin(request)
    override = get_object_or_404(
        PermissionOverride.objects.filter(user_id__in=_manageable_user_ids(request.user)),
        pk=pk,
    )
    if request.method == "POST":
        log_permission_audit(
            "OVERRIDE_DELETE",
            performed_by=request.user,
            target_user=override.user,
            ip_address=get_client_ip(request),
            details={
                "permission": override.permission.codename,
                "override_id": str(override.id),
            },
        )
        override.delete()
        flash_success(request, "Override removed.")
        return redirect("permissions:override_list")
    return render(request, "permissions/override_confirm_delete.html", {
        "override": override,
        **ucc_context(request.user, active="overrides"),
    })


@login_required
def user_effective(request, user_id):
    _require_permissions_admin(request)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)
    if not user_may_manage_target(request.user, target) and not request.user.is_superuser:
        raise PermissionDenied("You may only inspect effective permissions within your organization scope.")
    effective = get_effective_permissions(target)
    overrides = PermissionOverride.objects.filter(user=target).select_related("permission")
    grouped = {}
    for codename, allowed in effective.items():
        from permissions.registry import PERMISSION_REGISTRY
        meta = PERMISSION_REGISTRY.get(codename, {})
        cat = meta.get("category", "Other")
        grouped.setdefault(cat, []).append({
            "codename": codename,
            "name": meta.get("name", codename),
            "allowed": allowed,
        })
    return render(request, "permissions/user_effective.html", {
        "target_user": target,
        "grouped_permissions": grouped,
        "overrides": overrides,
        **ucc_context(request.user, active="directory"),
    })


@login_required
def audit_log(request):
    _require_permissions_admin(request)
    user_ids = _manageable_user_ids(request.user)
    logs = PermissionAuditLog.objects.filter(
        target_user_id__in=user_ids
    ).select_related(
        "performed_by", "target_user"
    ).order_by("-created_at")[:300]
    return render(request, "permissions/audit_log.html", {
        "logs": logs,
        **ucc_context(request.user, active="audit"),
    })


@login_required
def export_matrix_csv(request):
    _require_permissions_admin(request)
    import csv
    data = get_matrix_data()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="churchhub-permission-matrix.csv"'
    writer = csv.writer(response)
    header = ["Permission", "Category"] + [label for _role, label in data["roles"]]
    writer.writerow(header)
    for perm in data["permissions"]:
        row = [perm.name, perm.category]
        for role, _label in data["roles"]:
            row.append("Yes" if data["cells"].get((role, perm.id), False) else "No")
        writer.writerow(row)
    return response
