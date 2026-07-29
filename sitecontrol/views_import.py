"""Platform bulk import views (members and receipts)."""

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render

from church_system.flash import flash_error, flash_success, flash_warning
from church_system.spreadsheet_io import build_template_xlsx
from organization.models import Church
from sitecontrol.checks import platform_required, require_platform_capability
from sitecontrol.forms_import import PlatformDataImportForm
from sitecontrol.import_services import (
    commit_member_import,
    commit_transaction_import,
    preview_member_import,
    preview_transaction_import,
)
from sitecontrol.platform_access import filter_churches_for_operator
from sitecontrol.rbac import CAP_MANAGE_DATA_IMPORT
from sitecontrol.services import log_platform_action
from sitecontrol.views import _breadcrumbs, _require_tenant_access


def _church_queryset(user):
    return filter_churches_for_operator(
        Church.objects.select_related(
            "district__zone__conference__denomination",
        ).order_by("name"),
        user,
    )


@platform_required
@require_platform_capability(CAP_MANAGE_DATA_IMPORT)
def import_hub(request):
    return render(
        request,
        "sitecontrol/import_hub.html",
        {
            "breadcrumbs": _breadcrumbs(
                ("Platform", "/platform/"),
                ("Data Import",),
            ),
        },
    )


def _handle_import_post(request, *, kind: str):
    form = PlatformDataImportForm(
        request.POST or None,
        request.FILES or None,
        church_queryset=_church_queryset(request.user),
    )
    preview = None
    redirect_name = None
    if request.method == "POST" and form.is_valid():
        church = form.cleaned_data["church"]
        _require_tenant_access(request, church)
        uploaded = form.cleaned_data["file"]
        commit = form.cleaned_data.get("commit")
        try:
            if kind == "members":
                if commit:
                    preview = commit_member_import(church, request.user, uploaded)
                else:
                    preview = preview_member_import(uploaded)
            else:
                if commit:
                    preview = commit_transaction_import(church, request.user, uploaded)
                else:
                    preview = preview_transaction_import(church, uploaded)
        except ValidationError as exc:
            flash_error(request, exc.messages[0] if exc.messages else str(exc))
            return form, preview, None

        if preview.failed:
            flash_warning(
                request,
                f"{preview.failed} of {preview.total} row(s) failed validation. "
                "Fix the spreadsheet and preview again.",
            )
        elif preview.dry_run:
            flash_success(
                request,
                f"All {preview.total} row(s) passed validation. "
                "Upload the same file again with “Import now” checked to commit.",
            )
        else:
            action = "MEMBER_IMPORT" if kind == "members" else "TRANSACTION_IMPORT"
            denomination = None
            if church.district_id:
                denomination = church.district.zone.conference.denomination
            log_platform_action(
                request,
                action,
                f"Imported {preview.succeeded} {kind} row(s) for {church.name}",
                target_model="Church",
                target_id=church.pk,
                details={"total": preview.total, "failed": preview.failed},
                denomination=denomination,
            )
            flash_success(
                request,
                f"Successfully imported {preview.succeeded} row(s) for {church.name}.",
            )
            redirect_name = (
                "sitecontrol:import_members"
                if kind == "members"
                else "sitecontrol:import_transactions"
            )
    return form, preview, redirect_name


@platform_required
@require_platform_capability(CAP_MANAGE_DATA_IMPORT)
def import_members(request):
    form, preview, redirect_name = _handle_import_post(request, kind="members")
    if redirect_name:
        return redirect(redirect_name)
    return render(
        request,
        "sitecontrol/import_members.html",
        {
            "form": form,
            "preview": preview,
            "breadcrumbs": _breadcrumbs(
                ("Platform", "/platform/"),
                ("Data Import", "/platform/import/"),
                ("Members",),
            ),
        },
    )


@platform_required
@require_platform_capability(CAP_MANAGE_DATA_IMPORT)
def import_transactions(request):
    form, preview, redirect_name = _handle_import_post(request, kind="transactions")
    if redirect_name:
        return redirect(redirect_name)
    return render(
        request,
        "sitecontrol/import_transactions.html",
        {
            "form": form,
            "preview": preview,
            "breadcrumbs": _breadcrumbs(
                ("Platform", "/platform/"),
                ("Data Import", "/platform/import/"),
                ("Receipts",),
            ),
        },
    )


@platform_required
@require_platform_capability(CAP_MANAGE_DATA_IMPORT)
def import_member_template(request):
    content = build_template_xlsx(
        [
            "first_name",
            "last_name",
            "middle_name",
            "email",
            "phone",
            "gender",
            "date_of_birth",
            "membership_number",
            "membership_status",
            "date_joined",
        ],
        [
            [
                "John",
                "Smith",
                "",
                "john@example.org",
                "0240000000",
                "Male",
                "1990-05-15",
                "M-1001",
                "Active",
                "2024-01-01",
            ],
        ],
    )
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="churchhub_member_import_template.xlsx"'
    return response


@platform_required
@require_platform_capability(CAP_MANAGE_DATA_IMPORT)
def import_transaction_template(request):
    content = build_template_xlsx(
        [
            "date",
            "member_email",
            "membership_number",
            "tithe",
            "combined",
            "income",
            "description",
            "payment_method",
        ],
        [
            [
                "2025-01-15",
                "john@example.org",
                "",
                "100.00",
                "50.00",
                "",
                "Sabbath offering",
                "CASH",
            ],
        ],
    )
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="churchhub_receipt_import_template.xlsx"'
    return response
