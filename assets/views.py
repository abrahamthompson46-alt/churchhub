"""Fixed asset register views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_exception, flash_success, flash_warning
from permissions.checks import (
    can_approve_assets,
    can_manage_asset_policy,
    can_manage_assets,
    can_view_all_churches,
)
from sitecontrol.checks import require_feature

from .forms import (
    AssetCategoryForm,
    DepreciationPolicyForm,
    FixedAssetForm,
    MaintenanceLogForm,
    RejectAssetForm,
    RunDepreciationForm,
)
from .models import AssetCategory, FixedAsset
from .rbac import get_hierarchy_context, user_may_view_assets
from .services import (
    AssetError,
    approve_asset,
    asset_register_csv,
    church_activity_logs,
    dispose_asset,
    ensure_depreciation_policy,
    generate_asset_code,
    hierarchy_asset_rollup,
    insurance_warranty_alerts,
    log_policy_change,
    preview_monthly_depreciation,
    register_dashboard_kpis,
    reject_asset,
    run_monthly_depreciation,
    submit_asset_for_approval,
)


def _assets_access(view_func):
    @login_required
    @require_feature("assets")
    def _wrapped(request, *args, **kwargs):
        if not can_manage_assets(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _policy_access(view_func):
    @login_required
    @require_feature("assets")
    def _wrapped(request, *args, **kwargs):
        if not can_manage_asset_policy(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _assets_read_access(view_func):
    @login_required
    @require_feature("assets")
    def _wrapped(request, *args, **kwargs):
        if not user_may_view_assets(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


@_assets_read_access
def index(request):
    church = require_church(request)
    kpis = register_dashboard_kpis(church)
    alerts = insurance_warranty_alerts(church)
    context = {
        **kpis,
        "alerts": alerts[:10],
        "can_manage": can_manage_assets(request.user),
        "can_approve": can_approve_assets(request.user),
        "can_policy": can_manage_asset_policy(request.user),
    }
    return render(request, "assets/index.html", context)


@_assets_access
def asset_list(request):
    church = require_church(request)
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    assets = FixedAsset.objects.filter(church=church).select_related("category")
    if status:
        assets = assets.filter(status=status)
    if q:
        assets = assets.filter(
            Q(asset_code__icontains=q)
            | Q(name__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(location__icontains=q)
        )
    paginator = Paginator(assets, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "assets/asset_list.html", {
        "assets": page_obj,
        "page_obj": page_obj,
        "status_filter": status,
        "search_query": q,
        "status_choices": FixedAsset.STATUS_CHOICES,
        "can_approve": can_approve_assets(request.user),
    })


@_assets_access
def asset_create(request):
    church = require_church(request)
    if request.method == "POST":
        form = FixedAssetForm(request.POST, church=church)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.church = church
            asset.asset_code = generate_asset_code(church)
            asset.created_by = request.user
            asset.status = "DRAFT"
            asset.save()
            flash_success(request, f"Asset {asset.asset_code} saved as draft.")
            return redirect("assets:asset_detail", pk=asset.pk)
    else:
        form = FixedAssetForm(church=church)
    return render(request, "assets/asset_form.html", {"form": form, "title": "New Fixed Asset"})


@login_required
@require_feature("assets")
def asset_detail(request, pk):
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    if not user_may_view_assets(request.user):
        raise PermissionDenied
    maintenance_form = MaintenanceLogForm()
    reject_form = RejectAssetForm()
    return render(request, "assets/asset_detail.html", {
        "asset": asset,
        "maintenance_form": maintenance_form,
        "reject_form": reject_form,
        "can_manage": can_manage_assets(request.user),
        "can_approve": can_approve_assets(request.user),
        "depreciation_entries": asset.depreciation_entries.all()[:24],
        "audit_logs": asset.audit_logs.all()[:20],
        "maintenance_logs": asset.maintenance_logs.all()[:20],
    })


@_assets_access
def asset_edit(request, pk):
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    if not asset.is_editable:
        flash_warning(request, "Approved assets cannot be edited. Contact an administrator.")
        return redirect("assets:asset_detail", pk=asset.pk)
    if request.method == "POST":
        form = FixedAssetForm(request.POST, instance=asset, church=church)
        if form.is_valid():
            form.save()
            flash_success(request, "Asset updated.")
            return redirect("assets:asset_detail", pk=asset.pk)
    else:
        form = FixedAssetForm(instance=asset, church=church)
    return render(request, "assets/asset_form.html", {"form": form, "title": f"Edit {asset.asset_code}"})


@_assets_access
@require_POST
def asset_submit(request, pk):
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    try:
        submit_asset_for_approval(asset, request.user)
        flash_success(request, "Asset submitted for approval.")
    except AssetError as exc:
        flash_exception(request, exc)
    return redirect("assets:asset_detail", pk=asset.pk)


@login_required
@require_feature("assets")
@require_POST
def asset_approve(request, pk):
    if not can_approve_assets(request.user):
        raise PermissionDenied
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    try:
        approve_asset(asset, request.user)
        flash_success(request, f"Asset {asset.asset_code} approved and activated.")
    except AssetError as exc:
        flash_exception(request, exc)
    return redirect("assets:asset_detail", pk=asset.pk)


@login_required
@require_feature("assets")
@require_POST
def asset_reject(request, pk):
    if not can_approve_assets(request.user):
        raise PermissionDenied
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    form = RejectAssetForm(request.POST)
    if form.is_valid():
        try:
            reject_asset(asset, request.user, form.cleaned_data["reason"])
            flash_success(request, "Asset rejected.")
        except AssetError as exc:
            flash_exception(request, exc)
    else:
        flash_warning(request, "Rejection reason is required.")
    return redirect("assets:asset_detail", pk=asset.pk)


@_assets_access
@require_POST
def asset_dispose(request, pk):
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    notes = request.POST.get("notes", "")
    try:
        dispose_asset(asset, request.user, notes=notes)
        flash_success(request, "Asset marked as disposed.")
    except AssetError as exc:
        flash_exception(request, exc)
    return redirect("assets:asset_detail", pk=asset.pk)


@_assets_access
def asset_export_csv(request):
    church = require_church(request)
    csv_data = asset_register_csv(church)
    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="asset-register-{church.code}.csv"'
    return response


@_assets_access
@require_POST
def maintenance_add(request, pk):
    church = require_church(request)
    asset = get_object_or_404(FixedAsset, pk=pk, church=church)
    if asset.status == "DISPOSED":
        flash_warning(request, "Cannot add maintenance to a disposed asset.")
        return redirect("assets:asset_detail", pk=asset.pk)
    form = MaintenanceLogForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        log.asset = asset
        log.recorded_by = request.user
        log.save()
        flash_success(request, "Maintenance record added.")
    return redirect("assets:asset_detail", pk=asset.pk)


@_policy_access
def policy_edit(request):
    church = require_church(request)
    policy = ensure_depreciation_policy(church)
    if request.method == "POST":
        form = DepreciationPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            log_policy_change(
                church,
                "POLICY_UPDATE",
                request.user,
                target_label="Depreciation Policy",
                notes="Policy settings updated.",
            )
            flash_success(request, "Depreciation policy saved.")
            return redirect("assets:policy_edit")
    else:
        form = DepreciationPolicyForm(instance=policy)
    return render(request, "assets/policy_form.html", {"form": form})


@_policy_access
def category_list(request):
    church = require_church(request)
    categories = AssetCategory.objects.filter(church=church).select_related("template")
    return render(request, "assets/category_list.html", {"categories": categories})


@_policy_access
def category_create(request):
    church = require_church(request)
    if request.method == "POST":
        form = AssetCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.church = church
            category.is_custom = True
            category.save()
            log_policy_change(
                church,
                "CATEGORY_CREATE",
                request.user,
                target_label=category.name,
                details={"code": category.code},
            )
            flash_success(request, "Custom category created.")
            return redirect("assets:category_list")
    else:
        form = AssetCategoryForm()
    return render(request, "assets/category_form.html", {"form": form, "title": "New Category"})


@_policy_access
def category_edit(request, pk):
    church = require_church(request)
    category = get_object_or_404(AssetCategory, pk=pk, church=church)
    if request.method == "POST":
        form = AssetCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            log_policy_change(
                church,
                "CATEGORY_UPDATE",
                request.user,
                target_label=category.name,
                details={"code": category.code, "is_custom": category.is_custom},
            )
            flash_success(request, "Category updated.")
            return redirect("assets:category_list")
    else:
        form = AssetCategoryForm(instance=category)
    return render(request, "assets/category_form.html", {"form": form, "title": category.name})


@_policy_access
def run_depreciation(request):
    church = require_church(request)
    now = timezone.now()
    preview = None
    year = request.GET.get("year") or request.POST.get("year")
    month = request.GET.get("month") or request.POST.get("month")
    try:
        year = int(year) if year else now.year
        month = int(month) if month else now.month
    except (TypeError, ValueError):
        year, month = now.year, now.month

    if request.method == "GET" and request.GET.get("preview") == "1":
        try:
            preview = preview_monthly_depreciation(church, year, month)
        except AssetError as exc:
            flash_exception(request, exc)

    if request.method == "POST":
        form = RunDepreciationForm(request.POST)
        if form.is_valid():
            year = form.cleaned_data["year"]
            month = form.cleaned_data["month"]
            if request.POST.get("async") == "1":
                from church_system.tasks import run_church_depreciation_task

                if not can_manage_asset_policy(request.user):
                    raise PermissionDenied
                active = get_active_church(request)
                if not active or active.pk != church.pk:
                    raise PermissionDenied
                run_church_depreciation_task.delay(
                    str(church.pk), year, month, str(request.user.pk)
                )
                flash_success(request, "Depreciation run queued in the background.")
                return redirect("assets:run_depreciation")
            result = run_monthly_depreciation(church, year, month, request.user)
            flash_success(
                request,
                f"Depreciation run complete: {result['posted']} posted, {result['skipped']} skipped.",
            )
            if result["errors"]:
                flash_warning(request, "; ".join(result["errors"][:5]))
            return redirect("assets:run_depreciation")
    else:
        form = RunDepreciationForm(initial={"year": year, "month": month})

    return render(request, "assets/run_depreciation.html", {
        "form": form,
        "preview": preview,
        "preview_year": year,
        "preview_month": month,
    })


@_assets_read_access
def activity_log(request):
    church = require_church(request)
    action = request.GET.get("action", "").strip()
    entries = church_activity_logs(church, action=action)
    paginator = Paginator(entries, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    action_choices = sorted({
        row["action"] for row in entries
    })
    return render(request, "assets/activity_log.html", {
        "entries": page_obj,
        "page_obj": page_obj,
        "action_filter": action,
        "action_choices": action_choices,
    })


@_assets_read_access
def activity_log_export(request):
    church = require_church(request)
    import csv
    from io import StringIO

    action = request.GET.get("action", "").strip()
    entries = church_activity_logs(church, action=action, limit=5000)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["When", "Type", "Action", "Target", "User", "Notes"])
    for row in entries:
        writer.writerow([
            row["when"].isoformat(),
            row["kind"],
            row["action"],
            row["label"],
            row["user"].username if row["user"] else "",
            row["notes"],
        ])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="asset-activity-{church.code}.csv"'
    return response


@login_required
@require_feature("assets")
def hierarchy_rollup(request):
    if not can_view_all_churches(request.user):
        raise PermissionDenied
    conference_id = request.GET.get("conference") or None
    zone_id = request.GET.get("zone") or None
    district_id = request.GET.get("district") or None
    rows = hierarchy_asset_rollup(
        request.user,
        conference_id=conference_id,
        zone_id=zone_id,
        district_id=district_id,
    )
    hctx = get_hierarchy_context(request.user)
    zones = hctx["zones"]
    districts = hctx["districts"]
    if conference_id:
        zones = zones.filter(conference_id=conference_id)
        districts = districts.filter(zone__conference_id=conference_id)
    if zone_id:
        districts = districts.filter(zone_id=zone_id)
    return render(request, "assets/hierarchy.html", {
        "rows": rows,
        "conferences": hctx["conferences"],
        "zones": zones,
        "districts": districts,
        "selected_conference": conference_id,
        "selected_zone": zone_id,
        "selected_district": district_id,
        "can_filter_hierarchy": hctx["can_filter_hierarchy"],
    })
