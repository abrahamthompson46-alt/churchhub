"""
Financial services — balanced double-entry posting and audit trail.
"""

from datetime import date

from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from permissions.superadmin import is_superadmin

from . import repositories as repo
from . import selectors
from .models import (
    Account,
    BankReconciliation,
    BankReconciliationItem,
    FinancialAuditLog,
    FinancialPeriod,
    MonthlyCutoff,
    Transaction,
    TransactionLine,
    TreasuryApprovalPolicy,
    WorkingDay,
)


class UnbalancedTransactionError(ValueError):
    pass


class PeriodLockedError(ValueError):
    pass


class WorkingDayClosedError(ValueError):
    pass


def _log_audit(church, action, user, transaction=None, details=None):
    return repo.create_audit_log(
        church=church,
        action=action,
        user=user,
        transaction=transaction,
        details=details,
    )


def _quantize_currency(amount):
    from church_system.money import quantize_money

    return quantize_money(amount)


def validate_transaction_balance(transaction):
    """Raise if journal lines do not sum to zero (within one cent tolerance)."""
    total = repo.transaction_line_sum(transaction)
    if _quantize_currency(total) != Decimal("0.00"):
        raise UnbalancedTransactionError(
            f"Transaction {transaction.reference} is unbalanced: sum={total}"
        )
    return True


def assert_period_open(church, transaction_date=None):
    """Raise if the church's financial period for the given date is locked."""
    transaction_date = transaction_date or timezone.now().date()
    if selectors.is_financial_period_locked(
        church, transaction_date.year, transaction_date.month
    ):
        raise PeriodLockedError(
            f"Financial period {transaction_date.strftime('%B %Y')} is locked for {church.name}."
        )


def get_active_working_day(church):
    """Return the currently open working day for a church, if any."""
    return selectors.active_working_day(church)


def get_working_day_status(church):
    """Summary for templates: system clock vs business day."""
    active = get_active_working_day(church)
    system_date = timezone.localdate()
    return {
        "system_date": system_date,
        "active_working_day": active,
        "working_date": active.date if active else None,
        "is_open": bool(active),
        "last_closed": selectors.last_closed_working_day(church),
    }


def resolve_transaction_date(church, date=None):
    """Default posting date: explicit date, else open working day, else today."""
    if date:
        return date
    active = get_active_working_day(church)
    if active:
        return active.date
    return timezone.localdate()


def assert_working_day_allows_posting(church, transaction_date):
    """Require an open working day and matching business date for financial posts."""
    active = get_active_working_day(church)
    if not active:
        raise WorkingDayClosedError(
            f"No working day is open for {church.name}. Open the day before recording transactions."
        )
    if transaction_date != active.date:
        raise WorkingDayClosedError(
            f"Transactions must be posted to the open working day ({active.date:%d %b %Y}). "
            f"Received {transaction_date:%d %b %Y}."
        )
    if active.status != WorkingDay.STATUS_OPEN:
        raise WorkingDayClosedError(f"Working day {active.date:%d %b %Y} is closed.")


@db_transaction.atomic
def open_working_day(church, business_date, user, notes=""):
    """Open a business day for financial posting."""
    business_date = business_date or timezone.localdate()
    assert_period_open(church, business_date)

    current_open = get_active_working_day(church)
    if current_open and current_open.date != business_date:
        raise ValueError(
            f"Close the open working day ({current_open.date:%d %b %Y}) before opening another."
        )

    existing = selectors.working_day_for_date(church, business_date)
    if existing and existing.status == WorkingDay.STATUS_OPEN:
        raise ValueError(f"Working day {business_date:%d %b %Y} is already open.")

    if existing and existing.status == WorkingDay.STATUS_CLOSED:
        existing.status = WorkingDay.STATUS_OPEN
        existing.opened_by = user
        existing.opened_at = timezone.now()
        existing.closed_at = None
        existing.closed_by = None
        existing.notes = notes or existing.notes
        working_day = repo.save_working_day(existing)
    else:
        working_day = repo.create_working_day(
            church=church,
            date=business_date,
            status=WorkingDay.STATUS_OPEN,
            opened_by=user,
            notes=notes,
        )

    _log_audit(
        church,
        "UPDATE",
        user,
        details={"action": "open_working_day", "date": business_date.isoformat()},
    )
    return working_day


@db_transaction.atomic
def close_working_day(church, user, notes=""):
    """Close the currently open working day."""
    active = get_active_working_day(church)
    if not active:
        raise ValueError("No working day is currently open.")

    active.status = WorkingDay.STATUS_CLOSED
    active.closed_at = timezone.now()
    active.closed_by = user
    if notes:
        active.notes = notes
    repo.save_working_day(
        active,
        update_fields=["status", "closed_at", "closed_by", "notes", "updated_at"],
    )

    _log_audit(
        church,
        "UPDATE",
        user,
        details={"action": "close_working_day", "date": active.date.isoformat()},
    )
    return active


def get_recent_working_days(church, limit=10):
    return selectors.recent_working_days(church, limit=limit)


def lock_financial_period(church, year, month, user, notes=""):
    """Lock a month to prevent new or modified transactions."""
    period, _ = FinancialPeriod.objects.update_or_create(
        church=church,
        year=year,
        month=month,
        defaults={"is_locked": True, "locked_at": timezone.now(), "locked_by": user, "notes": notes},
    )
    if not period.is_locked:
        period.is_locked = True
        period.locked_at = timezone.now()
        period.locked_by = user
        period.notes = notes
        period.save()
    _log_audit(church, "UPDATE", user, details={"action": "lock_period", "year": year, "month": month})
    return period


def unlock_financial_period(church, year, month, user, notes=""):
    """Unlock a month to allow new transactions."""
    period = FinancialPeriod.objects.filter(church=church, year=year, month=month).first()
    if not period or not period.is_locked:
        raise ValueError("Period is not locked.")
    period.is_locked = False
    period.notes = notes or period.notes
    period.save(update_fields=["is_locked", "notes"])
    _log_audit(church, "UPDATE", user, details={"action": "unlock_period", "year": year, "month": month})
    return period


def get_financial_periods(church, year=None):
    """Return period lock status for each month in a year."""
    year = year or timezone.now().year
    periods = {
        p.month: p
        for p in selectors.financial_periods_for_year(church, year)
    }
    return [
        {
            "year": year,
            "month": m,
            "label": date(year, m, 1).strftime("%B"),
            "period": periods.get(m),
            "is_locked": periods[m].is_locked if m in periods else False,
        }
        for m in range(1, 13)
    ]


CORE_ACCOUNT_NAMES = {
    "TITHE": "Tithe",
    "COMBINED": "Combined Offering",
    "INCOME": "General Income",
    "EXPENSE": "General Expense",
    "DISTRICT_PAYABLE": "District Payable",
    "TITHE_REMIT_PAYABLE": "Tithe Remittance Payable",
    "COMBINED_REMIT_PAYABLE": "Combined Remittance Payable",
    "COMBINED_RETENTION": "Combined Retention Income",
    "WELFARE_FUND": "Welfare Fund",
    "REMITTANCE_RECEIVABLE": "Remittance Receivable",
    "SALARY_EXPENSE": "Salaries & Allowances",
    "EMPLOYER_SSNIT_EXPENSE": "Employer SSNIT Expense",
    "SALARIES_PAYABLE": "Salaries Payable",
    "PAYE_PAYABLE": "PAYE Payable",
    "SSNIT_PAYABLE": "SSNIT Payable",
    "PENSION_PAYABLE": "Pension Payable",
    "BANK": "Main Bank",
    "CASH": "Cash",
    "FIXED_ASSET": "Property, Plant & Equipment",
    "ACCUMULATED_DEPRECIATION": "Accumulated Depreciation",
    "DEPRECIATION_EXPENSE": "Depreciation Expense",
}


def _get_account(church, account_type):
    name = CORE_ACCOUNT_NAMES.get(account_type)
    if not name:
        raise ValueError(f"Unknown account type: {account_type}")
    return repo.get_account_by_name(church, name)


def _post_line(transaction, account, amount, fund=""):
    if account.church_id != transaction.church_id:
        raise ValueError(
            f"Account {account.name} does not belong to church {transaction.church.name}."
        )
    return repo.create_transaction_line(
        transaction=transaction,
        account=account,
        amount=amount,
        fund=fund,
    )


# ==========================================
# DEFAULT ACCOUNT CREATION
# ==========================================

def create_default_accounts(church):
    from transactions.account_codes import ACCOUNT_CODE_BY_NAME

    defaults = [
        ("Tithe", "TITHE"),
        ("Combined Offering", "COMBINED"),
        ("General Income", "INCOME"),
        ("General Expense", "EXPENSE"),
        ("District Payable", "DISTRICT_PAYABLE"),
        ("Tithe Remittance Payable", "TITHE_REMIT_PAYABLE"),
        ("Combined Remittance Payable", "COMBINED_REMIT_PAYABLE"),
        ("Combined Retention Income", "COMBINED_RETENTION"),
        ("Welfare Fund", "WELFARE_FUND"),
        ("Remittance Receivable", "REMITTANCE_RECEIVABLE"),
        ("Salaries & Allowances", "SALARY_EXPENSE"),
        ("Employer SSNIT Expense", "EMPLOYER_SSNIT_EXPENSE"),
        ("Salaries Payable", "SALARIES_PAYABLE"),
        ("PAYE Payable", "PAYE_PAYABLE"),
        ("SSNIT Payable", "SSNIT_PAYABLE"),
        ("Pension Payable", "PENSION_PAYABLE"),
        ("Main Bank", "BANK"),
        ("Cash", "CASH"),
        ("Property, Plant & Equipment", "FIXED_ASSET"),
        ("Accumulated Depreciation", "ACCUMULATED_DEPRECIATION"),
        ("Depreciation Expense", "DEPRECIATION_EXPENSE"),
    ]

    for name, acc_type in defaults:
        code = ACCOUNT_CODE_BY_NAME.get(name, "")
        Account.objects.update_or_create(
            church=church,
            name=name,
            defaults={"account_type": acc_type, "code": code, "is_active": True},
        )


def create_default_offering_categories(church):
    """Seed standard offering categories linked to church accounts."""
    from transactions.account_codes import code_for_name

    from .models import OfferingCategory

    # Prefer chart names that match ledger EXTENDED_ACCOUNTS to avoid duplicate codes.
    categories = [
        ("TITHE", "Tithe", "Tithe", "TITHE", True),
        ("COMBINED", "Combined Offering", "Combined Offering", "COMBINED", True),
        ("THANKSGIVING", "Thanksgiving", "Thanksgiving Offering", "INCOME", False),
        ("BUILDING", "Building Fund", "Building Fund", "INCOME", False),
        ("MISSION", "Mission Offering", "Mission Offering", "INCOME", False),
        ("WELFARE", "Welfare Fund", "Welfare Fund", "WELFARE_FUND", False),
    ]
    for code, label, account_name, acc_type, remit in categories:
        if acc_type in ("TITHE", "COMBINED"):
            account = Account.objects.get(church=church, account_type=acc_type)
        else:
            gl_code = code_for_name(account_name) or code
            account = Account.objects.filter(church=church, name=account_name).first()
            if account is None:
                account = Account.objects.create(
                    church=church,
                    name=account_name,
                    account_type=acc_type,
                    code=gl_code,
                    is_active=True,
                )
            elif not account.code:
                account.code = gl_code
                account.save(update_fields=["code"])
        OfferingCategory.objects.get_or_create(
            church=church,
            code=code,
            defaults={
                "name": label,
                "account": account,
                "remit_to_district": remit,
            },
        )


# ==========================================
# RECEIPT AUTO-APPROVAL (income SoD exception)
# ==========================================

# When a church policy leaves the limit blank, cap auto-approval at this amount
# instead of allowing unlimited maker self-approval.
DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT = Decimal("500.00")

def get_or_create_treasury_approval_policy(church):
    """Church policy defaults: auto-approve enabled with a capped limit."""
    policy, created = TreasuryApprovalPolicy.objects.get_or_create(church=church)
    if created and policy.default_receipt_auto_approve_limit is None:
        policy.default_receipt_auto_approve_limit = DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT
        policy.save(update_fields=["default_receipt_auto_approve_limit"])
    return policy


def effective_receipt_auto_approve_limit(user, church):
    """
    Return (enabled, limit).

    limit is None when unlimited; Decimal when capped (inclusive).
    User.max_receipt_auto_approve overrides the church default when set.
    """
    try:
        policy = church.treasury_approval_policy
        enabled = bool(policy.receipt_auto_approve_enabled)
        church_limit = policy.default_receipt_auto_approve_limit
    except TreasuryApprovalPolicy.DoesNotExist:
        enabled = True
        church_limit = None

    user_limit = getattr(user, "max_receipt_auto_approve", None)
    if user_limit is not None:
        return enabled, Decimal(str(user_limit))
    if church_limit is not None:
        return enabled, Decimal(str(church_limit))
    return enabled, DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT


def receipt_should_auto_approve(user, church, amount):
    """True when income may be auto-approved under church/user policy."""
    enabled, limit = effective_receipt_auto_approve_limit(user, church)
    if not enabled:
        return False
    amount = Decimal(str(amount))
    if limit is None:
        return True
    return amount <= limit


@db_transaction.atomic
def auto_approve_receipt(transaction, user):
    """
    Approve a RECEIPT as the maker when within policy limit.

    Documented maker-checker exception for income; audit details mark auto_approved.
    """
    if transaction.transaction_type != "RECEIPT":
        raise ValueError("Only receipts can be auto-approved.")
    if transaction.locked:
        raise ValueError("Transaction is already locked.")
    if transaction.approval_status != "PENDING":
        raise ValueError("Transaction is not pending approval.")

    assert_period_open(transaction.church, transaction.date)
    validate_transaction_balance(transaction)
    transaction.approval_status = "APPROVED"
    transaction.locked = True
    transaction.approved_by = user
    transaction.approved_at = timezone.now()
    repo.save_transaction(
        transaction,
        update_fields=["approval_status", "locked", "approved_by", "approved_at"],
    )
    _log_audit(
        transaction.church,
        "APPROVE",
        user,
        transaction=transaction,
        details={
            "reference": transaction.reference,
            "auto_approved": True,
            "sod_exception": "receipt_auto_approve",
        },
    )
    _mark_cutoff_transferred_for_remittance(transaction)
    try:
        from church_system.perf_cache import invalidate_church_finance_caches

        invalidate_church_finance_caches(
            transaction.church_id,
            year=transaction.date.year,
            month=transaction.date.month,
        )
    except Exception:
        pass
    return transaction


# ==========================================
# RECORD RECEIPT (balanced double-entry)
# ==========================================

@db_transaction.atomic
def record_receipt(
    church,
    created_by,
    tithe_amount=Decimal("0.00"),
    combined_amount=Decimal("0.00"),
    income_amount=Decimal("0.00"),
    special_offerings=None,
    payment_account_type="CASH",
    description="",
    member=None,
    date=None,
):
    """
    Post a balanced receipt:
      DR Cash/Bank (+total)
      CR Tithe / Combined / Income / Special offerings (-amounts)

    Receipts within the church/user auto-approve limit are approved immediately
    (maker-checker exception for income). Larger amounts stay PENDING.

    Prefer record_receipt_by_category for the teller UI; this multi-amount API
    remains for imports, contributions, welfare, and classic mode.
    """
    special_offerings = special_offerings or {}
    special_total = sum(Decimal(str(v)) for v in special_offerings.values())
    total_received = tithe_amount + combined_amount + income_amount + special_total

    if total_received <= 0:
        raise ValueError("Receipt total must be greater than zero.")

    txn_date = resolve_transaction_date(church, date)
    assert_period_open(church, txn_date)
    assert_working_day_allows_posting(church, txn_date)

    trx = repo.create_transaction(
        transaction_type="RECEIPT",
        church=church,
        created_by=created_by,
        description=description,
        member=member,
        date=txn_date,
    )

    payment_account = _get_account(church, payment_account_type)
    _post_line(trx, payment_account, total_received)

    from remittance.services import post_offering_credit_lines, record_welfare_contribution

    if tithe_amount > 0:
        post_offering_credit_lines(trx, church, "TITHE", tithe_amount, as_of_date=txn_date)

    if combined_amount > 0:
        post_offering_credit_lines(trx, church, "COMBINED", combined_amount, as_of_date=txn_date)

    if income_amount > 0:
        _post_line(trx, _get_account(church, "INCOME"), -income_amount)

    for offering_code, amount in special_offerings.items():
        amount = Decimal(str(amount))
        if amount <= 0:
            continue
        from .models import OfferingCategory

        category = OfferingCategory.objects.get(church=church, code=offering_code)
        if offering_code == "WELFARE":
            post_offering_credit_lines(trx, church, "WELFARE", amount, as_of_date=txn_date)
            if member:
                record_welfare_contribution(
                    church,
                    member,
                    trx,
                    amount,
                    contribution_date=txn_date,
                    user=created_by,
                )
        else:
            _post_line(trx, category.account, -amount)

    validate_transaction_balance(trx)
    _log_audit(
        church,
        "CREATE",
        created_by,
        transaction=trx,
        details={"type": "RECEIPT", "total": str(total_received)},
    )
    if receipt_should_auto_approve(created_by, church, total_received):
        trx = auto_approve_receipt(trx, created_by)
    return trx


@db_transaction.atomic
def record_receipt_by_category(
    church,
    created_by,
    category,
    amount,
    description="",
    member=None,
    date=None,
):
    """
    Post a single-category receipt using LedgerCategory defaults.

    Server re-resolves debit/credit from the category (never trust client IDs).
    Remittance tithe/combined/welfare categories keep policy splits via ledger posting.
    Auto-approve follows the same receipt rules as post_ledger_entry.
    """
    from ledger.services import build_entry_draft, post_ledger_entry

    if category is None:
        raise ValueError("A receipt category is required.")
    if getattr(category, "church_id", None) != church.pk:
        raise ValueError("Invalid category for this church.")
    if category.transaction_type != "RECEIPT":
        raise ValueError("Only receipt categories can be recorded here.")
    if not category.is_active:
        raise ValueError("This category is inactive.")

    draft = build_entry_draft(
        category=category,
        amount=amount,
        narration=description,
        entry_date=date,
        member=member,
    )
    # Idempotency is owned by the view (RECEIPT claim); do not double-claim here.
    return post_ledger_entry(church, created_by, draft, idempotency_key=None)


# ==========================================
# RECORD EXPENSE
# ==========================================

@db_transaction.atomic
def record_expense(
    church,
    created_by,
    amount,
    payment_account_type="CASH",
    description="",
    date=None,
    expense_account=None,
):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")

    txn_date = resolve_transaction_date(church, date)
    assert_period_open(church, txn_date)
    assert_working_day_allows_posting(church, txn_date)

    trx = repo.create_transaction(
        transaction_type="EXPENSE",
        church=church,
        created_by=created_by,
        description=description,
        date=txn_date,
    )

    _post_line(trx, _get_account(church, payment_account_type), -amount)
    expense_acct = expense_account or _get_account(church, "EXPENSE")
    if expense_acct.church_id != church.pk:
        raise ValueError("Expense account must belong to this church.")
    _post_line(trx, expense_acct, amount)

    validate_transaction_balance(trx)
    _log_audit(
        church,
        "CREATE",
        created_by,
        transaction=trx,
        details={"type": "EXPENSE", "amount": str(amount)},
    )
    return trx


# ==========================================
# RECORD TRANSFER (bank/cash or remittance)
# ==========================================

@db_transaction.atomic
def record_transfer(
    church,
    created_by,
    from_account_type,
    to_account_type,
    amount,
    description="",
    date=None,
):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Transfer amount must be greater than zero.")

    txn_date = resolve_transaction_date(church, date)
    assert_period_open(church, txn_date)
    assert_working_day_allows_posting(church, txn_date)

    trx = repo.create_transaction(
        transaction_type="TRANSFER",
        church=church,
        created_by=created_by,
        description=description,
        date=txn_date,
    )

    _post_line(trx, _get_account(church, to_account_type), amount)
    _post_line(trx, _get_account(church, from_account_type), -amount)

    validate_transaction_balance(trx)
    _log_audit(
        church,
        "CREATE",
        created_by,
        transaction=trx,
        details={
            "type": "TRANSFER",
            "from": from_account_type,
            "to": to_account_type,
            "amount": str(amount),
        },
    )
    return trx


# ==========================================
# DISTRICT REMITTANCE
# ==========================================

@db_transaction.atomic
def record_district_remittance(
    church,
    created_by,
    amount,
    payment_account_type="BANK",
    month_date=None,
    description="District remittance",
):
    """
    Step 3 of remittance: bank/cash payment that clears remit payables.

    Workflow:
      1. Receipts credit Tithe/Combined Remittance Payable (policy split)
      2. TRF_*_REMIT / settlement moves liability to hierarchy clearing accounts
      3. This function pays district from Bank/Cash:
           DR district clearing (if settlement posted) and/or remit payable
           CR Bank/Cash

    Use this when cash actually leaves the church.
    """
    from remittance.services import (
        build_remittance_payment_debits,
        outstanding_district_remittance_parts,
    )

    month_date = month_date.replace(day=1) if month_date else None
    cutoff = generate_monthly_cutoff(church, month_date) if month_date else None

    if cutoff:
        if cutoff.transferred:
            raise ValueError(
                f"District remittance for {month_date.strftime('%B %Y')} has already been transferred."
            )
        pending_remit = FinancialAuditLog.objects.filter(
            church=church,
            action="REMIT",
            details__cutoff_id=str(cutoff.pk),
        ).select_related("transaction").exclude(
            transaction__isnull=True,
        ).exclude(
            transaction__approval_status="REJECTED",
        ).exclude(
            transaction__is_voided=True,
        )
        if pending_remit.exists():
            raise ValueError(
                f"A remittance for {month_date.strftime('%B %Y')} is already recorded or pending approval."
            )

    outstanding = outstanding_district_remittance_parts(church)
    if cutoff:
        tithe_part = outstanding["tithe"]
        combined_part = outstanding["combined"]
        amount = outstanding["total"]
    else:
        amount = Decimal(str(amount))
        tithe_part = amount
        combined_part = Decimal("0.00")

    if amount <= 0:
        raise ValueError("Remittance amount must be greater than zero.")

    posting_date = resolve_transaction_date(church)
    assert_period_open(church, posting_date)
    assert_working_day_allows_posting(church, posting_date)

    trx = repo.create_transaction(
        transaction_type="TRANSFER",
        church=church,
        created_by=created_by,
        description=description,
        date=posting_date,
    )

    fund_by_offering = {"TITHE": "TITHE_TRUST", "COMBINED": "COMBINED_TRUST"}
    for offering_type, part in (("TITHE", tithe_part), ("COMBINED", combined_part)):
        if part <= 0:
            continue
        for account, debit_amount in build_remittance_payment_debits(
            church, offering_type, part
        ):
            _post_line(
                trx,
                account,
                debit_amount,
                fund=fund_by_offering[offering_type],
            )

    _post_line(trx, _get_account(church, payment_account_type), -amount)

    validate_transaction_balance(trx)

    if cutoff:
        _log_audit(
            church,
            "REMIT",
            created_by,
            transaction=trx,
            details={
                "amount": str(amount),
                "month": str(month_date),
                "cutoff_id": str(cutoff.pk),
            },
        )
    else:
        _log_audit(
            church,
            "REMIT",
            created_by,
            transaction=trx,
            details={"amount": str(amount), "month": str(month_date)},
        )
    return trx


# ==========================================
# APPROVE / REJECT
# ==========================================


def resolve_journal_checker(maker, *candidates):
    """Return the first candidate user distinct from maker, or None."""
    maker_id = getattr(maker, "pk", maker) if maker is not None else None
    for candidate in candidates:
        if candidate is None:
            continue
        candidate_id = getattr(candidate, "pk", candidate)
        if maker_id is None or candidate_id != maker_id:
            return candidate
    return None


@db_transaction.atomic
def approve_module_journal(transaction, *checker_candidates):
    """
    Approve a module-created PENDING journal through approve_transaction when a
    checker distinct from created_by is available.

    Returns the transaction (still PENDING when no distinct checker is found).
    """
    checker = resolve_journal_checker(transaction.created_by, *checker_candidates)
    if checker is None:
        return transaction
    return approve_transaction(transaction, checker)


@db_transaction.atomic
def approve_transaction(transaction, user):
    if transaction.approval_status == "APPROVED" and transaction.locked:
        return transaction
    if transaction.locked:
        raise ValueError("Transaction is already locked.")
    if transaction.created_by_id == user.id and not is_superadmin(user):
        raise ValueError("Creator cannot approve their own transaction.")

    assert_period_open(transaction.church, transaction.date)
    validate_transaction_balance(transaction)
    transaction.approval_status = "APPROVED"
    transaction.locked = True
    transaction.approved_by = user
    transaction.approved_at = timezone.now()
    repo.save_transaction(
        transaction,
        update_fields=["approval_status", "locked", "approved_by", "approved_at"],
    )
    _log_audit(
        transaction.church,
        "APPROVE",
        user,
        transaction=transaction,
        details={"reference": transaction.reference},
    )
    _mark_cutoff_transferred_for_remittance(transaction)
    try:
        from remittance.notifications import notify_district_remittance_payment_approved

        notify_district_remittance_payment_approved(transaction, approved_by=user)
    except Exception:
        pass
    try:
        from church_system.perf_cache import invalidate_church_finance_caches

        invalidate_church_finance_caches(
            transaction.church_id,
            year=transaction.date.year,
            month=transaction.date.month,
        )
    except Exception:
        pass
    return transaction


def _mark_cutoff_transferred_for_remittance(transaction):
    """Mark monthly cut-off complete when a district remittance txn is approved."""
    audit = selectors.remittance_audit_for_transaction(transaction)
    if not audit:
        return
    cutoff_id = (audit.details or {}).get("cutoff_id")
    if cutoff_id:
        repo.mark_monthly_cutoff_transferred(
            cutoff_id=cutoff_id,
            transfer_date=timezone.now().date(),
        )
        return
    month = (audit.details or {}).get("month")
    if month:
        repo.mark_monthly_cutoff_transferred(
            church=transaction.church,
            month=month,
            transfer_date=timezone.now().date(),
        )


@db_transaction.atomic
def reject_transaction(transaction, user, reason=""):
    if transaction.locked:
        raise ValueError("Transaction is already locked.")

    transaction.approval_status = "REJECTED"
    transaction.locked = True
    transaction.approved_by = user
    transaction.approved_at = timezone.now()
    repo.save_transaction(
        transaction,
        update_fields=["approval_status", "locked", "approved_by", "approved_at"],
    )
    _log_audit(
        transaction.church,
        "REJECT",
        user,
        transaction=transaction,
        details={"reference": transaction.reference, "reason": reason},
    )
    return transaction


@db_transaction.atomic
def void_transaction(transaction, user, reason=""):
    """Void an approved transaction by posting an equal-and-opposite reversal."""
    if transaction.is_voided:
        raise ValueError("Transaction is already voided.")
    if transaction.approval_status != "APPROVED":
        raise ValueError("Only approved transactions can be voided.")
    if transaction.reversal_of_id:
        raise ValueError("Reversal entries cannot be voided.")

    assert_period_open(transaction.church, transaction.date)
    validate_transaction_balance(transaction)

    reversal_date = transaction.date
    assert_period_open(transaction.church, reversal_date)
    active_day = get_active_working_day(transaction.church)
    if active_day and active_day.date == reversal_date:
        assert_working_day_allows_posting(transaction.church, reversal_date)

    reversal = repo.create_transaction(
        transaction_type=transaction.transaction_type,
        church=transaction.church,
        member=transaction.member,
        description=f"VOID: {transaction.reference}" + (f" — {reason}" if reason else ""),
        date=reversal_date,
        created_by=user,
        approval_status="APPROVED",
        locked=False,
        approved_by=user,
        approved_at=timezone.now(),
        reversal_of=transaction,
    )

    for line in transaction.lines.select_related("account"):
        _post_line(reversal, line.account, -line.amount)

    validate_transaction_balance(reversal)
    reversal.locked = True
    repo.save_transaction(reversal, update_fields=["locked"])

    from remittance.welfare_services import void_welfare_for_transaction

    void_welfare_for_transaction(transaction, user)

    transaction.is_voided = True
    transaction.voided_at = timezone.now()
    transaction.voided_by = user
    repo.save_transaction(
        transaction, update_fields=["is_voided", "voided_at", "voided_by"]
    )
    _log_audit(
        transaction.church,
        "VOID",
        user,
        transaction=transaction,
        details={
            "reference": transaction.reference,
            "reversal_reference": reversal.reference,
            "reason": reason,
        },
    )
    try:
        from church_system.perf_cache import invalidate_church_finance_caches

        invalidate_church_finance_caches(
            transaction.church_id,
            year=transaction.date.year,
            month=transaction.date.month,
        )
    except Exception:
        pass
    return reversal


# ==========================================
# MONTHLY CUTOFF
# ==========================================

def generate_monthly_cutoff(church, month_date):
    month_date = month_date.replace(day=1)
    approved_filter = {
        "transaction__church": church,
        "transaction__approval_status": "APPROVED",
        "transaction__is_voided": False,
        "transaction__date__month": month_date.month,
        "transaction__date__year": month_date.year,
    }

    tithe_total = abs(
        TransactionLine.objects.filter(
            account__account_type="TITHE_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    combined_total = abs(
        TransactionLine.objects.filter(
            account__account_type="COMBINED_REMIT_PAYABLE",
            **approved_filter,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    cutoff, _ = MonthlyCutoff.objects.update_or_create(
        church=church,
        month=month_date,
        defaults={
            "total_tithe": tithe_total,
            "total_combined": combined_total,
        },
    )
    return cutoff


# ==========================================
# BANK RECONCILIATION HELPERS
# ==========================================

def compute_book_balance(church, bank_account, as_of_date):
    """Sum approved, non-voided transaction lines on a bank account up to a date."""
    total = TransactionLine.objects.filter(
        account=bank_account,
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__lte=as_of_date,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return total


@db_transaction.atomic
def create_bank_reconciliation(church, bank_account, statement_date, statement_balance, user, notes=""):
    """Start a bank reconciliation with unmatched ledger lines."""
    if bank_account.account_type != "BANK":
        raise ValueError("Account must be a bank account.")
    if bank_account.church_id != church.pk:
        raise ValueError("Bank account does not belong to this church.")

    book_balance = compute_book_balance(church, bank_account, statement_date)
    recon = BankReconciliation.objects.create(
        church=church,
        bank_account=bank_account,
        statement_date=statement_date,
        statement_balance=Decimal(str(statement_balance)),
        book_balance=book_balance,
        notes=notes,
    )

    lines = TransactionLine.objects.filter(
        account=bank_account,
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__lte=statement_date,
    ).select_related("transaction").order_by("-transaction__date")

    matched_line_ids = BankReconciliationItem.objects.filter(
        is_matched=True,
        reconciliation__bank_account=bank_account,
        reconciliation__is_reconciled=True,
    ).values_list("transaction_line_id", flat=True)

    for line in lines.exclude(pk__in=matched_line_ids):
        BankReconciliationItem.objects.create(
            reconciliation=recon,
            transaction_line=line,
        )

    _log_audit(
        church,
        "CREATE",
        user,
        details={
            "type": "bank_reconciliation",
            "reconciliation_id": str(recon.pk),
            "statement_balance": str(statement_balance),
            "book_balance": str(book_balance),
        },
    )
    return recon


@db_transaction.atomic
def update_reconciliation_matches(reconciliation, matched_line_ids, user):
    """Mark selected ledger lines as matched on a reconciliation."""
    if reconciliation.is_reconciled:
        raise ValueError("Reconciliation is already finalized.")

    reconciliation.items.update(is_matched=False)
    if matched_line_ids:
        reconciliation.items.filter(
            transaction_line_id__in=matched_line_ids
        ).update(is_matched=True)

    matched_total = TransactionLine.objects.filter(
        pk__in=matched_line_ids,
        account=reconciliation.bank_account,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    reconciliation.book_balance = matched_total
    reconciliation.save(update_fields=["book_balance"])
    return reconciliation


@db_transaction.atomic
def finalize_bank_reconciliation(reconciliation, user):
    """Mark reconciliation complete when balances align."""
    if reconciliation.is_reconciled:
        raise ValueError("Already reconciled.")

    matched_total = TransactionLine.objects.filter(
        reconciliation_items__reconciliation=reconciliation,
        reconciliation_items__is_matched=True,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    if matched_total != reconciliation.statement_balance:
        diff = reconciliation.statement_balance - matched_total
        raise ValueError(
            f"Matched ledger total (₵{matched_total}) does not equal "
            f"statement balance (₵{reconciliation.statement_balance}). Difference: ₵{diff}."
        )

    reconciliation.is_reconciled = True
    reconciliation.reconciled_by = user
    reconciliation.reconciled_at = timezone.now()
    reconciliation.book_balance = matched_total
    reconciliation.save(update_fields=["is_reconciled", "reconciled_by", "reconciled_at", "book_balance"])

    _log_audit(
        reconciliation.church,
        "UPDATE",
        user,
        details={
            "action": "finalize_reconciliation",
            "reconciliation_id": str(reconciliation.pk),
            "statement_date": str(reconciliation.statement_date),
        },
    )
    return reconciliation


# ==========================================
# REPORTING
# ==========================================

def budget_vs_actual(church, year):
    """Return budget lines with actual spend/income for the year."""
    from budgets.services import budget_vs_actual as _budget_vs_actual

    return _budget_vs_actual(church, year)
