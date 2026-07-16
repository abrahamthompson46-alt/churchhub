from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from church_system.church_scope import filter_by_church, require_church
from members.models import Member
from permissions.checks import (
    can_export_giving,
    can_manage_finances,
    can_view_giving,
)
from reports.exporters import export_table_csv, export_table_excel, export_table_pdf
from sitecontrol.checks import require_feature

from .services import church_giving_leaders, member_giving_lines, member_giving_summary


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
    member = get_object_or_404(
        filter_by_church(Member.objects.all(), request),
        pk=member_id,
    )
    from .services import can_view_member_giving
    if not can_view_member_giving(request.user, member):
        raise PermissionDenied
    year = int(request.GET.get("year", timezone.now().year))
    summary = member_giving_summary(member, year=year)
    lines = member_giving_lines(member, year=year)

    export_fmt = request.GET.get("export")
    if export_fmt in ("csv", "excel", "pdf"):
        if not (can_export_giving(request.user) or can_manage_finances(request.user)):
            raise PermissionDenied
        headers = ["Date", "Reference", "Account", "Amount"]
        rows = [
            [l.transaction.date, l.transaction.reference, l.account.name, abs(l.amount)]
            for l in lines
        ]
        slug = f"giving-{member.pk}-{year}"
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        if export_fmt == "excel":
            return export_table_excel(headers, rows, f"{slug}.xlsx", "Giving Statement")
        return export_table_pdf(headers, rows, "Giving Statement", member.full_name, f"{slug}.pdf")

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
