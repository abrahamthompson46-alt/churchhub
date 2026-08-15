"""Dashboard views for contribution campaigns."""

from functools import wraps
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from church_system.church_scope import require_church
from church_system.flash import flash_error, flash_exception, flash_success, flash_warning
from church_system.spreadsheet_io import build_template_xlsx
from permissions.checks import (
    any_permission_required,
    can_manage_contribution_campaigns,
    can_manage_finances,
    can_record_contributions,
    can_view_contribution_reports,
)
from reports.exporters import export_table_csv, export_table_excel
from sitecontrol.checks import require_feature

from .forms import (
    BulkContributionForm,
    CampaignFilterForm,
    CampaignImportForm,
    ContributionCampaignForm,
    RecordContributionForm,
)
from .import_services import commit_campaign_import, preview_campaign_import
from . import selectors
from .services import (
    ContributionServiceError,
    archive_campaign,
    build_bulk_entry_rows,
    build_campaign_summary,
    close_campaign,
    create_campaign,
    open_campaign,
    record_bulk_contributions,
    record_member_contribution,
    save_member_targets,
    update_campaign,
)


def _campaign_view_required(view_func):
    @login_required
    @require_feature("contribution_campaigns")
    @any_permission_required(
        "view_contribution_reports",
        "manage_contribution_campaigns",
        "record_contributions",
        "manage_finances",
    )
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def _campaign_manage_required(view_func):
    @login_required
    @require_feature("contribution_campaigns")
    @any_permission_required("manage_contribution_campaigns", "manage_finances")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def _record_required(view_func):
    @login_required
    @require_feature("contribution_campaigns")
    @any_permission_required("record_contributions", "manage_contribution_campaigns", "manage_finances")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


@_campaign_view_required
def campaign_list(request):
    church = require_church(request)
    filter_form = CampaignFilterForm(request.GET or None)
    status = filter_form.data.get("status") if filter_form.is_valid() else None
    campaigns = selectors.campaigns_for_church(church, status=status or None)
    rows = []
    for campaign in campaigns:
        summary = build_campaign_summary(campaign)
        rows.append({"campaign": campaign, "summary": summary})
    return render(
        request,
        "contributions/campaign_list.html",
        {
            "rows": rows,
            "filter_form": filter_form,
            "church": church,
            "can_manage": can_manage_contribution_campaigns(request.user)
            or can_manage_finances(request.user),
        },
    )


@_campaign_manage_required
def campaign_create(request):
    church = require_church(request)
    form = ContributionCampaignForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        try:
            campaign = create_campaign(
                church,
                performed_by=request.user,
                name=form.cleaned_data["name"],
                code=form.cleaned_data["code"],
                purpose=form.cleaned_data["purpose"],
                deadline=form.cleaned_data["deadline"],
                offering_category=form.cleaned_data["offering_category"],
                target_amount=form.cleaned_data.get("target_amount"),
                default_member_target=form.cleaned_data.get("default_member_target"),
                portal_visible=form.cleaned_data["portal_visible"],
                show_church_progress=form.cleaned_data["show_church_progress"],
                send_email_reminders=form.cleaned_data["send_email_reminders"],
            )
            flash_success(request, f"Campaign “{campaign.name}” saved as draft.")
            return redirect("contributions:campaign_detail", pk=campaign.pk)
        except Exception as exc:
            flash_exception(request, exc)
    return render(
        request,
        "contributions/campaign_form.html",
        {"form": form, "title": "New Contribution Campaign", "church": church},
    )


@_campaign_manage_required
def campaign_edit(request, pk):
    church = require_church(request)
    campaign = selectors.get_campaign_or_404(request, pk)
    form = ContributionCampaignForm(request.POST or None, instance=campaign, church=church)
    if request.method == "POST" and form.is_valid():
        try:
            update_campaign(
                campaign,
                performed_by=request.user,
                **form.cleaned_data,
            )
            flash_success(request, f"Campaign “{campaign.name}” updated.")
            return redirect("contributions:campaign_detail", pk=campaign.pk)
        except Exception as exc:
            flash_exception(request, exc)
    return render(
        request,
        "contributions/campaign_form.html",
        {"form": form, "title": f"Edit {campaign.name}", "campaign": campaign, "church": church},
    )


@_campaign_view_required
def campaign_detail(request, pk):
    church = require_church(request)
    campaign = selectors.get_campaign_or_404(request, pk)
    summary = build_campaign_summary(campaign)
    member_totals = list(selectors.campaign_member_totals(campaign))
    non_contributors = selectors.members_without_contribution(campaign)[:50]
    record_form = RecordContributionForm(
        church=church,
        initial={"idempotency_key": str(uuid.uuid4())},
    )
    can_record = (
        can_record_contributions(request.user)
        or can_manage_contribution_campaigns(request.user)
        or can_manage_finances(request.user)
    ) and campaign.is_open
    can_manage = can_manage_contribution_campaigns(request.user) or can_manage_finances(request.user)

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        if not (can_view_contribution_reports(request.user) or can_manage_finances(request.user)):
            raise PermissionDenied
        headers = ["Member", "Membership #", "Total", "Gifts"]
        rows = [
            [
                f"{row['member__first_name']} {row['member__last_name']}".strip(),
                row["member__membership_number"] or "",
                row["total"],
                row["gift_count"],
            ]
            for row in member_totals
        ]
        slug = f"campaign-{campaign.code.lower()}"
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        return export_table_excel(headers, rows, f"{slug}.xlsx", campaign.name[:31])

    recent = selectors.contributions_for_campaign(campaign)[:25]
    return render(
        request,
        "contributions/campaign_detail.html",
        {
            "campaign": campaign,
            "summary": summary,
            "member_totals": member_totals,
            "non_contributors": non_contributors,
            "recent_contributions": recent,
            "record_form": record_form,
            "can_record": can_record,
            "can_manage": can_manage,
            "church": church,
        },
    )


@_record_required
@require_POST
def campaign_record_contribution(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    form = RecordContributionForm(request.POST, church=campaign.church)
    if not form.is_valid():
        flash_error(request, "Could not record contribution. Check the form and try again.")
        return redirect("contributions:campaign_detail", pk=campaign.pk)
    try:
        record_member_contribution(
            campaign,
            member=form.cleaned_data["member"],
            amount=form.cleaned_data["amount"],
            performed_by=request.user,
            contribution_date=form.cleaned_data["contribution_date"],
            notes=form.cleaned_data.get("notes") or "",
            payment_account_type=form.cleaned_data["payment_account_type"],
            idempotency_key=form.cleaned_data["idempotency_key"],
        )
        flash_success(request, "Contribution recorded and receipt posted.")
    except (ContributionServiceError, Exception) as exc:
        flash_exception(request, exc)
    return redirect("contributions:campaign_detail", pk=campaign.pk)


@_campaign_manage_required
@require_POST
def campaign_open(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    try:
        open_campaign(campaign, performed_by=request.user)
        flash_success(request, f"“{campaign.name}” is now open for contributions.")
    except ContributionServiceError as exc:
        flash_error(request, str(exc))
    return redirect("contributions:campaign_detail", pk=campaign.pk)


@_campaign_manage_required
@require_POST
def campaign_close(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    try:
        close_campaign(campaign, performed_by=request.user)
        flash_success(request, f"“{campaign.name}” has been closed.")
    except ContributionServiceError as exc:
        flash_error(request, str(exc))
    return redirect("contributions:campaign_detail", pk=campaign.pk)


@_campaign_manage_required
@require_POST
def campaign_archive(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    try:
        archive_campaign(campaign, performed_by=request.user)
        flash_success(request, f"“{campaign.name}” archived.")
    except ContributionServiceError as exc:
        flash_error(request, str(exc))
    return redirect("contributions:campaign_list")


@_record_required
def campaign_bulk_entry(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    if not campaign.is_open:
        flash_error(request, "Bulk entry is only available while the campaign is open.")
        return redirect("contributions:campaign_detail", pk=campaign.pk)
    bulk_form = BulkContributionForm(
        request.POST or None,
        initial={"idempotency_key": str(uuid.uuid4())},
    )
    rows = build_bulk_entry_rows(campaign)
    if request.method == "POST" and bulk_form.is_valid():
        from decimal import Decimal, InvalidOperation

        entries = []
        for row in rows:
            raw = (request.POST.get(f"amount_{row['member'].pk}") or "").strip()
            if not raw:
                continue
            try:
                amount = Decimal(raw)
            except InvalidOperation:
                flash_error(request, f"Invalid amount for {row['member'].full_name}.")
                return redirect("contributions:campaign_bulk", pk=campaign.pk)
            if amount > 0:
                entries.append({"member": row["member"], "amount": amount})
        try:
            created = record_bulk_contributions(
                campaign,
                entries=entries,
                performed_by=request.user,
                contribution_date=bulk_form.cleaned_data["contribution_date"],
                payment_account_type=bulk_form.cleaned_data["payment_account_type"],
                batch_idempotency_key=bulk_form.cleaned_data["idempotency_key"],
            )
            flash_success(request, f"Recorded {len(created)} contribution(s).")
            return redirect("contributions:campaign_detail", pk=campaign.pk)
        except Exception as exc:
            flash_exception(request, exc)
    return render(
        request,
        "contributions/campaign_bulk.html",
        {"campaign": campaign, "rows": rows, "bulk_form": bulk_form},
    )


@_record_required
def campaign_import(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    if not campaign.is_open:
        flash_error(request, "Import is only available while the campaign is open.")
        return redirect("contributions:campaign_detail", pk=campaign.pk)
    preview = None
    form = CampaignImportForm(request.POST or None, request.FILES or None)
    redirect_after = None
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        try:
            if form.cleaned_data.get("commit"):
                preview = commit_campaign_import(campaign, request.user, uploaded)
            else:
                preview = preview_campaign_import(campaign, uploaded)
        except Exception as exc:
            flash_exception(request, exc)
        else:
            if preview.failed:
                flash_warning(
                    request,
                    f"{preview.failed} of {preview.total} row(s) failed. Fix the file and try again.",
                )
            elif preview.dry_run:
                flash_success(
                    request,
                    f"All {preview.total} row(s) validated. Re-upload with Import now checked to commit.",
                )
            else:
                flash_success(request, f"Imported {preview.succeeded} contribution(s).")
                redirect_after = redirect("contributions:campaign_detail", pk=campaign.pk)
    if redirect_after:
        return redirect_after
    return render(
        request,
        "contributions/campaign_import.html",
        {"campaign": campaign, "form": form, "preview": preview},
    )


@_record_required
def campaign_import_template(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    content = build_template_xlsx(
        ["membership_number", "member_email", "amount", "date", "notes", "payment_method"],
        [["M-1001", "", "50.00", "", "Sabbath gift", "CASH"]],
    )
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{campaign.code.lower()}_import.xlsx"'
    return response


@_campaign_manage_required
def campaign_targets(request, pk):
    campaign = selectors.get_campaign_or_404(request, pk)
    rows = build_bulk_entry_rows(campaign)
    if request.method == "POST":
        from decimal import Decimal, InvalidOperation

        targets = {}
        for row in rows:
            member = row["member"]
            raw = (request.POST.get(f"target_{member.pk}") or "").strip()
            if not raw:
                targets[member.pk] = None
                continue
            try:
                targets[member.pk] = Decimal(raw)
            except InvalidOperation:
                flash_error(request, f"Invalid target for {member.full_name}.")
                return redirect("contributions:campaign_targets", pk=campaign.pk)
        try:
            count = save_member_targets(campaign, targets=targets, performed_by=request.user)
            flash_success(request, f"Updated {count} member target override(s).")
            return redirect("contributions:campaign_detail", pk=campaign.pk)
        except Exception as exc:
            flash_exception(request, exc)
    return render(
        request,
        "contributions/campaign_targets.html",
        {"campaign": campaign, "rows": rows},
    )
