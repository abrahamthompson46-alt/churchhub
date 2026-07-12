"""Enterprise welfare ledger, balances, and case workflow services."""

from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from remittance.models import (
    WelfareAssistanceCase,
    WelfareContribution,
    WelfareMemberLedger,
)
from remittance.services import RemittancePolicyError


def _quantize(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"))


def generate_case_number(church):
    year = timezone.now().year
    prefix = f"WEL-{year}-"
    last = (
        WelfareAssistanceCase.objects.filter(church=church, case_number__startswith=prefix)
        .order_by("-case_number")
        .values_list("case_number", flat=True)
        .first()
    )
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
    from transactions.models import Account, TransactionLine

    account = Account.objects.filter(church=church, account_type="WELFARE_FUND").first()
    if not account:
        return Decimal("0.00")
    total = TransactionLine.objects.filter(
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        account=account,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(total)


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
    return WelfareMemberLedger.objects.create(
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
    contribution = WelfareContribution.objects.create(
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
    contributions = WelfareContribution.objects.filter(transaction=transaction).select_related(
        "member", "church"
    )
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
        contribution.delete()


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


def member_welfare_ledger(member, year=None, start_date=None, end_date=None, limit=500):
    qs = WelfareMemberLedger.objects.filter(member=member).select_related(
        "contribution", "case", "transaction", "created_by"
    )
    if year:
        qs = qs.filter(entry_date__year=year)
    if start_date:
        qs = qs.filter(entry_date__gte=start_date)
    if end_date:
        qs = qs.filter(entry_date__lte=end_date)
    return qs.order_by("entry_date", "created_at")[:limit]


def member_welfare_opening_balance(member, before_date):
    if not before_date:
        return Decimal("0.00")
    qs = WelfareMemberLedger.objects.filter(member=member, entry_date__lt=before_date)
    ins = qs.filter(direction="IN").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    outs = qs.filter(direction="OUT").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return _quantize(ins - outs)


def build_member_welfare_statement(member, start_date=None, end_date=None):
    """Chronological welfare ledger with running balance (contributions in, disbursements out)."""
    entries = list(
        member_welfare_ledger(member, start_date=start_date, end_date=end_date, limit=2000)
    )
    opening = member_welfare_opening_balance(member, start_date) if start_date else Decimal("0.00")
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


def member_welfare_cases(member, limit=50):
    return (
        WelfareAssistanceCase.objects.filter(member=member)
        .select_related("created_by", "approved_by", "disbursed_by", "disbursement_transaction")
        .order_by("-created_at")[:limit]
    )


def member_welfare_contributions(member, year=None, limit=100):
    qs = WelfareContribution.objects.filter(
        member=member,
        transaction__is_voided=False,
    )
    if year:
        qs = qs.filter(contribution_date__year=year)
    return qs.select_related("transaction").order_by("-contribution_date")[:limit]


def member_welfare_summary(member, year=None, start_date=None, end_date=None):
    ledger_qs = WelfareMemberLedger.objects.filter(member=member)
    case_qs = WelfareAssistanceCase.objects.filter(member=member)
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
    contributions = WelfareContribution.objects.filter(church=church, contribution_date__year=year)
    cases = WelfareAssistanceCase.objects.filter(church=church, created_at__year=year)
    return {
        "fund_balance": get_welfare_fund_balance(church),
        "contributions_ytd": contributions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "disbursed_ytd": cases.filter(status="DISBURSED").aggregate(
            total=Sum("amount_approved")
        )["total"] or Decimal("0.00"),
        "pending_cases": cases.filter(status__in=("PENDING", "UNDER_REVIEW")).count(),
        "approved_awaiting": cases.filter(status="APPROVED").count(),
        "cases_by_status": dict(
            cases.values("status").annotate(c=Count("id")).values_list("status", "c")
        ),
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
    case = WelfareAssistanceCase.objects.create(
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


@db_transaction.atomic
def send_welfare_case_to_review(case, user, review_notes=""):
    if case.status != "PENDING":
        raise RemittancePolicyError("Only pending cases can be sent for review.")
    case.status = "UNDER_REVIEW"
    case.reviewed_by = user
    case.reviewed_at = timezone.now()
    case.review_notes = review_notes
    case.save()
    return case


@db_transaction.atomic
def approve_welfare_case(case, user, amount_approved=None):
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be approved.")
    approved = _quantize(amount_approved or case.amount_requested)
    if approved <= 0:
        raise RemittancePolicyError("Approved amount must be greater than zero.")
    case.status = "APPROVED"
    case.amount_approved = approved
    case.approved_by = user
    case.approved_at = timezone.now()
    case.save()
    return case


@db_transaction.atomic
def reject_welfare_case(case, user, rejection_reason=""):
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be rejected.")
    case.status = "REJECTED"
    case.rejection_reason = rejection_reason
    case.approved_by = user
    case.approved_at = timezone.now()
    case.save()
    return case


@db_transaction.atomic
def cancel_welfare_case(case, user):
    if case.status not in ("PENDING", "UNDER_REVIEW"):
        raise RemittancePolicyError("Only pending or under-review cases can be cancelled.")
    case.status = "CANCELLED"
    case.reviewed_by = user
    case.reviewed_at = timezone.now()
    case.save()
    return case


@db_transaction.atomic
def disburse_welfare_case(case, user, payment_account_type="CASH"):
    from transactions.models import Transaction, TransactionLine
    from transactions.services import (
        _get_account,
        _log_audit,
        assert_period_open,
        validate_transaction_balance,
    )

    if case.status != "APPROVED":
        raise RemittancePolicyError("Only approved cases can be disbursed.")
    amount = case.amount_approved
    if not amount or amount <= 0:
        raise RemittancePolicyError("Approved amount must be greater than zero.")

    assert_welfare_fund_sufficient(case.church, amount)

    txn_date = timezone.now().date()
    assert_period_open(case.church, txn_date)

    trx = Transaction.objects.create(
        transaction_type="EXPENSE",
        church=case.church,
        created_by=user,
        description=f"Welfare assistance — {case.case_number} — {case.member.full_name}",
        member=case.member,
        date=txn_date,
        approval_status="APPROVED",
        approved_by=user,
        approved_at=timezone.now(),
        locked=True,
    )
    payment = _get_account(case.church, payment_account_type)
    welfare_fund = _get_account(case.church, "WELFARE_FUND")

    TransactionLine.objects.create(
        transaction=trx,
        account=welfare_fund,
        amount=amount,
        fund="WELFARE",
    )
    TransactionLine.objects.create(
        transaction=trx,
        account=payment,
        amount=-amount,
        fund="WELFARE",
    )

    validate_transaction_balance(trx)
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
    case.save()

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
        post_approved=True,
    )
    contribution = WelfareContribution.objects.filter(transaction=trx, member=member).first()
    if contribution:
        update_fields = []
        if notes:
            contribution.notes = notes
            update_fields.append("notes")
        if contribution.contribution_date != contribution_date:
            contribution.contribution_date = contribution_date
            update_fields.append("contribution_date")
        if update_fields:
            contribution.save(update_fields=update_fields)
        WelfareMemberLedger.objects.filter(contribution=contribution).update(
            description=(notes or contribution.notes or "Welfare contribution")[:255],
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
    for contribution in WelfareContribution.objects.filter(member__isnull=False).iterator():
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

    for case in WelfareAssistanceCase.objects.iterator():
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
