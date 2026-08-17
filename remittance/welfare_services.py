"""Enterprise welfare ledger, balances, and case workflow services."""

from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from remittance import repositories as repo
from remittance import selectors
from remittance.services import RemittancePolicyError
from church_system.money import quantize_money
from transactions import repositories as txn_repo


def _quantize(amount):
    return quantize_money(amount)


def generate_case_number(church):
    year = timezone.now().year
    prefix = f"WEL-{year}-"
    last = selectors.last_case_number_for_prefix(church, prefix)
    if last:
        try:
            seq = int(last.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def get_welfare_fund_balance(church):
    """Available welfare fund balance from approved GL lines."""
    account = selectors.account_by_type(church, "WELFARE_FUND")
    if not account:
        return Decimal("0.00")
    return selectors.welfare_fund_line_total(church, account)


def assert_welfare_fund_sufficient(church, amount):
    amount = _quantize(amount)
    balance = get_welfare_fund_balance(church)
    if amount > balance:
        raise RemittancePolicyError(
            f"Insufficient welfare fund balance. Available: ₵{balance:.2f}, required: ₵{amount:.2f}."
        )


def post_ledger_entry(
    *,
    church,
    member,
    entry_type,
    direction,
    amount,
    entry_date=None,
    description="",
    reference="",
    contribution=None,
    case=None,
    transaction=None,
    user=None,
):
    return repo.create_member_ledger_entry(
        church=church,
        member=member,
        entry_type=entry_type,
        direction=direction,
        amount=_quantize(amount),
        entry_date=entry_date or timezone.now().date(),
        description=description[:255],
        reference=reference,
        contribution=contribution,
        case=case,
        transaction=transaction,
        created_by=user,
    )


@db_transaction.atomic
def record_welfare_contribution(church, member, transaction, amount, contribution_date=None, notes="", user=None):
    """Track a member welfare contribution and ledger entry linked to a receipt."""
    contribution_date = contribution_date or timezone.now().date()
    contribution = repo.create_welfare_contribution(
        church=church,
        member=member,
        transaction=transaction,
        amount=_quantize(amount),
        contribution_date=contribution_date,
        notes=notes,
        is_anonymous=member is None,
    )
    if member:
        post_ledger_entry(
            church=church,
            member=member,
            entry_type="CONTRIBUTION",
            direction="IN",
            amount=amount,
            entry_date=contribution_date,
            description=notes or "Welfare contribution",
            reference=transaction.reference if transaction else "",
            contribution=contribution,
            transaction=transaction,
            user=user,
        )
    return contribution


@db_transaction.atomic
def void_welfare_for_transaction(transaction, user):
    """Reverse welfare contributions and member ledger entries when a receipt is voided."""
    contributions = selectors.contributions_for_transaction(transaction)
    for contribution in contributions:
        if contribution.member_id:
            post_ledger_entry(
                church=contribution.church,
                member=contribution.member,
                entry_type="ADJUSTMENT",
                direction="OUT",
                amount=contribution.amount,
                entry_date=timezone.now().date(),
                description=f"Void reversal — {transaction.reference or transaction.pk}",
                reference=transaction.reference or "",
                contribution=contribution,
                transaction=transaction,
                user=user,
            )
        repo.delete_welfare_contribution(contribution)


def welfare_module_enabled(church, user=None):
    from accounts.permissions import can_manage_finances
    from permissions.superadmin import is_superadmin
    from sitecontrol.services import church_has_feature

    if user and is_superadmin(user):
        return True
    if user and can_manage_finances(user):
        return True
    if not church:
        return False
    return church_has_feature(church, "remittance")


def member_welfare_ledger(
    member,
    year=None,
    start_date=None,
    end_date=None,
    limit=500,
    entry_type=None,
    direction=None,
):
    qs = selectors.member_ledger_qs(
        member, year=year, start_date=start_date, end_date=end_date
    )
    if entry_type:
        qs = qs.filter(entry_type=entry_type)
    if direction:
        qs = qs.filter(direction=direction)
    return qs.order_by("entry_date", "created_at")[:limit]


def member_welfare_opening_balance(member, before_date):
    if not before_date:
        return Decimal("0.00")
    qs = selectors.member_ledger_before_date(member, before_date)
    ins = qs.filter(direction="IN").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    outs = qs.filter(direction="OUT").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return _quantize(ins - outs)


def build_member_welfare_statement(
    member,
    start_date=None,
    end_date=None,
    entry_type=None,
    direction=None,
):
    """Chronological welfare ledger with running balance (contributions in, disbursements out)."""
    entries = list(
        member_welfare_ledger(
            member,
            start_date=start_date,
            end_date=end_date,
            entry_type=entry_type,
            direction=direction,
            limit=2000,
        )
    )
    use_opening = start_date and not entry_type and not direction
    opening = member_welfare_opening_balance(member, start_date) if use_opening else Decimal("0.00")
    balance = opening
    rows = []
    total_in = Decimal("0.00")
    total_out = Decimal("0.00")

    for entry in entries:
        in_amt = out_amt = Decimal("0.00")
        if entry.direction == "IN":
            in_amt = entry.amount
            balance += entry.amount
            total_in += entry.amount
        elif entry.direction == "OUT":
            out_amt = entry.amount
            balance -= entry.amount
            total_out += entry.amount
        rows.append({
            "entry": entry,
            "date": entry.entry_date,
            "type": entry.get_entry_type_display(),
            "reference": entry.reference,
            "description": entry.description,
            "in_amount": in_amt,
            "out_amount": out_amt,
            "balance": balance,
            "case_id": entry.case_id,
        })

    return {
        "opening_balance": opening,
        "closing_balance": balance,
        "total_in": total_in,
        "total_out": total_out,
        "rows": rows,
    }


def member_welfare_cases(member, limit=50, status=None, assistance_type=None):
    qs = selectors.member_cases_qs(member)
    if status:
        qs = qs.filter(status=status)
    if assistance_type:
        qs = qs.filter(assistance_type=assistance_type)
    return qs.order_by("-created_at")[:limit]


def member_welfare_contributions(member, year=None, limit=100):
    return (
        selectors.member_contributions_qs(member, year=year)
        .order_by("-contribution_date")[:limit]
    )


def member_welfare_summary(member, year=None, start_date=None, end_date=None):
    ledger_qs = selectors.member_ledger_qs(member)
    case_qs = selectors.member_cases_qs(member)
    if year:
        ledger_qs = ledger_qs.filter(entry_date__year=year)
        case_qs = case_qs.filter(created_at__year=year)
    if start_date:
        ledger_qs = ledger_qs.filter(entry_date__gte=start_date)
        case_qs = case_qs.filter(created_at__date__gte=start_date)
    if end_date:
        ledger_qs = ledger_qs.filter(entry_date__lte=end_date)
        case_qs = case_qs.filter(created_at__date__lte=end_date)

    contributed = ledger_qs.filter(entry_type="CONTRIBUTION").aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    received = ledger_qs.filter(entry_type="DISBURSEMENT").aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    adjustments = ledger_qs.filter(entry_type="ADJUSTMENT").aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    pending_cases = case_qs.filter(status__in=("PENDING", "UNDER_REVIEW")).count()
    pending_amount = case_qs.filter(status__in=("PENDING", "UNDER_REVIEW")).aggregate(
        total=Sum("amount_requested")
    )["total"] or Decimal("0.00")
    approved_awaiting = case_qs.filter(status="APPROVED").aggregate(
        total=Sum("amount_approved")
    )["total"] or Decimal("0.00")

    return {
        "contributed": contributed,
        "received": received,
        "adjustments": adjustments,
        "net_position": contributed - received,
        "pending_cases": pending_cases,
        "pending_amount": pending_amount,
        "approved_awaiting_disbursement": approved_awaiting,
        "open_requests": pending_cases + case_qs.filter(status="APPROVED").count(),
    }


def welfare_year_choices(years_back=5):
    current = timezone.now().year
    return list(range(current, current - years_back, -1))


def church_welfare_dashboard(church, year=None):
    year = year or timezone.now().year
    contributions = selectors.church_contributions_year_qs(church, year)
    cases = selectors.church_cases_year_qs(church, year)
    return {
        "fund_balance": get_welfare_fund_balance(church),
        "contributions_ytd": contributions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "disbursed_ytd": cases.filter(status="DISBURSED").aggregate(
            total=Sum("amount_approved")
        )["total"] or Decimal("0.00"),
        "pending_cases": cases.filter(status__in=("PENDING", "UNDER_REVIEW")).count(),
        "approved_awaiting": cases.filter(status="APPROVED").count(),
        "cases_by_status": selectors.cases_by_status_counts(cases),
    }


@db_transaction.atomic
def create_welfare_case(
    church,
    member,
    amount_requested,
    reason,
    user,
    assistance_type="OTHER",
    priority="NORMAL",
):
    case_number = generate_case_number(church)
    case = repo.create_welfare_case(
        church=church,
        case_number=case_number,
        member=member,
        amount_requested=_quantize(amount_requested),
        reason=reason,
        assistance_type=assistance_type,
        priority=priority,
        created_by=user,
    )
    post_ledger_entry(
        church=church,
        member=member,
        entry_type="REQUEST",
        direction="NEUTRAL",
        amount=amount_requested,
        entry_date=timezone.now().date(),
        description=f"Assistance request — {case.get_assistance_type_display()}",
        reference=case_number,
        case=case,
        user=user,
    )
    return case


def _welfare_is_high_risk(case) -> bool:
    return case.priority in ("HIGH", "URGENT") or case.assistance_type in (
        "MEDICAL",
        "EMERGENCY",
        "BEREAVEMENT",
    )


@db_transaction.atomic
def send_welfare_case_to_review(case, user, review_notes=""):
    if case.status != "PENDING":
        raise RemittancePolicyError("Only pending cases can be sent for review.")
    if case.created_by_id and case.created_by_id == user.id:
        raise RemittancePolicyError(
            "The case creator cannot review their own welfare case."
        )
    case.status = "UNDER_REVIEW"
    case.reviewed_by = user
    case.reviewed_at = timezone.now()
    case.review_notes = review_notes
    repo.save_welfare_case(case)
    return case


@db_transaction.atomic
def approve_welfare_case(case, user, amount_approved=None):
    """
    INV-SOD-02 / CH-SEC-011:
    - Creator cannot approve.
    - Reviewer cannot be final approver when reviewed_by is set.
    - High-risk cases must be UNDER_REVIEW before approval.
    """
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be approved.")
    if case.created_by_id and case.created_by_id == user.id:
        raise RemittancePolicyError(
            "The case creator cannot approve their own welfare case."
        )
    if case.reviewed_by_id and case.reviewed_by_id == user.id:
        raise RemittancePolicyError(
            "The case reviewer cannot also be the final approver."
        )
    if _welfare_is_high_risk(case) and case.status == "PENDING":
        raise RemittancePolicyError(
            "High-risk welfare cases must be reviewed by another officer before approval."
        )
    approved = _quantize(amount_approved or case.amount_requested)
    if approved <= 0:
        raise RemittancePolicyError("Approved amount must be greater than zero.")
    case.status = "APPROVED"
    case.amount_approved = approved
    case.approved_by = user
    case.approved_at = timezone.now()
    repo.save_welfare_case(case)
    return case


@db_transaction.atomic
def reject_welfare_case(case, user, rejection_reason=""):
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be rejected.")
    if case.created_by_id and case.created_by_id == user.id:
        raise RemittancePolicyError(
            "The case creator cannot reject their own welfare case."
        )
    case.status = "REJECTED"
    case.rejection_reason = rejection_reason
    case.approved_by = user
    case.approved_at = timezone.now()
    repo.save_welfare_case(case)
    return case


@db_transaction.atomic
def cancel_welfare_case(case, user):
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be cancelled.")
    case.status = "CANCELLED"
    case.reviewed_by = user
    case.reviewed_at = timezone.now()
    repo.save_welfare_case(case)
    return case


def _log_welfare_disburse_rejected(case, user, reason):
    """Audit rejected duplicate/invalid disbursement attempts (outside atomic rollback)."""
    from transactions.services import _log_audit

    _log_audit(
        case.church,
        "CREATE",
        user,
        transaction=None,
        details={
            "type": "WELFARE_DISBURSE_REJECTED",
            "case_id": str(case.pk),
            "case_number": case.case_number,
            "reason": reason,
            "status": case.status,
        },
    )


def disburse_welfare_case(case, user, payment_account_type="CASH", idempotency_key=None):
    """
    Disburse an approved welfare case to the GL.

    Locks the case row first (select_for_update), posts lines on an unlocked
    journal, then approves/locks via maker-checker. Duplicate attempts are
    rejected and audited outside the atomic block so the audit survives rollback.
    """
    case_id = case.pk if hasattr(case, "pk") else case
    try:
        return _disburse_welfare_case_atomic(
            case_id, user, payment_account_type, idempotency_key
        )
    except RemittancePolicyError as exc:
        if getattr(exc, "log_duplicate_audit", False):
            locked_case = selectors.welfare_case_for_audit(case_id)
            if locked_case:
                _log_welfare_disburse_rejected(locked_case, user, str(exc))
        raise


@db_transaction.atomic
def _disburse_welfare_case_atomic(case_id, user, payment_account_type, idempotency_key):
    from transactions.idempotency import (
        IdempotencyReplay,
        claim_financial_idempotency,
        complete_financial_idempotency,
        normalize_idempotency_key,
    )
    from transactions.services import (
        _get_account,
        _log_audit,
        approve_module_journal,
        assert_period_open,
        assert_working_day_allows_posting,
        resolve_transaction_date,
        validate_transaction_balance,
    )

    case = selectors.welfare_case_lock_for_disburse(case_id)

    if case.status == "DISBURSED" or case.disbursement_transaction_id:
        err = RemittancePolicyError(
            "This welfare case has already been disbursed."
        )
        err.log_duplicate_audit = True
        raise err

    if case.status != "APPROVED":
        raise RemittancePolicyError("Only approved cases can be disbursed.")

    amount = case.amount_approved
    if not amount or amount <= 0:
        raise RemittancePolicyError("Approved amount must be greater than zero.")

    key = normalize_idempotency_key(idempotency_key) or f"welfare-disburse-{case.pk}"
    try:
        idem_record = claim_financial_idempotency(
            case.church, user, "EXPENSE", key
        )
    except IdempotencyReplay as replay:
        case.refresh_from_db()
        if case.disbursement_transaction_id:
            err = RemittancePolicyError(
                "This welfare case has already been disbursed."
            )
            err.log_duplicate_audit = True
            raise err from replay
        raise RemittancePolicyError(
            "Duplicate welfare disbursement submission detected."
        ) from replay

    assert_welfare_fund_sufficient(case.church, amount)

    txn_date = resolve_transaction_date(case.church)
    assert_period_open(case.church, txn_date)
    assert_working_day_allows_posting(case.church, txn_date)

    maker = case.approved_by or case.created_by or user
    trx = txn_repo.create_transaction(
        transaction_type="EXPENSE",
        church=case.church,
        created_by=maker,
        description=f"Welfare assistance — {case.case_number} — {case.member.full_name}",
        member=case.member,
        date=txn_date,
    )
    payment = _get_account(case.church, payment_account_type)
    welfare_fund = _get_account(case.church, "WELFARE_FUND")

    txn_repo.create_transaction_line(
        transaction=trx,
        account=welfare_fund,
        amount=amount,
        fund="WELFARE",
    )
    txn_repo.create_transaction_line(
        transaction=trx,
        account=payment,
        amount=-amount,
        fund="WELFARE",
    )

    validate_transaction_balance(trx)
    trx = approve_module_journal(trx, user)
    if trx.approval_status != "APPROVED":
        raise RemittancePolicyError(
            "Welfare disbursement journal requires approval by an officer "
            "other than the case approver."
        )

    _log_audit(
        case.church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "type": "WELFARE_DISBURSEMENT",
            "case_id": str(case.pk),
            "case_number": case.case_number,
            "amount": str(amount),
        },
    )

    case.status = "DISBURSED"
    case.disbursement_transaction = trx
    case.disbursed_by = user
    case.disbursed_at = timezone.now()
    repo.save_welfare_case(
        case,
        update_fields=[
            "status",
            "disbursement_transaction",
            "disbursed_by",
            "disbursed_at",
            "updated_at",
        ],
    )

    post_ledger_entry(
        church=case.church,
        member=case.member,
        entry_type="DISBURSEMENT",
        direction="OUT",
        amount=amount,
        entry_date=txn_date,
        description=f"Welfare disbursed — {case.get_assistance_type_display()}",
        reference=case.case_number,
        case=case,
        transaction=trx,
        user=user,
    )
    complete_financial_idempotency(idem_record, trx)
    return case, trx


@db_transaction.atomic
def record_manual_welfare_contribution(church, member, amount, user, contribution_date=None, notes="", payment_account_type="CASH"):
    """Record welfare contribution via standard receipt posting."""
    from transactions.services import record_receipt

    if not member:
        raise RemittancePolicyError("A member is required for tracked welfare contributions.")
    contribution_date = contribution_date or timezone.now().date()
    trx = record_receipt(
        church=church,
        created_by=user,
        special_offerings={"WELFARE": _quantize(amount)},
        member=member,
        payment_account_type=payment_account_type,
        date=contribution_date,
        description=notes or f"Welfare contribution — {member.full_name}",
    )
    contribution = selectors.contribution_for_transaction_member(trx, member)
    if contribution:
        update_fields = []
        if notes:
            contribution.notes = notes
            update_fields.append("notes")
        if contribution.contribution_date != contribution_date:
            contribution.contribution_date = contribution_date
            update_fields.append("contribution_date")
        if update_fields:
            repo.save_welfare_contribution(contribution, update_fields=update_fields)
        repo.update_ledger_for_contribution(
            contribution,
            description=(notes or contribution.notes or "Welfare contribution"),
            entry_date=contribution_date,
        )
    return trx, contribution


def can_view_member_welfare(user, member):
    from accounts.permissions import can_manage_finances, can_manage_members

    if not welfare_module_enabled(member.church, user):
        return False
    if can_manage_finances(user) or can_manage_members(user):
        return True
    linked = getattr(user, "member_id", None)
    return linked is not None and linked == member.pk


def backfill_welfare_ledger():
    """Create ledger rows for historical contributions and disbursed cases."""
    created = 0
    for contribution in selectors.contributions_with_member_iterator():
        if contribution.ledger_entries.exists():
            continue
        post_ledger_entry(
            church=contribution.church,
            member=contribution.member,
            entry_type="CONTRIBUTION",
            direction="IN",
            amount=contribution.amount,
            entry_date=contribution.contribution_date,
            description=contribution.notes or "Welfare contribution (backfill)",
            reference=contribution.transaction.reference if contribution.transaction else "",
            contribution=contribution,
            transaction=contribution.transaction,
            user=None,
        )
        created += 1

    for case in selectors.all_welfare_cases_iterator():
        if not case.ledger_entries.filter(entry_type="REQUEST").exists():
            post_ledger_entry(
                church=case.church,
                member=case.member,
                entry_type="REQUEST",
                direction="NEUTRAL",
                amount=case.amount_requested,
                entry_date=case.created_at.date(),
                description=f"Assistance request — {case.get_assistance_type_display()}",
                reference=case.case_number or str(case.pk)[:8],
                case=case,
                user=case.created_by,
            )
            created += 1
        if case.status == "DISBURSED" and case.amount_approved and not case.ledger_entries.filter(entry_type="DISBURSEMENT").exists():
            post_ledger_entry(
                church=case.church,
                member=case.member,
                entry_type="DISBURSEMENT",
                direction="OUT",
                amount=case.amount_approved,
                entry_date=(case.disbursed_at or case.updated_at).date(),
                description="Welfare disbursed (backfill)",
                reference=case.case_number or str(case.pk)[:8],
                case=case,
                transaction=case.disbursement_transaction,
                user=case.disbursed_by,
            )
            created += 1
    return created
