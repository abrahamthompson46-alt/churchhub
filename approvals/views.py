"""HTTP for approval cases, policy, and delegations. Existing finance URLs stay."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from approvals import selectors
from approvals.forms import ApprovalPolicyForm, CaseNoteForm, DelegationForm
from approvals.services import (
    actor_may_decide,
    create_delegation,
    ensure_case,
    escalate_case,
    get_or_create_policy,
    request_correction,
    revoke_delegation,
    save_required_steps,
)
from church_system.church_scope import require_church
from church_system.flash import flash_error, flash_exception, flash_success
from permissions.checks import (
    can_manage_approval_delegations,
    can_manage_approval_policy,
    can_view_approval_cases,
    permission_required,
)
from permissions.scoping import get_manageable_users
from transactions import selectors as txn_selectors


@login_required
@permission_required("view_approval_cases")
def case_list(request):
    qs = selectors.scoped_cases_qs(request.user, request=request)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "approvals/case_list.html",
        {
            "page_obj": page,
            "cases": page,
            "can_manage_policy": can_manage_approval_policy(request.user),
            "can_delegate": can_manage_approval_delegations(request.user),
        },
    )


@login_required
@permission_required("view_approval_cases")
def case_detail(request, pk):
    case = selectors.case_for_user(request.user, pk, request=request)
    if case is None:
        raise Http404()
    return render(
        request,
        "approvals/case_detail.html",
        {
            "case": case,
            "can_decide": actor_may_decide(request.user, case.transaction),
            "note_form": CaseNoteForm(),
        },
    )


@login_required
@permission_required("manage_approval_policy")
def policy_edit(request):
    church = require_church(request)
    policy = get_or_create_policy(church)
    if request.method == "POST":
        form = ApprovalPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            try:
                save_required_steps(church, request.user, form.cleaned_data["required_steps"])
                flash_success(request, "Journal approval steps saved. Receipt auto-approve is unchanged.")
                return redirect("approvals:policy")
            except PermissionDenied:
                raise
            except ValueError as exc:
                flash_exception(request, str(exc))
        else:
            flash_error(request, "Could not save the step policy.")
    else:
        form = ApprovalPolicyForm(instance=policy)
    return render(request, "approvals/policy.html", {"form": form, "church": church, "policy": policy})


@login_required
@permission_required("manage_approval_delegations")
def delegation_list(request):
    church = require_church(request)
    qs = selectors.scoped_delegations_qs(request.user, request=request)
    people = get_manageable_users(request.user).exclude(pk=request.user.pk)
    form = DelegationForm(queryset=people)
    return render(
        request,
        "approvals/delegations.html",
        {"delegations": qs, "form": form, "church": church},
    )


@login_required
@require_POST
@permission_required("manage_approval_delegations")
def delegation_create(request):
    church = require_church(request)
    people = get_manageable_users(request.user).exclude(pk=request.user.pk)
    form = DelegationForm(request.POST, queryset=people)
    if form.is_valid():
        try:
            create_delegation(
                grantor=request.user,
                grantee=form.cleaned_data["grantee"],
                church=church,
                valid_from=form.cleaned_data["valid_from"],
                valid_until=form.cleaned_data["valid_until"],
                max_amount=form.cleaned_data.get("max_amount"),
            )
            flash_success(request, "Delegation saved.")
        except (PermissionDenied, ValueError) as exc:
            if isinstance(exc, PermissionDenied):
                raise
            flash_exception(request, str(exc))
    else:
        flash_error(request, "Could not create the delegation.")
    return redirect("approvals:delegations")


@login_required
@require_POST
@permission_required("manage_approval_delegations")
def delegation_revoke(request, pk):
    row = selectors.scoped_delegations_qs(request.user, request=request).filter(pk=pk).first()
    if row is None:
        raise Http404()
    revoke_delegation(row, request.user)
    flash_success(request, "Delegation revoked.")
    return redirect("approvals:delegations")


@login_required
@require_POST
def case_correct(request, pk):
    txn = txn_selectors.transaction_for_request(request, pk)
    form = CaseNoteForm(request.POST)
    if not form.is_valid():
        flash_error(request, "A correction note is required.")
        return redirect("transactions:pending_approvals")
    try:
        ensure_case(txn)
        request_correction(txn, request.user, note=form.cleaned_data["note"])
        flash_success(request, f"{txn.reference} remains pending; correction was requested.")
    except PermissionDenied:
        raise
    except ValueError as exc:
        flash_exception(request, str(exc))
    return redirect("transactions:pending_approvals")


@login_required
@require_POST
def case_escalate(request, pk):
    txn = txn_selectors.transaction_for_request(request, pk)
    form = CaseNoteForm(request.POST)
    if not form.is_valid():
        flash_error(request, "An escalation reason is required.")
        return redirect("transactions:pending_approvals")
    try:
        ensure_case(txn)
        escalate_case(txn, request.user, reason=form.cleaned_data["note"])
        flash_success(request, f"{txn.reference} was escalated and is still pending (not auto-approved).")
    except PermissionDenied:
        raise
    except ValueError as exc:
        flash_exception(request, str(exc))
    return redirect("transactions:pending_approvals")
