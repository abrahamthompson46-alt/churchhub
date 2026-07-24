"""Remittance policy and welfare views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_exception, flash_success
from reports.exporters import export_table_csv, export_table_excel, export_table_pdf
from permissions.checks import (
    can_approve_welfare,
    can_disburse_welfare,
    can_manage_finances,
    can_manage_remittance_policy,
    can_manage_settlements,
    can_manage_welfare_cases,
    can_view_welfare,
)
from sitecontrol.checks import require_feature
from remittance import repositories as repo
from remittance import selectors
from remittance.forms import (
    RemittancePolicyForm,
    SettlementDraftForm,
    WelfareApproveForm,
    WelfareCaseAttachmentForm,
    WelfareCaseForm,
    WelfareContributionForm,
    WelfareDisburseForm,
    WelfareRejectForm,
    WelfareReviewForm,
)
from remittance.models import RemittancePolicy
from remittance.services import (
    RemittancePolicyError,
    approve_welfare_case,
    create_settlement_draft,
    create_welfare_case,
    disburse_welfare_case,
    ensure_hierarchy_settlement_policies,
    get_fund_balances,
    get_unit_choices,
    post_settlement_batch,
    reject_welfare_case,
    resolve_unit_label,
    save_remittance_policy,
)
from remittance.welfare_services import (
    cancel_welfare_case,
    build_member_welfare_statement,
    can_view_member_welfare,
    church_welfare_dashboard,
    member_welfare_cases,
    member_welfare_contributions,
    member_welfare_summary,
    record_manual_welfare_contribution,
    send_welfare_case_to_review,
    welfare_module_enabled,
    welfare_year_choices,
)


def _policy_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not can_manage_remittance_policy(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _finance_or_policy(view_func):
    @login_required
    @require_feature("remittance")
    def _wrapped(request, *args, **kwargs):
        if not (can_manage_finances(request.user) or can_manage_remittance_policy(request.user)):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


@_finance_or_policy
def policy_index(request):
    church = require_church(request)
    unit_type = request.GET.get("unit_type", "CHURCH")
    unit_id = request.GET.get("unit_id", str(church.pk))

    if unit_type == "CHURCH":
        unit_id = str(church.pk)

    unit_choices = get_unit_choices(unit_type, church=church, user=request.user)
    allowed_ids = {choice_id for choice_id, _label in unit_choices}
    if unit_id and str(unit_id) not in allowed_ids:
        from remittance.services import log_remittance_scope_violation

        log_remittance_scope_violation(
            request.user,
            unit_type,
            unit_id,
            reason="policy_index rejected out-of-scope unit picker value",
            church=church,
        )
        unit_id = next(iter(allowed_ids), str(church.pk) if unit_type == "CHURCH" else "")

    policies = selectors.policies_for_unit(unit_type, unit_id)

    fund_balances = get_fund_balances(church) if unit_type == "CHURCH" else []

    return render(request, "remittance/index.html", {
        "policies": policies,
        "fund_balances": fund_balances,
        "unit_type": unit_type,
        "unit_id": unit_id,
        "unit_label": resolve_unit_label(unit_type, unit_id) if unit_id else "",
        "unit_type_choices": RemittancePolicy.UNIT_TYPES,
        "unit_choices": unit_choices,
        "can_edit": can_manage_remittance_policy(request.user),
        "active_church": church,
        "can_manage_settlements": can_manage_settlements(request.user),
        "can_manage_finances": can_manage_finances(request.user),
        "can_manage_remittance_policy": can_manage_remittance_policy(request.user),
        "can_view_welfare": can_view_welfare(request.user),
        "can_manage_welfare_cases": can_manage_welfare_cases(request.user),
    })


@_policy_required
def policy_create(request):
    church = get_active_church(request)
    initial = {
        "unit_type": request.GET.get("unit_type", "CHURCH"),
        "unit_id": request.GET.get("unit_id", str(church.pk) if church else ""),
        "is_active": True,
    }
    form = RemittancePolicyForm(request.POST or None, initial=initial, church=church, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            save_remittance_policy(request.POST, request.user, church=church)
            flash_success(request, "Remittance policy saved.")
            return redirect(
                "remittance:index"
                f"?unit_type={form.cleaned_data['unit_type']}&unit_id={form.cleaned_data['unit_id']}"
            )
        except RemittancePolicyError as exc:
            flash_exception(request, exc)
    return render(request, "remittance/policy_form.html", {
        "form": form,
        "title": "Add Remittance Policy",
    })


@_policy_required
def policy_edit(request, pk):
    policy = selectors.policy_by_pk(pk)
    church = get_active_church(request)
    from remittance.services import user_can_edit_remittance_policy

    if not user_can_edit_remittance_policy(request.user, policy, active_church=church):
        raise PermissionDenied
    form = RemittancePolicyForm(request.POST or None, instance=policy, church=church, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            save_remittance_policy(request.POST, request.user, policy=policy, church=church)
            flash_success(request, "Remittance policy updated.")
            return redirect(
                "remittance:index"
                f"?unit_type={policy.unit_type}&unit_id={policy.unit_id}"
            )
        except RemittancePolicyError as exc:
            flash_exception(request, exc)
    return render(request, "remittance/policy_form.html", {
        "form": form,
        "title": "Edit Remittance Policy",
        "object": policy,
    })


@_finance_or_policy
def settlement_list(request):
    church = require_church(request)
    ensure_hierarchy_settlement_policies(church, user=request.user)

    batches = selectors.settlements_for_church(church)

    draft_form = SettlementDraftForm(
        request.POST or None,
        initial={
            "period_start": timezone.now().date().replace(day=1),
            "period_end": timezone.now().date(),
        },
    )

    if request.method == "POST" and request.POST.get("action") == "create_draft":
        if not can_manage_finances(request.user):
            raise PermissionDenied
        draft_form = SettlementDraftForm(request.POST)
        if draft_form.is_valid():
            try:
                create_settlement_draft(
                    from_unit_type="CHURCH",
                    from_unit_id=church.pk,
                    offering_type=draft_form.cleaned_data["offering_type"],
                    period_start=draft_form.cleaned_data["period_start"],
                    period_end=draft_form.cleaned_data["period_end"],
                    user=request.user,
                    church=church,
                )
                flash_success(request, "Settlement draft created.")
                return redirect("remittance:settlements")
            except RemittancePolicyError as exc:
                flash_exception(request, exc)

    return render(request, "remittance/settlements.html", {
        "batches": batches,
        "active_church": church,
        "can_edit": can_manage_finances(request.user),
        "draft_form": draft_form,
    })


@_finance_or_policy
def settlement_post(request, pk):
    if not can_manage_finances(request.user):
        raise PermissionDenied
    batch = selectors.settlement_by_pk(pk)
    church = require_church(request)
    if batch.from_unit_type != "CHURCH" or str(batch.from_unit_id) != str(church.pk):
        raise PermissionDenied
    if request.method == "POST":
        try:
            post_settlement_batch(batch, request.user)
            flash_success(request, "Settlement batch posted.")
        except RemittancePolicyError as exc:
            flash_exception(request, exc)
    return redirect("remittance:settlements")


@_finance_or_policy
def welfare_index(request):
    church = require_church(request)
    year = int(request.GET.get("year", timezone.now().year))
    dashboard = church_welfare_dashboard(church, year=year)

    contributions = selectors.welfare_contributions_for_year(church, year)
    cases = selectors.welfare_cases_for_year(church, year)
    case_form = WelfareCaseForm(church=church)
    contribution_form = WelfareContributionForm(church=church)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_case":
            if not can_manage_welfare_cases(request.user):
                raise PermissionDenied
            case_form = WelfareCaseForm(request.POST, church=church)
            if case_form.is_valid():
                case = create_welfare_case(
                    church=church,
                    member=case_form.cleaned_data["member_obj"],
                    amount_requested=case_form.cleaned_data["amount_requested"],
                    reason=case_form.cleaned_data["reason"],
                    user=request.user,
                    assistance_type=case_form.cleaned_data["assistance_type"],
                    priority=case_form.cleaned_data["priority"],
                )
                flash_success(request, f"Case {case.case_number} submitted.")
                return redirect("remittance:welfare")
        elif action == "record_contribution":
            if not can_manage_welfare_cases(request.user):
                raise PermissionDenied
            contribution_form = WelfareContributionForm(request.POST, church=church)
            if contribution_form.is_valid():
                try:
                    record_manual_welfare_contribution(
                        church=church,
                        member=contribution_form.cleaned_data["member_obj"],
                        amount=contribution_form.cleaned_data["amount"],
                        user=request.user,
                        contribution_date=contribution_form.cleaned_data["contribution_date"],
                        notes=contribution_form.cleaned_data.get("notes", ""),
                        payment_account_type=contribution_form.cleaned_data["payment_account_type"],
                    )
                    flash_success(request, "Welfare contribution recorded.")
                    return redirect("remittance:welfare")
                except RemittancePolicyError as exc:
                    flash_exception(request, exc)

    return render(request, "remittance/welfare.html", {
        "contributions": contributions,
        "cases": cases,
        "dashboard": dashboard,
        "year": year,
        "year_choices": welfare_year_choices(),
        "active_church": church,
        "case_form": case_form,
        "contribution_form": contribution_form,
        "can_manage": can_manage_welfare_cases(request.user),
        "can_approve": can_approve_welfare(request.user),
    })


@_finance_or_policy
def welfare_case_detail(request, pk):
    church = require_church(request)
    case = selectors.welfare_case_for_church(church, pk, detail=True)
    attachment_form = WelfareCaseAttachmentForm()
    ledger_entries = selectors.welfare_case_ledger_entries(case)

    if request.method == "POST" and request.POST.get("action") == "upload_attachment":
        if not can_manage_welfare_cases(request.user):
            raise PermissionDenied
        attachment_form = WelfareCaseAttachmentForm(request.POST, request.FILES)
        if attachment_form.is_valid():
            repo.create_case_attachment(
                case=case,
                label=attachment_form.cleaned_data.get("label", ""),
                file=attachment_form.cleaned_data["file"],
                uploaded_by=request.user,
            )
            flash_success(request, "Attachment uploaded.")
            return redirect("remittance:welfare_case_detail", pk=case.pk)

    return render(request, "remittance/welfare_case_detail.html", {
        "case": case,
        "ledger_entries": ledger_entries,
        "attachments": selectors.welfare_case_attachments(case),
        "attachment_form": attachment_form,
        "can_manage": can_manage_welfare_cases(request.user),
        "can_approve": can_approve_welfare(request.user),
        "active_church": church,
    })


@_finance_or_policy
def welfare_case_action(request, pk):
    church = require_church(request)
    case = selectors.welfare_case_for_church(church, pk)
    action = request.POST.get("action")

    try:
        if action == "review":
            if not can_manage_welfare_cases(request.user):
                raise PermissionDenied
            form = WelfareReviewForm(request.POST)
            if form.is_valid():
                send_welfare_case_to_review(case, request.user, review_notes=form.cleaned_data.get("review_notes", ""))
                flash_success(request, "Case sent for review.")
        elif action == "approve":
            if not can_approve_welfare(request.user):
                raise PermissionDenied
            form = WelfareApproveForm(request.POST)
            if form.is_valid():
                approve_welfare_case(case, request.user, amount_approved=form.cleaned_data.get("amount_approved"))
                flash_success(request, "Welfare case approved.")
        elif action == "reject":
            if not can_approve_welfare(request.user):
                raise PermissionDenied
            form = WelfareRejectForm(request.POST)
            if form.is_valid():
                reject_welfare_case(case, request.user, rejection_reason=form.cleaned_data.get("rejection_reason", ""))
                flash_success(request, "Welfare case rejected.")
        elif action == "cancel":
            if not can_manage_welfare_cases(request.user):
                raise PermissionDenied
            cancel_welfare_case(case, request.user)
            flash_success(request, "Welfare case cancelled.")
        elif action == "disburse":
            if not can_disburse_welfare(request.user):
                raise PermissionDenied
            form = WelfareDisburseForm(request.POST)
            if form.is_valid():
                disburse_welfare_case(
                    case,
                    request.user,
                    payment_account_type=form.cleaned_data["payment_account_type"],
                )
                flash_success(request, "Welfare assistance disbursed.")
    except RemittancePolicyError as exc:
        flash_exception(request, exc)

    next_url = request.POST.get("next") or request.GET.get("next")
    from dashboard.utils import safe_internal_redirect

    safe_next = safe_internal_redirect(next_url, None)
    if safe_next:
        return redirect(safe_next)
    return redirect("remittance:welfare_case_detail", pk=case.pk)


@login_required
def member_welfare_statement(request, member_id):
    member = selectors.member_for_request(request, member_id)
    if not welfare_module_enabled(member.church, request.user):
        raise PermissionDenied
    if not can_view_member_welfare(request.user, member):
        raise PermissionDenied

    from datetime import datetime

    start_date = end_date = None
    start_raw = request.GET.get("start_date", "").strip()
    end_raw = request.GET.get("end_date", "").strip()
    try:
        if start_raw:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        if end_raw:
            end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except ValueError:
        start_date = end_date = None

    year = request.GET.get("year")
    if year and not start_date and not end_date:
        year = int(year)
    else:
        year = None

    statement = build_member_welfare_statement(member, start_date=start_date, end_date=end_date)
    summary = member_welfare_summary(member, year=year, start_date=start_date, end_date=end_date)
    cases = member_welfare_cases(member)
    contributions = member_welfare_contributions(member, year=year)

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
        slug = f"welfare-{member.pk}"
        if start_date:
            slug += f"-{start_date}"
        title = f"Welfare Statement — {member.full_name}"
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="welfare_statement",
            export_format=export_fmt,
            row_count=len(rows),
            church=member.church,
            params={
                "member_id": str(member.pk),
                "start_date": str(start_date) if start_date else "",
                "end_date": str(end_date) if end_date else "",
            },
        )
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        if export_fmt == "excel":
            return export_table_excel(headers, rows, f"{slug}.xlsx", "Welfare Statement")
        return export_table_pdf(headers, rows, "Welfare Statement", member.full_name, f"{slug}.pdf")

    return render(request, "remittance/member_welfare.html", {
        "member": member,
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "year_choices": welfare_year_choices(),
        "summary": summary,
        "statement": statement,
        "cases": cases,
        "contributions": contributions,
        "breadcrumbs": [
            {"label": "Welfare", "url": "/remittance/welfare/"},
            {"label": member.full_name},
        ],
    })
