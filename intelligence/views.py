"""HTTP for risk alerts and policy. Existing finance URLs stay."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from church_system.church_scope import require_church
from church_system.flash import flash_error, flash_exception, flash_success
from intelligence import selectors
from intelligence.forms import AlertNoteForm, RiskPolicyForm
from intelligence.services import confirm_alert, dismiss_alert, get_or_create_policy, save_risk_policy
from permissions.checks import (
    can_manage_risk_policy,
    can_review_risk_alerts,
    permission_required,
)


@login_required
@permission_required("view_risk_alerts")
def alert_list(request):
    qs = selectors.scoped_alerts_qs(request.user, request=request)
    severity = (request.GET.get("severity") or "").strip()
    if severity:
        qs = qs.filter(severity=severity)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "intelligence/alert_list.html",
        {
            "page_obj": page,
            "alerts": page,
            "filter_severity": severity,
            "can_review": can_review_risk_alerts(request.user),
            "can_manage_policy": can_manage_risk_policy(request.user),
        },
    )


@login_required
@permission_required("view_risk_alerts")
def alert_detail(request, pk):
    alert = selectors.alert_for_user(request.user, pk, request=request)
    if alert is None:
        raise Http404()
    return render(
        request,
        "intelligence/alert_detail.html",
        {
            "alert": alert,
            "note_form": AlertNoteForm(),
            "can_review": can_review_risk_alerts(request.user),
        },
    )


@login_required
@require_POST
@permission_required("review_risk_alerts")
def alert_dismiss(request, pk):
    alert = selectors.alert_for_user(request.user, pk, request=request)
    if alert is None:
        raise Http404()
    form = AlertNoteForm(request.POST)
    note = form.cleaned_data.get("note", "") if form.is_valid() else ""
    try:
        dismiss_alert(alert, request.user, note=note)
        flash_success(request, "Risk alert dismissed. The journal was not changed.")
    except PermissionDenied:
        raise
    except Exception as exc:
        flash_exception(request, exc)
    return redirect("intelligence:alert_detail", pk=pk)


@login_required
@require_POST
@permission_required("review_risk_alerts")
def alert_confirm(request, pk):
    alert = selectors.alert_for_user(request.user, pk, request=request)
    if alert is None:
        raise Http404()
    form = AlertNoteForm(request.POST)
    note = form.cleaned_data.get("note", "") if form.is_valid() else ""
    try:
        confirm_alert(alert, request.user, note=note)
        flash_success(request, "Risk alert confirmed. The journal was not approved or rejected.")
    except PermissionDenied:
        raise
    except Exception as exc:
        flash_exception(request, exc)
    return redirect("intelligence:alert_detail", pk=pk)


@login_required
@permission_required("manage_risk_policy")
def policy_edit(request):
    church = require_church(request)
    policy = get_or_create_policy(church)
    if request.method == "POST":
        form = RiskPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            try:
                save_risk_policy(church, request.user, **form.cleaned_data)
                flash_success(
                    request,
                    "Risk thresholds saved. Receipt auto-approve still follows TreasuryApprovalPolicy.",
                )
                return redirect("intelligence:policy")
            except PermissionDenied:
                raise
            except Exception as exc:
                flash_error(request, str(exc))
    else:
        form = RiskPolicyForm(instance=policy)
    return render(request, "intelligence/policy.html", {"form": form, "policy": policy})
