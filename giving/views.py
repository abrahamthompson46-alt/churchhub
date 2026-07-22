from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from church_system.church_scope import require_church
from giving import selectors
from permissions.checks import (
    can_export_giving,
    can_manage_finances,
    can_view_giving,
)
from reports.exporters import export_table_csv, export_table_excel, export_table_pdf
from sitecontrol.checks import require_feature

from .services import (
    can_view_member_giving,
    church_giving_leaders,
    export_giving_statement_table,
    member_giving_lines,
    member_giving_summary,
)


@login_required
@require_feature("giving_portal")
def giving_index(request):
    if not (can_view_giving(request.user) or can_manage_finances(request.user)):
        raise PermissionDenied
    church = require_church(request)
    year = int(request.GET.get("year", timezone.now().year))
    leaders = church_giving_leaders(church, year=year)
    return render(request, "giving/index.html", {
        "leaders": leaders,
        "year": year,
        "church": church,
    })


@login_required
@require_feature("giving_portal")
def member_statement(request, member_id):
    member = selectors.get_scoped_member_or_404(request, member_id)
    if not can_view_member_giving(request.user, member):
        raise PermissionDenied
    year = int(request.GET.get("year", timezone.now().year))
    summary = member_giving_summary(member, year=year)
    lines = member_giving_lines(member, year=year)

    export_fmt = request.GET.get("export")
    if export_fmt in ("csv", "excel", "pdf"):
        if not (can_export_giving(request.user) or can_manage_finances(request.user)):
            raise PermissionDenied
        payload = export_giving_statement_table(lines)
        slug = f"giving-{member.pk}-{year}"
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="giving_statement",
            export_format=export_fmt,
            row_count=len(payload["rows"]),
            church=member.church,
            params={"member_id": str(member.pk), "year": year},
        )
        if export_fmt == "csv":
            return export_table_csv(
                payload["headers"], payload["rows"], f"{slug}.csv"
            )
        if export_fmt == "excel":
            return export_table_excel(
                payload["headers"],
                payload["rows"],
                f"{slug}.xlsx",
                payload["title"],
            )
        return export_table_pdf(
            payload["headers"],
            payload["rows"],
            payload["title"],
            member.full_name,
            f"{slug}.pdf",
        )

    return render(request, "giving/statement.html", {
        "member": member,
        "year": year,
        "summary": summary,
        "lines": lines,
        "breadcrumbs": [
            {"label": "Giving", "url": "/giving/"},
            {"label": member.full_name},
        ],
    })
