"""Ledger seed data and atomic posting services."""

from decimal import Decimal

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from ledger.models import LedgerCategory
from transactions.models import Account, Transaction, TransactionLine
from transactions.services import (
    WorkingDayClosedError,
    _log_audit,
    _post_line,
    assert_period_open,
    assert_working_day_allows_posting,
    create_default_accounts,
    validate_transaction_balance,
)

# Extended chart of accounts for church administration (beyond core defaults).
EXTENDED_ACCOUNTS = [
    ("Petty Cash", "CASH"),
    ("Utilities Expense", "EXPENSE"),
    ("Rent Expense", "EXPENSE"),
    ("Salaries & Allowances", "EXPENSE"),
    ("Maintenance & Repairs", "EXPENSE"),
    ("Transport & Travel", "EXPENSE"),
    ("Office Supplies", "EXPENSE"),
    ("Missions & Outreach", "EXPENSE"),
    ("Welfare Assistance", "EXPENSE"),
    ("Bank Charges", "EXPENSE"),
    ("Thanksgiving Offering", "INCOME"),
    ("Building Fund", "INCOME"),
    ("Mission Offering", "INCOME"),
    ("Special Project Income", "INCOME"),
    ("Accrued Expenses", "DISTRICT_PAYABLE"),
]

# Category templates: (code, name, type, debit_name, credit_name, narration, requires_member, remit, sort)
CATEGORY_TEMPLATES = [
    # Receipts — Cash
    ("REC_TITHE_CASH", "Tithe Receipt (Cash)", "RECEIPT", "Cash", "Tithe", "Tithe received — cash", True, True, 10),
    ("REC_COMBINED_CASH", "Combined Offering (Cash)", "RECEIPT", "Cash", "Combined Offering", "Combined offering — cash", False, True, 20),
    ("REC_INCOME_CASH", "General Income (Cash)", "RECEIPT", "Cash", "General Income", "General income — cash", False, False, 30),
    ("REC_THANKS_CASH", "Thanksgiving (Cash)", "RECEIPT", "Cash", "Thanksgiving Offering", "Thanksgiving offering — cash", False, False, 40),
    ("REC_BUILDING_CASH", "Building Fund (Cash)", "RECEIPT", "Cash", "Building Fund", "Building fund — cash", False, False, 50),
    ("REC_MISSION_CASH", "Mission Offering (Cash)", "RECEIPT", "Cash", "Mission Offering", "Mission offering — cash", False, False, 60),
    ("REC_WELFARE_CASH", "Welfare Fund (Cash)", "RECEIPT", "Cash", "Welfare Fund", "Welfare fund — cash", True, False, 70),
    ("REC_SPECIAL_CASH", "Special Project (Cash)", "RECEIPT", "Cash", "Special Project Income", "Special project income — cash", False, False, 80),
    # Receipts — Bank
    ("REC_TITHE_BANK", "Tithe Receipt (Bank)", "RECEIPT", "Main Bank", "Tithe", "Tithe received — bank", True, True, 110),
    ("REC_COMBINED_BANK", "Combined Offering (Bank)", "RECEIPT", "Main Bank", "Combined Offering", "Combined offering — bank", False, True, 120),
    ("REC_INCOME_BANK", "General Income (Bank)", "RECEIPT", "Main Bank", "General Income", "General income — bank", False, False, 130),
    ("REC_THANKS_BANK", "Thanksgiving (Bank)", "RECEIPT", "Main Bank", "Thanksgiving Offering", "Thanksgiving offering — bank", False, False, 140),
    ("REC_BUILDING_BANK", "Building Fund (Bank)", "RECEIPT", "Main Bank", "Building Fund", "Building fund — bank", False, False, 150),
    ("REC_WELFARE_BANK", "Welfare Fund (Bank)", "RECEIPT", "Main Bank", "Welfare Fund", "Welfare fund — bank", True, False, 160),
    # Expenses — Cash
    ("EXP_UTIL_CASH", "Utilities (Cash)", "EXPENSE", "Utilities Expense", "Cash", "Utilities expense — cash", False, False, 10),
    ("EXP_RENT_CASH", "Rent (Cash)", "EXPENSE", "Rent Expense", "Cash", "Rent expense — cash", False, False, 20),
    ("EXP_SALARY_CASH", "Salaries (Cash)", "EXPENSE", "Salaries & Allowances", "Cash", "Salaries — cash", False, False, 30),
    ("EXP_MAINT_CASH", "Maintenance (Cash)", "EXPENSE", "Maintenance & Repairs", "Cash", "Maintenance — cash", False, False, 40),
    ("EXP_TRANSPORT_CASH", "Transport (Cash)", "EXPENSE", "Transport & Travel", "Cash", "Transport — cash", False, False, 50),
    ("EXP_SUPPLIES_CASH", "Office Supplies (Cash)", "EXPENSE", "Office Supplies", "Cash", "Office supplies — cash", False, False, 60),
    ("EXP_MISSION_CASH", "Missions (Cash)", "EXPENSE", "Missions & Outreach", "Cash", "Missions expense — cash", False, False, 70),
    ("EXP_WELFARE_CASH", "Welfare Assistance (Cash)", "EXPENSE", "Welfare Assistance", "Cash", "Welfare assistance — cash", False, False, 80),
    ("EXP_GENERAL_CASH", "General Expense (Cash)", "EXPENSE", "General Expense", "Cash", "General expense — cash", False, False, 90),
    # Expenses — Bank
    ("EXP_UTIL_BANK", "Utilities (Bank)", "EXPENSE", "Utilities Expense", "Main Bank", "Utilities expense — bank", False, False, 110),
    ("EXP_RENT_BANK", "Rent (Bank)", "EXPENSE", "Rent Expense", "Main Bank", "Rent expense — bank", False, False, 120),
    ("EXP_SALARY_BANK", "Salaries (Bank)", "EXPENSE", "Salaries & Allowances", "Main Bank", "Salaries — bank", False, False, 130),
    ("EXP_MAINT_BANK", "Maintenance (Bank)", "EXPENSE", "Maintenance & Repairs", "Main Bank", "Maintenance — bank", False, False, 140),
    ("EXP_BANK_CHARGES", "Bank Charges", "EXPENSE", "Bank Charges", "Main Bank", "Bank service charges", False, False, 150),
    ("EXP_GENERAL_BANK", "General Expense (Bank)", "EXPENSE", "General Expense", "Main Bank", "General expense — bank", False, False, 160),
    # Transfers — remittance clears remit payables (not Tithe/Combined income accounts)
    ("TRF_CASH_TO_BANK", "Transfer Cash → Bank", "TRANSFER", "Main Bank", "Cash", "Cash deposited to bank", False, False, 10),
    ("TRF_BANK_TO_CASH", "Transfer Bank → Cash", "TRANSFER", "Cash", "Main Bank", "Cash withdrawn from bank", False, False, 20),
    ("TRF_CASH_TO_PETTY", "Fund Petty Cash", "TRANSFER", "Petty Cash", "Cash", "Transfer to petty cash", False, False, 30),
    ("TRF_PETTY_TO_CASH", "Return Petty Cash", "TRANSFER", "Cash", "Petty Cash", "Return from petty cash", False, False, 40),
    ("TRF_TITHE_REMIT", "Tithe Remittance to District", "TRANSFER", "Tithe Remittance Payable", "Main Bank", "District tithe remittance", False, True, 50),
    ("TRF_COMBINED_REMIT", "Combined Remittance to District", "TRANSFER", "Combined Remittance Payable", "Main Bank", "District combined remittance", False, True, 60),
]

FUND_BY_ACCOUNT_TYPE = {
    "TITHE": "OPERATIONAL",
    "TITHE_REMIT_PAYABLE": "TITHE_TRUST",
    "COMBINED": "COMBINED_RETENTION",
    "COMBINED_RETENTION": "COMBINED_RETENTION",
    "COMBINED_REMIT_PAYABLE": "COMBINED_TRUST",
    "WELFARE_FUND": "WELFARE",
}

# Names owned by transactions.services.create_default_accounts — never overwrite type.
CORE_ACCOUNT_NAMES = frozenset({
    "Tithe",
    "Combined Offering",
    "General Income",
    "General Expense",
    "District Payable",
    "Tithe Remittance Payable",
    "Combined Remittance Payable",
    "Combined Retention Income",
    "Welfare Fund",
    "Remittance Receivable",
    "Salaries & Allowances",
    "Employer SSNIT Expense",
    "Salaries Payable",
    "PAYE Payable",
    "SSNIT Payable",
    "Pension Payable",
    "Main Bank",
    "Cash",
})


def _account_map(church):
    return {a.name: a for a in Account.objects.filter(church=church)}


def _assert_accounts_belong_to_church(category):
    debit = category.default_debit_account
    credit = category.default_credit_account
    if debit.church_id != category.church_id:
        raise ValueError(
            f"Debit account '{debit.name}' does not belong to {category.church.name}."
        )
    if credit.church_id != category.church_id:
        raise ValueError(
            f"Credit account '{credit.name}' does not belong to {category.church.name}."
        )
    if debit.pk == credit.pk:
        raise ValueError("Debit and credit accounts must be different.")


def offering_type_for_category(category):
    """Map ledger receipt categories to remittance offering types."""
    code = (category.code or "").upper()
    if code.startswith("REC_TITHE"):
        return "TITHE"
    if code.startswith("REC_COMBINED"):
        return "COMBINED"
    if code.startswith("REC_WELFARE"):
        return "WELFARE"
    if category.remit_to_district and category.transaction_type == "RECEIPT":
        credit_type = category.default_credit_account.account_type
        if credit_type in ("TITHE", "COMBINED", "WELFARE_FUND"):
            return {
                "TITHE": "TITHE",
                "COMBINED": "COMBINED",
                "WELFARE_FUND": "WELFARE",
            }[credit_type]
    return None


def _fund_for_account(account):
    return FUND_BY_ACCOUNT_TYPE.get(account.account_type, "")


def _remittance_preview_lines(church, offering_type, debit_account, amount, as_of_date):
    from remittance.services import (
        ACCOUNT_TYPE_BY_SPLIT,
        RemittancePolicyError,
        calculate_split,
        ensure_default_policies_for_church,
        get_church_collection_policy,
    )

    ensure_default_policies_for_church(church)
    policy = get_church_collection_policy(church, offering_type, as_of_date=as_of_date)
    if not policy:
        raise RemittancePolicyError(
            f"No remittance policy configured for {offering_type} at {church.name}."
        )
    retain, remit = calculate_split(amount, policy.retain_percent, policy.remit_percent)
    mapping = ACCOUNT_TYPE_BY_SPLIT[offering_type]
    lines = [
        {
            "account_name": debit_account.name,
            "debit": str(amount),
            "credit": None,
        }
    ]
    if retain > 0:
        retain_acct = Account.objects.get(church=church, account_type=mapping["retain"])
        lines.append({
            "account_name": retain_acct.name,
            "debit": None,
            "credit": str(retain),
        })
    if remit > 0:
        remit_acct = Account.objects.get(church=church, account_type=mapping["remit"])
        lines.append({
            "account_name": remit_acct.name,
            "debit": None,
            "credit": str(remit),
        })
    return lines, retain, remit


def seed_ledger_accounts(church):
    """Ensure core and extended accounts exist for a church."""
    create_default_accounts(church)
    for name, acc_type in EXTENDED_ACCOUNTS:
        if name in CORE_ACCOUNT_NAMES:
            continue
        Account.objects.update_or_create(
            church=church,
            name=name,
            defaults={"account_type": acc_type},
        )


def seed_ledger_categories(church, reset=False):
    """Seed posting categories with default debit/credit accounts."""
    seed_ledger_accounts(church)
    from remittance.services import ensure_default_policies_for_church

    ensure_default_policies_for_church(church)
    accounts = _account_map(church)

    if reset:
        # Soft-deactivate so historical Transaction.ledger_category FKs stay valid.
        LedgerCategory.objects.filter(church=church).update(is_active=False)

    for row in CATEGORY_TEMPLATES:
        code, name, txn_type, debit_name, credit_name, narration, req_member, remit, sort = row
        debit = accounts.get(debit_name)
        credit = accounts.get(credit_name)
        if not debit or not credit:
            continue
        if debit.church_id != church.pk or credit.church_id != church.pk:
            continue
        LedgerCategory.objects.update_or_create(
            church=church,
            code=code,
            defaults={
                "name": name,
                "transaction_type": txn_type,
                "default_debit_account": debit,
                "default_credit_account": credit,
                "default_narration": narration,
                "requires_member": req_member,
                "remit_to_district": remit,
                "sort_order": sort,
                "is_active": True,
            },
        )


def seed_ledger(church, reset=False):
    seed_ledger_categories(church, reset=reset)


def get_categories_for_type(church, transaction_type):
    return LedgerCategory.objects.filter(
        church=church,
        transaction_type=transaction_type,
        is_active=True,
    ).select_related("default_debit_account", "default_credit_account")


def get_all_categories(church, transaction_type=None, include_inactive=False):
    """Posting categories, optionally filtered by type."""
    qs = LedgerCategory.objects.filter(church=church).select_related(
        "default_debit_account",
        "default_credit_account",
    )
    if not include_inactive:
        qs = qs.filter(is_active=True)
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)
    return qs.order_by("transaction_type", "sort_order", "name")


def get_categories_grouped(church):
    """Categories grouped by transaction type for reference screens."""
    sections = []
    for key, label in LedgerCategory.TRANSACTION_TYPES:
        categories = list(get_all_categories(church, transaction_type=key))
        if categories:
            sections.append({
                "type": key,
                "label": label,
                "categories": categories,
            })
    return sections


def get_ledger_summary(church):
    """Counts and recent ledger-sourced transactions for the hub page."""
    categories = LedgerCategory.objects.filter(church=church, is_active=True)
    entries = Transaction.objects.filter(
        church=church,
        ledger_category__isnull=False,
    )
    return {
        "category_count": categories.count(),
        "receipt_count": categories.filter(transaction_type="RECEIPT").count(),
        "expense_count": categories.filter(transaction_type="EXPENSE").count(),
        "transfer_count": categories.filter(transaction_type="TRANSFER").count(),
        "entry_count": entries.count(),
        "pending_count": entries.filter(approval_status="PENDING").count(),
        "approved_count": entries.filter(approval_status="APPROVED", is_voided=False).count(),
    }


def get_ledger_entries(
    church,
    status="",
    transaction_type="",
    date_from=None,
    date_to=None,
    member=None,
    category=None,
):
    """Ledger-sourced transactions for the entries list (unpaginated queryset)."""
    qs = Transaction.objects.filter(
        church=church,
        ledger_category__isnull=False,
    ).select_related(
        "ledger_category",
        "member",
        "created_by",
    ).prefetch_related("lines__account").order_by("-date", "-created_at")

    if status:
        qs = qs.filter(approval_status=status)
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if member:
        qs = qs.filter(member=member)
    if category:
        qs = qs.filter(ledger_category=category)
    return qs


def paginate_ledger_entries(queryset, page=1, per_page=25):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page)


def get_category_gl_totals(church, date_from=None, date_to=None):
    """Approved ledger entry totals grouped by category (absolute receipt/expense amount)."""
    qs = Transaction.objects.filter(
        church=church,
        ledger_category__isnull=False,
        approval_status="APPROVED",
        is_voided=False,
    )
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    rows = []
    for cat in LedgerCategory.objects.filter(church=church, is_active=True).order_by(
        "transaction_type", "sort_order", "name"
    ):
        cat_txns = qs.filter(ledger_category=cat)
        count = cat_txns.count()
        if not count:
            continue
        # Sum absolute debit side (positive lines) as volume
        volume = (
            TransactionLine.objects.filter(
                transaction__in=cat_txns,
                amount__gt=0,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        rows.append({
            "category": cat,
            "count": count,
            "volume": volume,
        })
    return rows


def export_ledger_entries_table(entries):
    headers = ["Reference", "Type", "Category", "Date", "Narration", "Member", "Amount", "Status"]
    rows = []
    for t in entries:
        rows.append([
            t.reference,
            t.get_transaction_type_display(),
            t.ledger_category.name if t.ledger_category_id else "",
            t.date.isoformat() if t.date else "",
            t.description or "",
            t.member.full_name if t.member_id else "",
            str(t.receipt_total),
            t.get_approval_status_display(),
        ])
    return {
        "headers": headers,
        "rows": rows,
        "title": "Ledger Entries",
        "subtitle": "Category-driven general ledger postings",
    }


def category_to_dict(category):
    return {
        "id": str(category.pk),
        "code": category.code,
        "name": category.name,
        "transaction_type": category.transaction_type,
        "debit_account_id": str(category.default_debit_account_id),
        "debit_account_name": category.default_debit_account.name,
        "credit_account_id": str(category.default_credit_account_id),
        "credit_account_name": category.default_credit_account.name,
        "default_narration": category.default_narration,
        "requires_member": category.requires_member,
        "remit_to_district": category.remit_to_district,
        "offering_type": offering_type_for_category(category),
    }


def _budget_warning_for_expense(church, category, amount, entry_date):
    """Return a soft warning string if expense would exceed church budget for the debit account."""
    if category.transaction_type != "EXPENSE":
        return ""
    try:
        from budgets.services import budget_line_variance
        from transactions.models import Budget
    except Exception:
        return ""

    year = entry_date.year
    budget = Budget.objects.filter(
        church=church,
        year=year,
        account=category.default_debit_account,
        level="CHURCH",
    ).first()
    if not budget:
        return ""
    meta = budget_line_variance(budget)
    projected = (meta.get("actual") or Decimal("0.00")) + Decimal(str(amount))
    if projected > budget.amount:
        return (
            f"This expense would put {category.default_debit_account.name} over budget "
            f"(budget ₵ {budget.amount}, projected ₵ {projected})."
        )
    return ""


def build_entry_draft(category, amount, narration, entry_date, member=None):
    """Validate and normalize a ledger entry draft before confirmation."""
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if category.requires_member and not member:
        raise ValueError("This category requires a member to be selected.")

    _assert_accounts_belong_to_church(category)

    entry_date = entry_date or timezone.now().date()
    assert_period_open(category.church, entry_date)
    try:
        assert_working_day_allows_posting(category.church, entry_date)
    except WorkingDayClosedError as exc:
        raise WorkingDayClosedError(
            f"{exc} Open the working day for {entry_date:%d %b %Y} before preparing this entry."
        ) from exc

    narration = (narration or category.default_narration or category.name).strip()
    if not narration:
        raise ValueError("Narration is required.")

    offering_type = offering_type_for_category(category)
    if offering_type:
        lines, retain, remit = _remittance_preview_lines(
            category.church,
            offering_type,
            category.default_debit_account,
            amount,
            entry_date,
        )
        credit_summary = ", ".join(
            f"{ln['account_name']} ₵ {ln['credit']}" for ln in lines if ln.get("credit")
        )
        debit_name = category.default_debit_account.name
        credit_name = credit_summary or category.default_credit_account.name
    else:
        lines = [
            {
                "account_name": category.default_debit_account.name,
                "debit": str(amount),
                "credit": None,
            },
            {
                "account_name": category.default_credit_account.name,
                "debit": None,
                "credit": str(amount),
            },
        ]
        debit_name = category.default_debit_account.name
        credit_name = category.default_credit_account.name
        retain = remit = None

    budget_warning = _budget_warning_for_expense(
        category.church, category, amount, entry_date
    )

    return {
        "category_id": str(category.pk),
        "category_code": category.code,
        "category_name": category.name,
        "transaction_type": category.transaction_type,
        "debit_account_id": str(category.default_debit_account_id),
        "debit_account_name": debit_name,
        "credit_account_id": str(category.default_credit_account_id),
        "credit_account_name": credit_name,
        "amount": str(amount),
        "narration": narration,
        "date": entry_date.isoformat(),
        "member_id": str(member.pk) if member else None,
        "member_name": member.full_name if member else "",
        "requires_member": category.requires_member,
        "offering_type": offering_type,
        "remit_to_district": category.remit_to_district,
        "lines": lines,
        "retain_amount": str(retain) if retain is not None else None,
        "remit_amount": str(remit) if remit is not None else None,
        "budget_warning": budget_warning,
    }


@db_transaction.atomic
def post_ledger_entry(church, user, draft, idempotency_key=None):
    """
    Atomically post a confirmed ledger entry to the general ledger.

    Remittance receipts (tithe/combined/welfare) use policy-driven credit splits.
    Standard double-entry otherwise:
      DR debit account  (+amount)
      CR credit account (-amount)
    """
    from transactions.idempotency import (
        IdempotencyReplay,
        MissingIdempotencyKey,
        claim_financial_idempotency,
        complete_financial_idempotency,
        normalize_idempotency_key,
    )

    idem_record = None
    key = normalize_idempotency_key(idempotency_key)
    if key:
        try:
            idem_record = claim_financial_idempotency(church, user, "LEDGER", key)
        except IdempotencyReplay as replay:
            return replay.existing_transaction
    elif idempotency_key is not None:
        # Explicit empty key from UI — require a real key
        raise MissingIdempotencyKey(
            "Missing idempotency key. Refresh the page and try again."
        )

    category = LedgerCategory.objects.select_related(
        "default_debit_account",
        "default_credit_account",
    ).get(pk=draft["category_id"], church=church, is_active=True)

    if category.transaction_type != draft["transaction_type"]:
        raise ValueError("Category does not match the selected transaction type.")

    _assert_accounts_belong_to_church(category)

    amount = Decimal(str(draft["amount"]))
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    from datetime import date as date_cls

    entry_date = date_cls.fromisoformat(draft["date"])
    assert_period_open(church, entry_date)
    assert_working_day_allows_posting(church, entry_date)

    member = None
    if draft.get("member_id"):
        from members.models import Member

        member = Member.objects.filter(pk=draft["member_id"], church=church).first()
        if category.requires_member and not member:
            raise ValueError("A valid member is required for this category.")

    txn_type = category.transaction_type
    if txn_type == "TRANSFER":
        django_type = "TRANSFER"
    elif txn_type == "EXPENSE":
        django_type = "EXPENSE"
    else:
        django_type = "RECEIPT"

    trx = Transaction.objects.create(
        transaction_type=django_type,
        church=church,
        created_by=user,
        description=draft["narration"],
        member=member,
        date=entry_date,
        ledger_category=category,
    )

    offering_type = offering_type_for_category(category)
    if offering_type:
        from remittance.services import (
            ensure_default_policies_for_church,
            post_offering_credit_lines,
        )

        ensure_default_policies_for_church(church, user=user)
        _post_line(trx, category.default_debit_account, amount)
        post_offering_credit_lines(
            trx, church, offering_type, amount, as_of_date=entry_date
        )
    else:
        debit_fund = _fund_for_account(category.default_debit_account)
        credit_fund = _fund_for_account(category.default_credit_account)
        _post_line(trx, category.default_debit_account, amount, fund=debit_fund)
        _post_line(trx, category.default_credit_account, -amount, fund=credit_fund)

    validate_transaction_balance(trx)
    _log_audit(
        church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "source": "ledger",
            "category": category.code,
            "amount": str(amount),
            "debit": category.default_debit_account.name,
            "credit": category.default_credit_account.name,
            "offering_type": offering_type,
            "budget_warning": draft.get("budget_warning") or "",
        },
    )

    if offering_type == "WELFARE" and member:
        from remittance.welfare_services import record_welfare_contribution

        record_welfare_contribution(
            church,
            member,
            trx,
            amount,
            contribution_date=entry_date,
            notes=draft.get("narration", ""),
            user=user,
        )

    if idem_record:
        complete_financial_idempotency(idem_record, trx)
    return trx


@db_transaction.atomic
def update_ledger_category(category, user, *, name=None, default_narration=None,
                           requires_member=None, is_active=None, sort_order=None,
                           default_debit_account=None, default_credit_account=None):
    """Church-facing category update with audit trail."""
    before = {
        "name": category.name,
        "default_narration": category.default_narration,
        "requires_member": category.requires_member,
        "is_active": category.is_active,
        "sort_order": category.sort_order,
        "debit": str(category.default_debit_account_id),
        "credit": str(category.default_credit_account_id),
    }
    if name is not None:
        category.name = name.strip() or category.name
    if default_narration is not None:
        category.default_narration = default_narration.strip()
    if requires_member is not None:
        category.requires_member = bool(requires_member)
    if is_active is not None:
        category.is_active = bool(is_active)
    if sort_order is not None:
        category.sort_order = int(sort_order)
    if default_debit_account is not None:
        if default_debit_account.church_id != category.church_id:
            raise ValueError("Debit account must belong to this church.")
        category.default_debit_account = default_debit_account
    if default_credit_account is not None:
        if default_credit_account.church_id != category.church_id:
            raise ValueError("Credit account must belong to this church.")
        category.default_credit_account = default_credit_account

    _assert_accounts_belong_to_church(category)
    category.full_clean()
    category.save()

    _log_audit(
        category.church,
        "UPDATE",
        user,
        details={
            "source": "ledger_category",
            "category_code": category.code,
            "before": before,
            "after": {
                "name": category.name,
                "default_narration": category.default_narration,
                "requires_member": category.requires_member,
                "is_active": category.is_active,
                "sort_order": category.sort_order,
                "debit": str(category.default_debit_account_id),
                "credit": str(category.default_credit_account_id),
            },
        },
    )
    return category
