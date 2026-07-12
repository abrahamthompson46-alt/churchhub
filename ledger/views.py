"""Ledger views — category-driven GL posting with feature gate."""

import uuid
from datetime import datetime
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from church_system.church_scope import require_church
from church_system.flash import flash_exception, flash_success
from ledger.forms import LedgerCategoryEditForm, LedgerEntryForm
from ledger.models import LedgerCategory
from ledger.services import (
    build_entry_draft,
    category_to_dict,
    export_ledger_entries_table,
    get_all_categories,
    get_categories_for_type,
    get_categories_grouped,
    get_category_gl_totals,
    get_ledger_entries,
    get_ledger_summary,
    paginate_ledger_entries,
    post_ledger_entry,
    update_ledger_category,
)
from members.models import Member
from permissions.checks import permission_required
from reports.exporters import export_table_csv, export_table_excel
from sitecontrol.checks import require_feature
from transactions.idempotency import IdempotencyReplay, MissingIdempotencyKey
from transactions.models import Transaction
from transactions.services import PeriodLockedError, WorkingDayClosedError

SESSION_DRAFT_KEY = "ledger_entry_draft"


def ledger_finance_required(view_func):
    """Finance permission + ledger feature gate."""

    @login_required
    @require_feature("ledger")
    @permission_required("manage_finances")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def _entry_initial(church, request):
    """Pre-fill entry form when linked from a category."""
    cat_id = request.GET.get("category")
    if not cat_id:
        return {}
    category = LedgerCategory.objects.filter(
        pk=cat_id,
        church=church,
        is_active=True,
    ).select_related("default_debit_account", "default_credit_account").first()
    if not category:
        return {}
    return {
        "transaction_type": category.transaction_type,
        "category": category,
        "narration": category.default_narration,
    }


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@ledger_finance_required
def index(request):
    church = require_church(request)
    summary = get_ledger_summary(church)
    recent = list(get_ledger_entries(church)[:8])
    return render(request, "ledger/index.html", {
        "summary": summary,
        "recent_entries": recent,
    })


@ledger_finance_required
def category_list(request):
    church = require_church(request)
    txn_type = request.GET.get("type", "")
    if txn_type and txn_type not in dict(LedgerCategory.TRANSACTION_TYPES):
        txn_type = ""
    if txn_type:
        categories = get_all_categories(church, transaction_type=txn_type)
        sections = None
    else:
        categories = None
        sections = get_categories_grouped(church)
    return render(request, "ledger/categories.html", {
        "sections": sections,
        "categories": categories,
        "type_filter": txn_type,
        "type_choices": LedgerCategory.TRANSACTION_TYPES,
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "Posting Categories"},
        ],
    })


@ledger_finance_required
def category_detail(request, pk):
    church = require_church(request)
    category = get_object_or_404(
        LedgerCategory.objects.select_related(
            "default_debit_account",
            "default_credit_account",
        ),
        pk=pk,
        church=church,
    )
    recent_entries = Transaction.objects.filter(
        church=church,
        ledger_category=category,
    ).select_related("ledger_category").prefetch_related("lines__account").order_by(
        "-date", "-created_at"
    )[:8]
    entry_url = f"{reverse('ledger:entry')}?category={category.pk}"
    return render(request, "ledger/category_detail.html", {
        "category": category,
        "recent_entries": recent_entries,
        "entry_url": entry_url,
        "sample_draft": {
            "debit_account_name": category.default_debit_account.name,
            "credit_account_name": category.default_credit_account.name,
            "amount": "100.00",
        },
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "Categories", "url": reverse("ledger:categories")},
            {"label": category.name},
        ],
    })


@ledger_finance_required
@require_http_methods(["GET", "POST"])
def category_edit(request, pk):
    church = require_church(request)
    category = get_object_or_404(LedgerCategory, pk=pk, church=church)
    if request.method == "POST":
        form = LedgerCategoryEditForm(request.POST, church=church, instance=category)
        if form.is_valid():
            try:
                update_ledger_category(
                    category,
                    request.user,
                    name=form.cleaned_data["name"],
                    default_narration=form.cleaned_data.get("default_narration", ""),
                    requires_member=form.cleaned_data["requires_member"],
                    is_active=form.cleaned_data["is_active"],
                    sort_order=form.cleaned_data["sort_order"],
                    default_debit_account=form.cleaned_data["default_debit_account"],
                    default_credit_account=form.cleaned_data["default_credit_account"],
                )
                flash_success(request, f"Category {category.code} updated.", title="Category saved")
                return redirect("ledger:category_detail", pk=category.pk)
            except Exception as exc:
                flash_exception(request, exc, title="Category could not be saved")
    else:
        form = LedgerCategoryEditForm(church=church, instance=category)
    return render(request, "ledger/category_edit.html", {
        "form": form,
        "category": category,
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "Categories", "url": reverse("ledger:categories")},
            {"label": category.name, "url": reverse("ledger:category_detail", args=[category.pk])},
            {"label": "Edit"},
        ],
    })


@ledger_finance_required
def entry_list(request):
    church = require_church(request)
    status = request.GET.get("status", "")
    txn_type = request.GET.get("type", "")
    date_from = _parse_date(request.GET.get("date_from"))
    date_to = _parse_date(request.GET.get("date_to"))
    member_id = request.GET.get("member", "")
    category_id = request.GET.get("category", "")

    member = None
    if member_id:
        member = Member.objects.filter(pk=member_id, church=church).first()
    category = None
    if category_id:
        category = LedgerCategory.objects.filter(pk=category_id, church=church).first()

    entries_qs = get_ledger_entries(
        church,
        status=status,
        transaction_type=txn_type,
        date_from=date_from,
        date_to=date_to,
        member=member,
        category=category,
    )

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        payload = export_ledger_entries_table(entries_qs[:5000])
        if export_fmt == "csv":
            return export_table_csv(payload["headers"], payload["rows"], "ledger-entries.csv")
        return export_table_excel(
            payload["headers"], payload["rows"], "ledger-entries.xlsx", payload["title"]
        )

    page_obj = paginate_ledger_entries(entries_qs, page=request.GET.get("page", 1), per_page=25)
    return render(request, "ledger/entries.html", {
        "entries": page_obj,
        "page_obj": page_obj,
        "status_filter": status,
        "type_filter": txn_type,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "member_filter": str(member.pk) if member else "",
        "category_filter": str(category.pk) if category else "",
        "members": Member.objects.filter(church=church, is_active=True).order_by(
            "last_name", "first_name"
        )[:500],
        "categories": get_all_categories(church),
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "Ledger Entries"},
        ],
    })


@ledger_finance_required
def category_report(request):
    """GL volume by posting category."""
    church = require_church(request)
    date_from = _parse_date(request.GET.get("date_from"))
    date_to = _parse_date(request.GET.get("date_to"))
    rows = get_category_gl_totals(church, date_from=date_from, date_to=date_to)

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        headers = ["Category", "Code", "Type", "Entries", "Volume"]
        export_rows = [
            [
                r["category"].name,
                r["category"].code,
                r["category"].get_transaction_type_display(),
                r["count"],
                str(r["volume"]),
            ]
            for r in rows
        ]
        if export_fmt == "csv":
            return export_table_csv(headers, export_rows, "ledger-by-category.csv")
        return export_table_excel(headers, export_rows, "ledger-by-category.xlsx", "GL by Category")

    return render(request, "ledger/category_report.html", {
        "rows": rows,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "By Category"},
        ],
    })


@ledger_finance_required
@require_http_methods(["GET", "POST"])
def entry_create(request):
    church = require_church(request)
    if request.method == "POST":
        form = LedgerEntryForm(request.POST, church=church)
        if form.is_valid():
            category = form.cleaned_data["category"]
            try:
                draft = build_entry_draft(
                    category=category,
                    amount=form.cleaned_data["amount"],
                    narration=form.cleaned_data["narration"],
                    entry_date=form.cleaned_data["date"],
                    member=form.cleaned_data.get("member"),
                )
                request.session[SESSION_DRAFT_KEY] = draft
                return redirect("ledger:entry_confirm")
            except (ValueError, PeriodLockedError, WorkingDayClosedError) as exc:
                flash_exception(request, exc, title="Entry could not be prepared")
    else:
        form = LedgerEntryForm(church=church, initial=_entry_initial(church, request))
    return render(request, "ledger/entry.html", {
        "form": form,
        "path_note": (
            "Use Treasury → Record Receipt for day-to-day tithes and offerings. "
            "Use this General Ledger entry when you need a category-driven journal "
            "(expenses, transfers, or special receipts)."
        ),
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "New Entry"},
        ],
    })


@ledger_finance_required
@require_http_methods(["GET", "POST"])
def entry_confirm(request):
    church = require_church(request)
    draft = request.session.get(SESSION_DRAFT_KEY)
    if not draft:
        flash_exception(request, "No entry to confirm. Please start again.", title="Session expired")
        return redirect("ledger:entry")

    if request.method == "POST":
        if request.POST.get("action") == "back":
            del request.session[SESSION_DRAFT_KEY]
            return redirect("ledger:entry")

        idem_key = request.POST.get("idempotency_key") or str(uuid.uuid4())
        try:
            txn = post_ledger_entry(
                church, request.user, draft, idempotency_key=idem_key
            )
            request.session.pop(SESSION_DRAFT_KEY, None)
            flash_success(
                request,
                f"{txn.reference} recorded and pending approval.",
                title="Ledger entry saved",
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
            flash_exception(request, exc, title="Entry could not be saved")

    return render(request, "ledger/confirm.html", {
        "draft": draft,
        "idempotency_key": str(uuid.uuid4()),
        "breadcrumbs": [
            {"label": "Ledger", "url": reverse("ledger:index")},
            {"label": "New Entry", "url": reverse("ledger:entry")},
            {"label": "Confirm"},
        ],
    })


@ledger_finance_required
@require_GET
def api_categories(request):
    church = require_church(request)
    txn_type = request.GET.get("type", "RECEIPT")
    if txn_type not in dict(LedgerCategory.TRANSACTION_TYPES):
        return JsonResponse({"categories": []})
    categories = get_categories_for_type(church, txn_type)
    return JsonResponse({
        "categories": [category_to_dict(c) for c in categories],
    })


@ledger_finance_required
@require_GET
def api_category_detail(request, pk):
    church = require_church(request)
    category = get_object_or_404(
        LedgerCategory.objects.select_related(
            "default_debit_account",
            "default_credit_account",
        ),
        pk=pk,
        church=church,
        is_active=True,
    )
    return JsonResponse(category_to_dict(category))
