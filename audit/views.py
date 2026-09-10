"""HTTP for enterprise controls (summary) and audit search (detail)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render

from audit import selectors
from permissions.checks import (
    can_export_enterprise_audit,
    can_view_enterprise_audit,
    can_view_enterprise_controls,
    permission_required,
)
from reports.exporters import export_table_csv


@login_required
@permission_required("view_enterprise_controls")
def controls_home(request):
    """Counts/tiles for all control users; District Admin has no event drill-down."""
    summary = selectors.summary_counts(request.user, days=7, request=request)
    can_detail = can_view_enterprise_audit(request.user)
    return render(
        request,
        "audit/controls_home.html",
        {
            "summary": summary,
            "can_detail": can_detail,
            "can_export": can_export_enterprise_audit(request.user),
        },
    )


@login_required
@permission_required("view_enterprise_audit")
def audit_event_list(request):
    qs = selectors.scoped_events_qs(request.user, request=request)
    domain = (request.GET.get("domain") or "").strip()
    action = (request.GET.get("action") or "").strip()
    if domain:
        qs = qs.filter(domain=domain)
    if action:
        qs = qs.filter(action=action)
    if request.GET.get("export") == "csv":
        if not can_export_enterprise_audit(request.user):
            raise PermissionDenied
        headers = ["occurred_at", "domain", "action", "church", "actor", "object", "outcome"]
        rows = [
            [
                event.occurred_at.isoformat(timespec="seconds"),
                event.domain,
                event.action,
                event.church.name if event.church_id else "",
                str(event.actor or ""),
                event.object_label,
                event.outcome,
            ]
            for event in qs[:5000]
        ]
        return export_table_csv(headers, rows, "enterprise-audit.csv")
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "audit/event_list.html",
        {
            "page_obj": page,
            "events": page,
            "filter_domain": domain,
            "filter_action": action,
            "can_export": can_export_enterprise_audit(request.user),
        },
    )


@login_required
@permission_required("view_enterprise_audit")
def audit_event_detail(request, pk):
    event = selectors.event_for_user(request.user, pk)
    if event is None:
        raise Http404()
    return render(request, "audit/event_detail.html", {"event": event})
