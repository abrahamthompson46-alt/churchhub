# transactions/views.py

import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from permissions.checks import (
    can_approve_transactions,
    can_finalize_reconciliation,
    can_lock_periods,
    can_manage_expenses,
    can_manage_finances,
    can_manage_receipts,
    can_manage_reconciliation,
    can_manage_working_day,
    can_reject_transactions,
    can_unlock_periods,
    can_void_transactions,
    can_view_audit_log,
    can_view_pending_approvals,
    can_view_reconciliation,
    can_view_transactions,
)
from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_error, flash_exception, flash_success, flash_warning
from transactions.forms import (
    BankReconciliationForm,
    ClassicReceiptForm,
    ExpenseForm,
    PeriodLockForm,
    ReceiptForm,
    TreasuryApprovalPolicyForm,
    VoidTransactionForm,
    WorkingDayCloseForm,
    WorkingDayOpenForm,
)
from transactions.idempotency import (
    IdempotencyReplay,
    MissingIdempotencyKey,
    claim_financial_idempotency,
    complete_financial_idempotency,
)
from transactions.reporting import (
    build_statement_rows,
    export_statement_csv,
    export_statement_excel,
    export_statement_pdf,
)
from transactions import selectors
from transactions.services import (
    PeriodLockedError,
    WorkingDayClosedError,
    approve_transaction as svc_approve,
    close_working_day,
    create_bank_reconciliation,
    finalize_bank_reconciliation,
    generate_monthly_cutoff,
    get_active_working_day,
    get_financial_periods,
    get_or_create_treasury_approval_policy,
    get_recent_working_days,
    get_working_day_status,
    lock_financial_period,
    open_working_day,
    record_district_remittance,
    record_expense,
    record_receipt,
    record_receipt_by_category,
    reject_transaction as svc_reject,
    resolve_transaction_date,
    unlock_financial_period,
    update_reconciliation_matches,
    void_transaction,
)


def _finance_required(view_func):
    """Read-oriented finance gate (INV-FIN-01). Must not wrap GL/recon writes."""

    @login_required
    def _wrapped(request, *args, **kwargs):
        if not (
            can_manage_finances(request.user)
            or can_view_transactions(request.user)
            or can_manage_receipts(request.user)
            or can_manage_expenses(request.user)
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _remittance_write_required(view_func):
    """District remittance payment requires manage_finances (INV-FIN-01)."""

    @login_required
    def _wrapped(request, *args, **kwargs):
        if not can_manage_finances(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _reconciliation_view_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not (
            can_view_reconciliation(request.user)
            or can_manage_reconciliation(request.user)
            or can_finalize_reconciliation(request.user)
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


def _reconciliation_manage_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not can_manage_reconciliation(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


@_finance_required
def pending_approvals(request):
    transactions_qs = selectors.pending_transactions_qs(request)
    paginator = Paginator(transactions_qs, 50)
    transactions = paginator.get_page(request.GET.get("page"))
    return render(request, "transactions/pending.html", {
        "transactions": transactions,
        "page_obj": transactions,
        "can_approve": can_approve_transactions(request.user),
    })


@login_required
@require_POST
def approve_transaction_view(request, pk):
    if not can_approve_transactions(request.user):
        raise PermissionDenied
    transaction = selectors.transaction_for_request(request, pk)
    try:
        svc_approve(transaction, request.user)
        flash_success(request, f"{transaction.reference} approved.")
        if transaction.created_by_id and transaction.created_by_id != request.user.id:
            from dashboard.services import notify_user
            notify_user(
                transaction.created_by,
                title="Transaction Approved",
                message=f"{transaction.reference} has been approved.",
                category="FINANCE",
                action_url=f"/transactions/transactions/{transaction.pk}/",
            )
    except ValueError as exc:
        flash_exception(request, str(exc))
    return redirect("transactions:pending_approvals")


@login_required
@require_POST
def reject_transaction_view(request, pk):
    if not can_approve_transactions(request.user):
        raise PermissionDenied
    transaction = selectors.transaction_for_request(request, pk)
    try:
        svc_reject(transaction, request.user)
        flash_success(request, f"{transaction.reference} rejected.")
        if transaction.created_by_id and transaction.created_by_id != request.user.id:
            from dashboard.services import notify_user

            notify_user(
                transaction.created_by,
                title="Transaction Rejected",
                message=f"{transaction.reference} was rejected.",
                category="FINANCE",
                action_url=f"/transactions/transactions/{transaction.pk}/",
            )
    except ValueError as exc:
        flash_exception(request, str(exc))
    return redirect("transactions:pending_approvals")


@login_required
@require_POST
def bulk_approve(request):
    if not can_approve_transactions(request.user):
        raise PermissionDenied
    ids = request.POST.getlist("transaction_ids")
    qs = selectors.pending_transactions_by_ids_qs(request, ids)
    count = 0
    skipped = 0
    notified = set()
    for txn in qs:
        try:
            svc_approve(txn, request.user)
            count += 1
            if txn.created_by_id and txn.created_by_id != request.user.id:
                notified.add(txn.created_by_id)
        except ValueError:
            skipped += 1
    if notified:
        from accounts.models import User
        from dashboard.services import notify_users

        creators = User.objects.filter(pk__in=notified, is_active=True)
        notify_users(
            creators,
            "Transactions approved",
            f"{count} transaction(s) you submitted were approved in a bulk review.",
            category="FINANCE",
            action_url="/transactions/pending/",
        )
    if skipped:
        flash_warning(request, f"{skipped} transaction(s) could not be approved.")
    flash_success(request, f"{count} transaction(s) approved.")
    return redirect("transactions:pending_approvals")


@_finance_required
def transaction_receipt(request, pk):
    """Printable treasurer confirmation / receipt slip for a recorded transaction."""
    transaction = selectors.transaction_for_request(request, pk, detail=True)
    lines = list(transaction.lines.all())
    if transaction.transaction_type == "RECEIPT":
        display_total = transaction.receipt_total
    else:
        cash_bank = [
            abs(line.amount)
            for line in lines
            if line.account.account_type in ("CASH", "BANK")
        ]
        if cash_bank:
            display_total = cash_bank[0]
        else:
            display_total = abs(sum(line.amount for line in lines if line.amount > 0))
    return render(request, "transactions/receipt.html", {
        "transaction": transaction,
        "just_recorded": request.GET.get("new") == "1",
        "display_total": display_total,
    })


@_finance_required
def financial_dashboard(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start = parse_date(start_date) if start_date else None
    end = parse_date(end_date) if end_date else None
    transactions = selectors.approved_statement_transactions_qs(
        request, start_date=start, end_date=end
    )

    rows, total_receipt, total_expense, final_balance = build_statement_rows(transactions)
    export = request.GET.get("export")
    church = get_active_church(request)
    period = f"{start_date or 'start'} to {end_date or 'today'}"

    if export == "csv":
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="financial_statement",
            export_format="csv",
            row_count=len(rows),
            church=church,
            params={"start_date": start_date or "", "end_date": end_date or ""},
        )
        return export_statement_csv(rows)
    if export == "excel":
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="financial_statement",
            export_format="excel",
            row_count=len(rows),
            church=church,
            params={"start_date": start_date or "", "end_date": end_date or ""},
        )
        return export_statement_excel(rows)
    if export == "pdf":
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="financial_statement",
            export_format="pdf",
            row_count=len(rows),
            church=church,
            params={"start_date": start_date or "", "end_date": end_date or ""},
        )
        return export_statement_pdf(rows, church_name=church.name if church else "", period=period)

    paginator = Paginator(rows, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "transactions/financial_dashboard.html", {
        "rows": page_obj,
        "page_obj": page_obj,
        "total_receipt": total_receipt,
        "total_expense": total_expense,
        "final_balance": final_balance,
        "start_date": start_date,
        "end_date": end_date,
        "church": church,
    })


@_finance_required
def record_receipt_view(request):
    if not can_manage_receipts(request.user):
        raise PermissionDenied
    church = require_church(request)
    default_date = resolve_transaction_date(church)
    initial = {"idempotency_key": str(uuid.uuid4()), "date": default_date}
    classic = request.GET.get("classic") == "1" or request.POST.get("classic") == "1"
    form_class = ClassicReceiptForm if classic else ReceiptForm
    form = form_class(request.POST or None, church=church, initial=initial)
    if request.method == "POST" and form.is_valid():
        idem_record = None
        try:
            idem_record = claim_financial_idempotency(
                church,
                request.user,
                "RECEIPT",
                form.cleaned_data.get("idempotency_key"),
            )
            if classic:
                txn = record_receipt(
                    church=church,
                    created_by=request.user,
                    tithe_amount=form.cleaned_data["tithe_amount"],
                    combined_amount=form.cleaned_data["combined_amount"],
                    income_amount=form.cleaned_data["income_amount"],
                    special_offerings=form.get_special_offerings(),
                    payment_account_type=form.cleaned_data["payment_account_type"],
                    description=form.cleaned_data["description"],
                    member=form.cleaned_data.get("member"),
                    date=form.cleaned_data.get("date"),
                )
            else:
                txn = record_receipt_by_category(
                    church=church,
                    created_by=request.user,
                    category=form.cleaned_data["category"],
                    amount=form.cleaned_data["amount"],
                    description=form.cleaned_data["description"],
                    member=form.cleaned_data.get("member"),
                    date=form.cleaned_data.get("date"),
                )
            complete_financial_idempotency(idem_record, txn)
            if txn.approval_status == "APPROVED":
                flash_success(
                    request,
                    f"Receipt {txn.reference} recorded and auto-approved.",
                )
            else:
                flash_success(
                    request,
                    f"Receipt {txn.reference} recorded and pending second approval "
                    f"(amount exceeds auto-approve limit).",
                )
            return redirect(
                f"{reverse('transactions:transaction_confirm', kwargs={'pk': txn.pk})}?new=1"
            )
        except IdempotencyReplay as exc:
            flash_warning(
                request,
                f"Duplicate submission ignored. Existing receipt {exc.existing_transaction.reference}.",
            )
            return redirect(
                f"{reverse('transactions:transaction_confirm', kwargs={'pk': exc.existing_transaction.pk})}?new=1"
            )
        except MissingIdempotencyKey as exc:
            flash_error(request, str(exc))
        except (PeriodLockedError, WorkingDayClosedError, ValueError) as exc:
            flash_exception(request, str(exc))

    category_payload = {}
    if not classic:
        from ledger.services import category_to_dict, get_categories_for_type

        category_payload = {
            str(c.pk): category_to_dict(c)
            for c in get_categories_for_type(church, "RECEIPT")
        }

    return render(
        request,
        "transactions/record_receipt.html",
        {
            "form": form,
            "classic": classic,
            "category_payload": category_payload,
            "business_date": default_date,
        },
    )


@_finance_required
def record_expense_view(request):
    if not can_manage_expenses(request.user):
        raise PermissionDenied
    church = require_church(request)
    default_date = resolve_transaction_date(church)
    initial = {"idempotency_key": str(uuid.uuid4()), "date": default_date}
    form = ExpenseForm(request.POST or None, church=church, initial=initial)
    if request.method == "POST" and form.is_valid():
        idem_record = None
        try:
            idem_record = claim_financial_idempotency(
                church,
                request.user,
                "EXPENSE",
                form.cleaned_data.get("idempotency_key"),
            )
            txn = record_expense(
                church=church,
                created_by=request.user,
                amount=form.cleaned_data["amount"],
                payment_account_type=form.cleaned_data["payment_account_type"],
                description=form.cleaned_data["description"],
                date=form.cleaned_data.get("date"),
                expense_account=form.cleaned_data.get("expense_account"),
            )
            complete_financial_idempotency(idem_record, txn)
            flash_success(request, f"Expense {txn.reference} recorded and pending approval.")
            return redirect(
                f"{reverse('transactions:transaction_confirm', kwargs={'pk': txn.pk})}?new=1"
            )
        except IdempotencyReplay as exc:
            flash_warning(
                request,
                f"Duplicate submission ignored. Existing expense {exc.existing_transaction.reference}.",
            )
            return redirect(
                f"{reverse('transactions:transaction_confirm', kwargs={'pk': exc.existing_transaction.pk})}?new=1"
            )
        except MissingIdempotencyKey as exc:
            flash_error(request, str(exc))
        except (PeriodLockedError, WorkingDayClosedError) as exc:
            flash_exception(request, str(exc))
    return render(request, "transactions/record_expense.html", {"form": form})


@_finance_required
def audit_log(request):
    logs_qs = selectors.audit_logs_qs(request)
    paginator = Paginator(logs_qs, 50)
    logs = paginator.get_page(request.GET.get("page"))
    return render(request, "transactions/audit_log.html", {"logs": logs, "page_obj": logs})


@_remittance_write_required
def record_remittance_view(request):
    """GET: remittance payment form. POST: record district remittance (also used from cut-off)."""
    church = require_church(request)
    month_str = request.POST.get("month") if request.method == "POST" else request.GET.get("month")
    month_date = parse_date(month_str) if month_str else timezone.now().date()
    cutoff = generate_monthly_cutoff(church, month_date)
    from remittance.services import outstanding_district_remittance_parts

    outstanding = outstanding_district_remittance_parts(church)
    amount = outstanding["total"]
    context = {
        "cutoff": cutoff,
        "month_date": month_date,
        "amount": amount,
        "outstanding": outstanding,
        "idempotency_key": f"remit-{church.pk}-{month_date.strftime('%Y-%m')}",
    }

    if request.method != "POST":
        return render(request, "transactions/record_remittance.html", context)

    if amount <= 0:
        flash_warning(request, "No payable amount for this period.")
        return redirect("transactions:record_remittance")
    idem_key = request.POST.get("idempotency_key") or f"remit-{church.pk}-{month_str}"
    try:
        idem_record = claim_financial_idempotency(
            church,
            request.user,
            "REMITTANCE",
            idem_key,
        )
        remit = record_district_remittance(
            church=church,
            created_by=request.user,
            amount=amount,
            month_date=month_date,
            description=f"District remittance for {month_date.strftime('%B %Y')}",
        )
        complete_financial_idempotency(idem_record, remit)
    except IdempotencyReplay as exc:
        flash_warning(
            request,
            f"Remittance already recorded ({exc.existing_transaction.reference}).",
        )
        return redirect("dashboard:cutoff")
    except (MissingIdempotencyKey, ValueError) as exc:
        flash_error(request, str(exc))
        return redirect("transactions:record_remittance")
    flash_success(
        request,
        f"District remittance of {amount} recorded and pending approval.",
    )
    return redirect("dashboard:cutoff")


@_finance_required
def budget_report(request):
    """Legacy route — consolidated into the budgets planning hub."""
    year = request.GET.get("year", timezone.now().year)
    level = request.GET.get("level", "CHURCH")
    return redirect(f"/budgets/?year={year}&level={level}")


@_finance_required
def transaction_list(request):
    church = get_active_church(request)
    business_date = resolve_transaction_date(church) if church else timezone.localdate()

    date_from = parse_date(request.GET.get("date_from") or "") or business_date
    date_to = parse_date(request.GET.get("date_to") or "") or business_date
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    status = request.GET.get("status", "")
    txn_type = request.GET.get("type", "")
    show_voided = request.GET.get("voided", "")

    transactions = selectors.transaction_list_qs(
        request,
        date_from=date_from,
        date_to=date_to,
        status=status,
        txn_type=txn_type,
        include_voided=(show_voided == "1"),
    )

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        from reports.exporters import export_table_csv, export_table_excel
        from reports.services import audit_export

        headers = ["Reference", "Date", "Type", "Status", "Description", "Amount", "Created by", "Voided"]
        rows = []
        for t in transactions[:5000]:
            rows.append([
                t.reference or "",
                t.date.isoformat() if t.date else "",
                t.get_transaction_type_display(),
                t.get_approval_status_display(),
                t.description or "",
                f"{abs(t.receipt_total):.2f}",
                (t.created_by.get_full_name() or t.created_by.username) if t.created_by else "",
                "Yes" if t.is_voided else "No",
            ])
        title = f"Transactions {date_from} to {date_to}"
        audit_export(
            user=request.user,
            report_key="transactions_list",
            export_format=export_fmt,
            row_count=len(rows),
            church=church,
            params={
                "status": status,
                "type": txn_type,
                "date_from": date_from.isoformat() if date_from else "",
                "date_to": date_to.isoformat() if date_to else "",
            },
        )
        if export_fmt == "csv":
            return export_table_csv(headers, rows, "transactions.csv")
        return export_table_excel(headers, rows, "transactions.xlsx", title)

    paginator = Paginator(transactions, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    query = request.GET.copy()
    query.pop("page", None)
    query.pop("export", None)

    return render(request, "transactions/transaction_list.html", {
        "transactions": page_obj,
        "page_obj": page_obj,
        "status_filter": status,
        "type_filter": txn_type,
        "date_from": date_from,
        "date_to": date_to,
        "business_date": business_date,
        "show_voided": show_voided == "1",
        "filter_query": query.urlencode(),
        "can_void": can_void_transactions(request.user),
    })


@_finance_required
def transaction_detail(request, pk):
    transaction = selectors.transaction_for_request(request, pk, detail=True)
    void_form = VoidTransactionForm()
    can_void = (
        can_void_transactions(request.user)
        and transaction.approval_status == "APPROVED"
        and not transaction.is_voided
        and not transaction.reversal_of_id
    )
    return render(request, "transactions/transaction_detail.html", {
        "transaction": transaction,
        "void_form": void_form,
        "can_void": can_void,
    })


@login_required
@require_POST
def void_transaction_view(request, pk):
    if not can_void_transactions(request.user):
        raise PermissionDenied
    transaction = selectors.transaction_for_request(request, pk)
    form = VoidTransactionForm(request.POST)
    reason = form.data.get("reason", "") if form.is_valid() else request.POST.get("reason", "")
    try:
        void_transaction(transaction, request.user, reason=reason)
        flash_success(
            request,
            f"{transaction.reference} reversed. It is excluded from books and reports.",
        )
    except (ValueError, PeriodLockedError, WorkingDayClosedError) as exc:
        flash_exception(request, str(exc))
    return redirect("transactions:transaction_detail", pk=pk)


@_finance_required
def period_list(request):
    church = require_church(request)
    year = int(request.GET.get("year", timezone.now().year))
    months = get_financial_periods(church, year)
    lock_form = PeriodLockForm(initial={"year": year, "month": timezone.now().month})
    working_status = get_working_day_status(church)
    active_day = get_active_working_day(church)
    open_form = WorkingDayOpenForm(initial={"date": timezone.localdate()})
    close_form = WorkingDayCloseForm()
    policy = get_or_create_treasury_approval_policy(church)
    approval_form = TreasuryApprovalPolicyForm(instance=policy)
    return render(request, "transactions/period_list.html", {
        "months": months,
        "year": year,
        "church": church,
        "lock_form": lock_form,
        "can_lock": can_lock_periods(request.user),
        "can_unlock": can_unlock_periods(request.user),
        "working_status": working_status,
        "active_working_day": active_day,
        "open_form": open_form,
        "close_form": close_form,
        "recent_working_days": get_recent_working_days(church),
        "can_manage_working_day": can_manage_working_day(request.user),
        "approval_form": approval_form,
        "can_edit_approval_policy": can_manage_finances(request.user),
    })


@login_required
@require_POST
def treasury_approval_policy_save(request):
    if not can_manage_finances(request.user):
        raise PermissionDenied
    church = require_church(request)
    policy = get_or_create_treasury_approval_policy(church)
    form = TreasuryApprovalPolicyForm(request.POST, instance=policy)
    if form.is_valid():
        form.save()
        flash_success(request, "Receipt auto-approval policy saved.")
    else:
        flash_error(request, "Could not save approval policy. Check the amounts.")
    return redirect(reverse("transactions:period_list") + "#receipt-approval")


@login_required
@require_POST
def working_day_open(request):
    if not can_manage_working_day(request.user):
        raise PermissionDenied
    church = require_church(request)
    form = WorkingDayOpenForm(request.POST)
    if form.is_valid():
        try:
            day = open_working_day(
                church,
                form.cleaned_data["date"],
                request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
            flash_success(request, f"Working day opened for {day.date:%d %b %Y}.")
        except (ValueError, PeriodLockedError) as exc:
            flash_exception(request, str(exc))
    else:
        flash_exception(request, "Invalid working day date.")
    return redirect("transactions:period_list")


@login_required
@require_POST
def working_day_close(request):
    if not can_manage_working_day(request.user):
        raise PermissionDenied
    church = require_church(request)
    form = WorkingDayCloseForm(request.POST)
    if form.is_valid():
        try:
            day = close_working_day(church, request.user, notes=form.cleaned_data.get("notes", ""))
            flash_success(request, f"Working day closed for {day.date:%d %b %Y}.")
        except ValueError as exc:
            flash_exception(request, str(exc))
    else:
        flash_exception(request, "Could not close working day.")
    return redirect("transactions:period_list")


@login_required
@require_POST
def period_lock(request):
    if not can_lock_periods(request.user):
        raise PermissionDenied
    church = require_church(request)
    form = PeriodLockForm(request.POST)
    if form.is_valid():
        try:
            lock_financial_period(
                church,
                form.cleaned_data["year"],
                form.cleaned_data["month"],
                request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
            flash_success(request, "Financial period locked.")
        except Exception as exc:
            flash_exception(request, str(exc))
    else:
        flash_exception(request, "Invalid period.")
    return redirect(f"{reverse('transactions:period_list')}?year={request.POST.get('year', timezone.now().year)}")


@login_required
@require_POST
def period_unlock(request):
    if not can_unlock_periods(request.user):
        raise PermissionDenied
    church = require_church(request)
    year = int(request.POST.get("year"))
    month = int(request.POST.get("month"))
    try:
        unlock_financial_period(church, year, month, request.user)
        flash_success(request, "Financial period unlocked.")
    except ValueError as exc:
        flash_exception(request, str(exc))
    return redirect(f"{reverse('transactions:period_list')}?year={year}")


@_reconciliation_view_required
def reconciliation_list(request):
    reconciliations_qs = selectors.reconciliations_qs(request)
    paginator = Paginator(reconciliations_qs, 25)
    reconciliations = paginator.get_page(request.GET.get("page"))
    return render(request, "transactions/reconciliation_list.html", {
        "reconciliations": reconciliations,
        "page_obj": reconciliations,
    })


@_reconciliation_manage_required
def reconciliation_create(request):
    church = require_church(request)
    form = BankReconciliationForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        try:
            recon = create_bank_reconciliation(
                church=church,
                bank_account=form.cleaned_data["bank_account"],
                statement_date=form.cleaned_data["statement_date"],
                statement_balance=form.cleaned_data["statement_balance"],
                user=request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
            flash_success(request, "Bank reconciliation started.")
            return redirect("transactions:reconciliation_detail", pk=recon.pk)
        except ValueError as exc:
            flash_exception(request, str(exc))
    return render(request, "transactions/reconciliation_form.html", {"form": form})


@_reconciliation_view_required
def reconciliation_detail(request, pk):
    recon = selectors.reconciliation_for_request(request, pk)
    items = selectors.reconciliation_items(recon)

    if request.method == "POST" and not recon.is_reconciled:
        action = request.POST.get("action")
        if action == "match":
            if not can_manage_reconciliation(request.user):
                raise PermissionDenied
            matched_ids = request.POST.getlist("matched_lines")
            try:
                update_reconciliation_matches(recon, matched_ids, request.user)
                flash_success(request, "Matches updated.")
            except ValueError as exc:
                flash_exception(request, str(exc))
            return redirect("transactions:reconciliation_detail", pk=pk)
        if action == "finalize" and can_finalize_reconciliation(request.user):
            try:
                finalize_bank_reconciliation(recon, request.user)
                flash_success(request, "Reconciliation finalized.")
            except ValueError as exc:
                flash_exception(request, str(exc))
            return redirect("transactions:reconciliation_detail", pk=pk)

    matched_total = sum(
        item.transaction_line.amount for item in items if item.is_matched
    )
    difference = recon.statement_balance - matched_total

    return render(request, "transactions/reconciliation_detail.html", {
        "reconciliation": recon,
        "items": items,
        "matched_total": matched_total,
        "difference": difference,
        "can_finalize": can_finalize_reconciliation(request.user) and not recon.is_reconciled,
        "can_match": can_manage_reconciliation(request.user) and not recon.is_reconciled,
    })
