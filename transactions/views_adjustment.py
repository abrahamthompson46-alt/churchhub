"""Adjustment journal views — church-scoped correction entries."""

import uuid
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from church_system.church_scope import require_church
from church_system.flash import flash_exception, flash_success
from permissions.checks import can_create_adjustment_journals, permission_required
from sitecontrol.checks import require_feature
from transactions.adjustment_forms import AdjustmentJournalForm, AdjustmentLineFormSet
from transactions.adjustment_services import build_adjustment_draft, post_adjustment_journal
from transactions.idempotency import IdempotencyReplay, MissingIdempotencyKey
from transactions.services import PeriodLockedError, WorkingDayClosedError

SESSION_DRAFT_KEY = "adjustment_journal_draft"


def adjustment_create_required(view_func):
    @login_required
    @require_feature("ledger")
    @permission_required("create_adjustment_journals")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def _lines_from_formset(formset):
    lines = []
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("empty"):
            continue
        account = form.cleaned_data["account"]
        lines.append(
            {
                "account_id": str(account.pk),
                "account_name": account.name,
                "side": form.cleaned_data["side"],
                "amount": form.cleaned_data["amount"],
            }
        )
    return lines


@adjustment_create_required
@require_http_methods(["GET", "POST"])
def adjustment_create(request):
    church = require_church(request)
    line_formset = AdjustmentLineFormSet(
        request.POST or None,
        prefix="lines",
        form_kwargs={"church": church},
    )
    header_form = AdjustmentJournalForm(
        request.POST or None,
        church=church,
        prefix="hdr",
    )

    if request.method == "POST":
        if header_form.is_valid() and line_formset.is_valid():
            try:
                draft = build_adjustment_draft(
                    church,
                    narration=header_form.cleaned_data["narration"],
                    entry_date=header_form.cleaned_data.get("date"),
                    lines=_lines_from_formset(line_formset),
                )
                request.session[SESSION_DRAFT_KEY] = draft
                return redirect("transactions:adjustment_confirm")
            except (ValueError, PeriodLockedError, WorkingDayClosedError) as exc:
                flash_exception(request, exc, title="Adjustment could not be prepared")

    return render(
        request,
        "transactions/adjustment_entry.html",
        {
            "header_form": header_form,
            "line_formset": line_formset,
            "business_date": header_form.fields["date"].initial
            or header_form.cleaned_data.get("date")
            if header_form.is_bound and header_form.is_valid()
            else header_form.fields["date"].initial,
            "breadcrumbs": [
                {"label": "Ledger", "url": reverse("ledger:index")},
                {"label": "Adjustment journal"},
            ],
        },
    )


@adjustment_create_required
@require_http_methods(["GET", "POST"])
def adjustment_confirm(request):
    church = require_church(request)
    draft = request.session.get(SESSION_DRAFT_KEY)
    if not draft:
        flash_exception(
            request, "No adjustment to confirm. Please start again.", title="Session expired"
        )
        return redirect("transactions:adjustment_create")

    if request.method == "POST":
        if request.POST.get("action") == "back":
            del request.session[SESSION_DRAFT_KEY]
            return redirect("transactions:adjustment_create")

        if not can_create_adjustment_journals(request.user):
            raise PermissionDenied

        idem_key = request.POST.get("idempotency_key") or str(uuid.uuid4())
        try:
            trx = post_adjustment_journal(
                church, request.user, draft, idempotency_key=idem_key
            )
            request.session.pop(SESSION_DRAFT_KEY, None)
            flash_success(
                request,
                f"{trx.reference} recorded and pending checker approval.",
                title="Adjustment journal saved",
            )
            return redirect("transactions:pending_approvals")
        except IdempotencyReplay as replay:
            request.session.pop(SESSION_DRAFT_KEY, None)
            flash_success(
                request,
                f"{replay.existing_transaction.reference} was already recorded.",
                title="Duplicate prevented",
            )
            return redirect("transactions:pending_approvals")
        except (ValueError, PeriodLockedError, WorkingDayClosedError, MissingIdempotencyKey) as exc:
            flash_exception(request, exc, title="Adjustment could not be saved")

    return render(
        request,
        "transactions/adjustment_confirm.html",
        {
            "draft": draft,
            "idempotency_key": str(uuid.uuid4()),
            "breadcrumbs": [
                {"label": "Ledger", "url": reverse("ledger:index")},
                {
                    "label": "Adjustment journal",
                    "url": reverse("transactions:adjustment_create"),
                },
                {"label": "Confirm"},
            ],
        },
    )