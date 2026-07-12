from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_info
from permissions.checks import can_view_reports

from .exporters import export_table_csv, export_table_excel, export_table_pdf
from .forms import ReportFilterForm, WelfareStatementForm
from .models import ReportAccessAuditLog, ReportExportJob
from .registry import REPORT_CATALOG
from .services import (
    build_report,
    get_hierarchy_context,
    log_report_access,
    reports_for_user,
    user_may_access_report,
)


def _hierarchy_kwargs(cleaned):
    kwargs = {}
    for key in ("conference", "zone", "district", "church"):
        val = cleaned.get(key)
        if val:
            kwargs[f"{key}_id"] = val.pk
    return kwargs


def _check_report_access(user, report_key, active_church=None):
    return user_may_access_report(user, report_key, active_church=active_church)


def _export_query_string(request, export_fmt, async_export=False):
    params = request.GET.copy()
    params["export"] = export_fmt
    if async_export:
        params["async"] = "1"
    elif "async" in params:
        del params["async"]
    return params.urlencode()


@login_required
def report_index(request):
    if not can_view_reports(request.user):
        raise PermissionDenied
    active = get_active_church(request)
    return render(request, "reports/index.html", {
        "reports": reports_for_user(request.user, active_church=active),
    })


def _export_params_from_form(cleaned):
    params = {
        "period": cleaned.get("period", "monthly"),
        "start_date": str(cleaned["start_date"]) if cleaned.get("start_date") else None,
        "end_date": str(cleaned["end_date"]) if cleaned.get("end_date") else None,
    }
    for key in ("conference", "zone", "district", "church"):
        val = cleaned.get(key)
        if val:
            params[f"{key}_id"] = str(val.pk)
    return params


def _queue_async_export(user, report_key, export_fmt, params):
    from church_system.tasks import generate_report_export_task

    job = ReportExportJob.objects.create(
        user=user,
        report_key=report_key,
        export_format=export_fmt,
        params=params,
    )
    generate_report_export_task.delay(str(job.pk))
    return job


@login_required
def export_job_status(request, pk):
    job = get_object_or_404(ReportExportJob, pk=pk, user=request.user)
    return render(request, "reports/export_job.html", {"job": job, "meta": REPORT_CATALOG.get(job.report_key)})


@login_required
def export_job_download(request, pk):
    job = get_object_or_404(ReportExportJob, pk=pk, user=request.user)
    if not job.is_ready:
        raise Http404
    return FileResponse(
        job.export_file.open("rb"),
        content_type=job.content_type,
        as_attachment=True,
        filename=job.export_file.name.split("/")[-1],
    )


@login_required
def run_report(request, report_key):
    active = get_active_church(request)
    if not _check_report_access(request.user, report_key, active_church=active):
        raise PermissionDenied
    meta = REPORT_CATALOG[report_key]
    hierarchy = get_hierarchy_context(request.user)
    form = ReportFilterForm(request.GET or None, user=request.user, hierarchy=hierarchy)

    data = None
    if form.is_valid():
        cleaned = form.cleaned_data
        data = build_report(
            report_key,
            request,
            period=cleaned.get("period", "monthly"),
            start_date=cleaned.get("start_date"),
            end_date=cleaned.get("end_date"),
            **_hierarchy_kwargs(cleaned),
        )

    export_fmt = request.GET.get("export")
    if data and export_fmt in ("csv", "excel", "pdf"):
        params = _export_params_from_form(form.cleaned_data)
        row_count = len(data.get("rows") or [])
        if request.GET.get("async") == "1":
            job = _queue_async_export(
                request.user,
                report_key,
                export_fmt,
                params,
            )
            log_report_access(
                user=request.user,
                report_key=report_key,
                action=ReportAccessAuditLog.ACTION_EXPORT,
                params={**params, "async": True, "job_id": str(job.pk)},
                row_count=row_count,
                church=active,
                export_format=export_fmt,
            )
            flash_info(request, "Your export is being prepared. You will be notified when it is ready.")
            return redirect("reports:export_job", pk=job.pk)
        log_report_access(
            user=request.user,
            report_key=report_key,
            action=ReportAccessAuditLog.ACTION_EXPORT,
            params=params,
            row_count=row_count,
            church=active,
            export_format=export_fmt,
        )
        slug = report_key.replace("_", "-")
        subtitle = f"{data['period_label']} — {data['start_date']} to {data['end_date']}"
        if export_fmt == "csv":
            return export_table_csv(data["headers"], data["rows"], f"{slug}.csv")
        if export_fmt == "excel":
            return export_table_excel(data["headers"], data["rows"], f"{slug}.xlsx", data["title"])
        return export_table_pdf(data["headers"], data["rows"], data["title"], subtitle, f"{slug}.pdf")

    if data:
        log_report_access(
            user=request.user,
            report_key=report_key,
            action=ReportAccessAuditLog.ACTION_RUN,
            params=_export_params_from_form(form.cleaned_data) if form.is_valid() else {},
            row_count=len(data.get("rows") or []),
            church=active,
        )

    export_links = {}
    if data:
        for fmt in ("csv", "excel", "pdf"):
            export_links[fmt] = "?" + _export_query_string(request, fmt)
        export_links["async_csv"] = "?" + _export_query_string(request, "csv", async_export=True)

    return render(request, "reports/run.html", {
        "report_key": report_key,
        "meta": meta,
        "form": form,
        "data": data,
        "export_links": export_links,
        "show_hierarchy": form.show_hierarchy_filters,
        "breadcrumbs": [
            {"label": "Reports", "url": "/reports/"},
            {"label": meta["label"]},
        ],
    })


@login_required
def welfare_statement(request):
    from accounts.permissions import can_manage_finances
    from remittance.welfare_services import (
        build_member_welfare_statement,
        member_welfare_cases,
        member_welfare_summary,
        welfare_module_enabled,
    )

    if not can_view_reports(request.user) or not can_manage_finances(request.user):
        raise PermissionDenied

    church = require_church(request)
    if not welfare_module_enabled(church, request.user):
        raise PermissionDenied

    form = WelfareStatementForm(request.GET or None, church=church)
    member = None
    statement = None
    summary = None
    cases = None

    if form.is_valid():
        member = form.cleaned_data["member_obj"]
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        statement = build_member_welfare_statement(member, start_date=start_date, end_date=end_date)
        summary = member_welfare_summary(member, start_date=start_date, end_date=end_date)
        cases = member_welfare_cases(member)

        export_fmt = request.GET.get("export")
        if export_fmt in ("csv", "excel", "pdf"):
            headers = ["Date", "Type", "Reference", "Description", "In", "Out", "Balance"]
            rows = []
            if statement["opening_balance"]:
                rows.append(["", "Opening", "", "Balance brought forward", "", "", statement["opening_balance"]])
            for row in statement["rows"]:
                rows.append([
                    row["date"],
                    row["type"],
                    row["reference"],
                    row["description"],
                    row["in_amount"] or "",
                    row["out_amount"] or "",
                    row["balance"],
                ])
            log_report_access(
                user=request.user,
                report_key="welfare_statement",
                action=ReportAccessAuditLog.ACTION_EXPORT,
                params={"member_id": str(member.pk), "export": export_fmt},
                row_count=len(rows),
                church=church,
                export_format=export_fmt,
            )
            slug = f"welfare-{member.pk}"
            if start_date:
                slug += f"-{start_date}"
            if export_fmt == "csv":
                return export_table_csv(headers, rows, f"{slug}.csv")
            if export_fmt == "excel":
                return export_table_excel(headers, rows, f"{slug}.xlsx", "Welfare Statement")
            return export_table_pdf(headers, rows, "Welfare Statement", member.full_name, f"{slug}.pdf")

        log_report_access(
            user=request.user,
            report_key="welfare_statement",
            action=ReportAccessAuditLog.ACTION_RUN,
            params={"member_id": str(member.pk)},
            row_count=len(statement.get("rows") or []),
            church=church,
        )

    return render(request, "reports/welfare_statement.html", {
        "form": form,
        "member": member,
        "statement": statement,
        "summary": summary,
        "cases": cases,
        "breadcrumbs": [
            {"label": "Reports", "url": "/reports/"},
            {"label": "Member Welfare Statement"},
        ],
    })
