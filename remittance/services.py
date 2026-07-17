"""Remittance policy resolution and offering split posting."""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction as db_transaction
from django.utils import timezone

from organization.services import get_church_financial_chain
from remittance.constants import CHURCH_DEFAULT_POLICIES, SETTLEMENT_DEFAULT_POLICIES
from remittance.models import RemittancePolicy, RemittancePolicyAuditLog
from transactions.models import Account, TransactionLine


class RemittancePolicyError(ValueError):
    pass


FUND_BY_OFFERING = {
    "TITHE": {"retain": "OPERATIONAL", "remit": "TITHE_TRUST"},
    "COMBINED": {"retain": "COMBINED_RETENTION", "remit": "COMBINED_TRUST"},
    "WELFARE": {"retain": "WELFARE", "remit": "WELFARE"},
}

ACCOUNT_TYPE_BY_SPLIT = {
    "TITHE": {"retain": "TITHE", "remit": "TITHE_REMIT_PAYABLE"},
    "COMBINED": {"retain": "COMBINED_RETENTION", "remit": "COMBINED_REMIT_PAYABLE"},
    "WELFARE": {"retain": "WELFARE_FUND", "remit": "WELFARE_FUND"},
}


def _quantize(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_split(gross_amount, retain_percent, remit_percent):
    """Split a gross amount into retain and remit portions."""
    gross_amount = Decimal(str(gross_amount))
    retain_percent = Decimal(str(retain_percent))
    remit_percent = Decimal(str(remit_percent))
    if retain_percent + remit_percent != Decimal("100"):
        raise RemittancePolicyError("Policy percentages must sum to 100.")
    retain = _quantize(gross_amount * retain_percent / Decimal("100"))
    remit = gross_amount - retain
    return retain, remit


def get_active_policy(unit_type, unit_id, offering_type, application_scope, as_of_date=None):
    """Return the active policy for a unit on a given date."""
    as_of_date = as_of_date or timezone.now().date()
    from django.db.models import Q

    qs = RemittancePolicy.objects.filter(
        unit_type=unit_type,
        unit_id=unit_id,
        offering_type=offering_type,
        application_scope=application_scope,
        is_active=True,
        effective_from__lte=as_of_date,
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date)
    ).order_by("-effective_from")
    return qs.first()


def get_church_collection_policy(church, offering_type, as_of_date=None):
    """Policy for gross collection at church level."""
    return get_active_policy(
        "CHURCH",
        church.pk,
        offering_type,
        "GROSS_COLLECTION",
        as_of_date=as_of_date,
    )


def get_settlement_policy(unit_type, unit_id, offering_type, as_of_date=None):
    """Policy for settlement between hierarchy levels."""
    return get_active_policy(
        unit_type,
        unit_id,
        offering_type,
        "SETTLEMENT_FROM_BELOW",
        as_of_date=as_of_date,
    )


def _get_account_by_type(church, account_type):
    account = Account.objects.filter(church=church, account_type=account_type).first()
    if not account:
        raise RemittancePolicyError(
            f"Missing {account_type} account for {church.name}. Run account setup."
        )
    return account


def post_offering_credit_lines(transaction, church, offering_type, gross_amount, as_of_date=None):
    """
    Post credit-side lines for an offering receipt using configured policy.

    Returns (retain_amount, remit_amount).
    """
    policy = get_church_collection_policy(church, offering_type, as_of_date=as_of_date)
    if not policy:
        raise RemittancePolicyError(
            f"No remittance policy configured for {offering_type} at {church.name}."
        )

    retain, remit = calculate_split(
        gross_amount,
        policy.retain_percent,
        policy.remit_percent,
    )
    mapping = ACCOUNT_TYPE_BY_SPLIT[offering_type]
    funds = FUND_BY_OFFERING[offering_type]

    if retain > 0:
        TransactionLine.objects.create(
            transaction=transaction,
            account=_get_account_by_type(church, mapping["retain"]),
            amount=-retain,
            fund=funds["retain"],
        )
    if remit > 0:
        TransactionLine.objects.create(
            transaction=transaction,
            account=_get_account_by_type(church, mapping["remit"]),
            amount=-remit,
            fund=funds["remit"],
        )
    return retain, remit


def record_welfare_contribution(church, member, transaction, amount, contribution_date=None, notes="", user=None):
    """Track a member welfare contribution linked to a receipt."""
    from remittance.welfare_services import record_welfare_contribution as _record

    return _record(
        church,
        member,
        transaction,
        amount,
        contribution_date=contribution_date,
        notes=notes,
        user=user,
    )


def ensure_default_policies_for_church(church, user=None):
    """Seed church-level gross collection policies if none exist."""
    created = []
    for row in CHURCH_DEFAULT_POLICIES:
        exists = RemittancePolicy.objects.filter(
            unit_type="CHURCH",
            unit_id=church.pk,
            offering_type=row["offering_type"],
            application_scope=row["application_scope"],
            is_active=True,
        ).exists()
        if exists:
            continue
        policy = RemittancePolicy.objects.create(
            unit_type="CHURCH",
            unit_id=church.pk,
            offering_type=row["offering_type"],
            application_scope=row["application_scope"],
            retain_percent=Decimal(row["retain_percent"]),
            remit_percent=Decimal(row["remit_percent"]),
            created_by=user,
            notes="Default church policy",
        )
        created.append(policy)
    return created


def ensure_default_settlement_policies(unit_type, unit_id, user=None):
    """Seed settlement policies for district/conference/union/GC units."""
    created = []
    for row in SETTLEMENT_DEFAULT_POLICIES:
        exists = RemittancePolicy.objects.filter(
            unit_type=unit_type,
            unit_id=unit_id,
            offering_type=row["offering_type"],
            application_scope=row["application_scope"],
            is_active=True,
        ).exists()
        if exists:
            continue
        policy = RemittancePolicy.objects.create(
            unit_type=unit_type,
            unit_id=unit_id,
            offering_type=row["offering_type"],
            application_scope=row["application_scope"],
            retain_percent=Decimal(row["retain_percent"]),
            remit_percent=Decimal(row["remit_percent"]),
            created_by=user,
            notes=f"Default {unit_type.lower()} settlement policy",
        )
        created.append(policy)
    return created


def ensure_hierarchy_settlement_policies(church, user=None):
    """Ensure settlement policies exist for all units above the church."""
    chain = get_church_financial_chain(church)
    units = [
        ("DISTRICT", chain["district"].pk),
        ("CONFERENCE", chain["conference"].pk),
    ]
    if chain["union"]:
        units.append(("UNION", chain["union"].pk))
    if chain["general_conference"]:
        units.append(("GENERAL_CONFERENCE", chain["general_conference"].pk))

    created = []
    for unit_type, unit_id in units:
        created.extend(ensure_default_settlement_policies(unit_type, unit_id, user=user))
    return created


def log_policy_change(policy, action, user, snapshot=None):
    RemittancePolicyAuditLog.objects.create(
        policy=policy,
        action=action,
        changed_by=user,
        snapshot=snapshot or {
            "offering_type": policy.offering_type,
            "application_scope": policy.application_scope,
            "unit_type": policy.unit_type,
            "unit_id": str(policy.unit_id),
            "retain_percent": str(policy.retain_percent),
            "remit_percent": str(policy.remit_percent),
            "effective_from": policy.effective_from.isoformat(),
            "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
            "is_active": policy.is_active,
        },
    )


@db_transaction.atomic
def save_remittance_policy(form_data, user, policy=None, church=None):
    """Create or update a remittance policy with audit trail."""
    from remittance.forms import RemittancePolicyForm

    if policy:
        instance = policy
        action = "UPDATE"
    else:
        instance = RemittancePolicy()
        action = "CREATE"

    form = RemittancePolicyForm(form_data, instance=instance, church=church)
    if not form.is_valid():
        raise RemittancePolicyError(form.errors.as_text())

    instance = form.save(commit=False)
    instance.created_by = instance.created_by or user
    instance.full_clean()
    instance.save()
    log_policy_change(instance, action, user)
    return instance


def get_fund_balances(church):
    """Summarize ledger lines by fund dimension for treasury display."""
    from django.db.models import Sum

    rows = (
        TransactionLine.objects.filter(
            transaction__church=church,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
        )
        .exclude(fund="")
        .values("fund")
        .annotate(balance=Sum("amount"))
        .order_by("fund")
    )
    labels = dict(TransactionLine.FUND_CHOICES)
    return [
        {"fund": row["fund"], "label": labels.get(row["fund"], row["fund"]), "balance": abs(row["balance"] or 0)}
        for row in rows
    ]


def resolve_unit_label(unit_type, unit_id):
    """Human-readable label for a financial unit."""
    from organization.models import Church, Conference, District, GeneralConference, Union

    model_map = {
        "CHURCH": Church,
        "DISTRICT": District,
        "CONFERENCE": Conference,
        "UNION": Union,
        "GENERAL_CONFERENCE": GeneralConference,
    }
    model = model_map.get(unit_type)
    if not model:
        return unit_type
    obj = model.objects.filter(pk=unit_id).first()
    return str(obj) if obj else f"{unit_type} ({unit_id})"


def get_unit_choices(unit_type, church=None):
    """Return (uuid, label) tuples for policy admin unit picker."""
    from organization.models import Church, Conference, District, GeneralConference, Union

    if unit_type == "CHURCH":
        if church:
            return [(str(church.pk), str(church))]
        return [(str(c.pk), str(c)) for c in Church.objects.select_related("district").order_by("name")[:200]]
    if unit_type == "DISTRICT":
        if church:
            return [(str(church.district.pk), str(church.district))]
        return [(str(d.pk), str(d)) for d in District.objects.select_related("zone").order_by("name")[:200]]
    if unit_type == "CONFERENCE":
        if church:
            return [(str(church.conference.pk), str(church.conference))]
        return [(str(c.pk), str(c)) for c in Conference.objects.order_by("name")]
    if unit_type == "UNION":
        if church and church.union:
            return [(str(church.union.pk), str(church.union))]
        return [(str(u.pk), str(u)) for u in Union.objects.select_related("general_conference").order_by("name")]
    if unit_type == "GENERAL_CONFERENCE":
        if church and church.general_conference:
            return [(str(church.general_conference.pk), str(church.general_conference))]
        return [(str(gc.pk), str(gc)) for gc in GeneralConference.objects.order_by("name")]
    return []


REMIT_PAYABLE_ACCOUNT = {
    "TITHE": "TITHE_REMIT_PAYABLE",
    "COMBINED": "COMBINED_REMIT_PAYABLE",
}

HIERARCHY_PARENT = {
    "CHURCH": ("DISTRICT", lambda church: church.district),
    "DISTRICT": ("CONFERENCE", lambda district: district.zone.conference),
    "CONFERENCE": ("UNION", lambda conference: conference.union),
    "UNION": ("GENERAL_CONFERENCE", lambda union: union.general_conference),
}


def _parent_unit(unit_type, unit_id):
    """Return (parent_type, parent_id) for the next level up."""
    from organization.models import Church, Conference, District, Union

    if unit_type == "CHURCH":
        church = Church.objects.select_related("district__zone__conference__union").get(pk=unit_id)
        return "DISTRICT", church.district.pk
    if unit_type == "DISTRICT":
        district = District.objects.select_related("zone__conference__union").get(pk=unit_id)
        return "CONFERENCE", district.zone.conference.pk
    if unit_type == "CONFERENCE":
        conference = Conference.objects.select_related("union").get(pk=unit_id)
        if conference.union_id:
            return "UNION", conference.union.pk
        return None, None
    if unit_type == "UNION":
        union = Union.objects.select_related("general_conference").get(pk=unit_id)
        return "GENERAL_CONFERENCE", union.general_conference.pk
    return None, None


def compute_period_remit_payable(church, offering_type, period_start, period_end):
    """Sum remittance payable credits posted in the period for an offering."""
    from django.db.models import Sum

    account_type = REMIT_PAYABLE_ACCOUNT.get(offering_type)
    if not account_type:
        return Decimal("0.00")
    total = TransactionLine.objects.filter(
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__gte=period_start,
        transaction__date__lte=period_end,
        account__account_type=account_type,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(total)


def compute_received_from_below(unit_type, unit_id, offering_type, period_start, period_end):
    """Gross received by a unit from posted child settlements in the period."""
    from django.db.models import Sum

    from remittance.models import SettlementBatch

    total = SettlementBatch.objects.filter(
        to_unit_type=unit_type,
        to_unit_id=unit_id,
        offering_type=offering_type,
        status="POSTED",
        period_start__lte=period_end,
        period_end__gte=period_start,
    ).aggregate(total=Sum("gross_received"))["total"] or Decimal("0.00")
    return total


@db_transaction.atomic
def create_settlement_draft(from_unit_type, from_unit_id, offering_type, period_start, period_end, user, church=None):
    """
    Create a draft settlement batch between hierarchy levels.

    Church settlements use remittance payable balances; higher levels apply
    SETTLEMENT_FROM_BELOW policy on amounts received from below.
    """
    from remittance.models import SettlementBatch

    to_unit_type, to_unit_id = _parent_unit(from_unit_type, from_unit_id)
    if not to_unit_type:
        raise RemittancePolicyError("No parent unit exists for this settlement.")

    if from_unit_type == "CHURCH":
        church = church or __import__("organization.models", fromlist=["Church"]).Church.objects.get(pk=from_unit_id)
        gross = compute_period_remit_payable(church, offering_type, period_start, period_end)
        retain = Decimal("0.00")
        remit = gross
    else:
        gross = compute_received_from_below(from_unit_type, from_unit_id, offering_type, period_start, period_end)
        policy = get_settlement_policy(from_unit_type, from_unit_id, offering_type, as_of_date=period_end)
        if not policy:
            raise RemittancePolicyError(
                f"No settlement policy for {from_unit_type} / {offering_type}."
            )
        retain, remit = calculate_split(gross, policy.retain_percent, policy.remit_percent)

    if gross <= 0:
        raise RemittancePolicyError("No settlement amount for the selected period.")

    existing = SettlementBatch.objects.filter(
        from_unit_type=from_unit_type,
        from_unit_id=from_unit_id,
        offering_type=offering_type,
        period_start=period_start,
        period_end=period_end,
        status__in=("DRAFT", "POSTED"),
    ).exists()
    if existing:
        raise RemittancePolicyError("A settlement batch already exists for this period.")

    return SettlementBatch.objects.create(
        offering_type=offering_type,
        from_unit_type=from_unit_type,
        from_unit_id=from_unit_id,
        to_unit_type=to_unit_type,
        to_unit_id=to_unit_id,
        period_start=period_start,
        period_end=period_end,
        gross_received=gross,
        retain_amount=retain,
        remit_amount=remit,
        status="DRAFT",
        created_by=user,
    )


def user_can_edit_remittance_policy(user, policy, active_church=None):
    """Ensure remittance policy edits stay within the user's hierarchy scope."""
    from permissions.checks import can_manage_remittance_policy, can_view_all_churches

    if not can_manage_remittance_policy(user):
        return False
    if user.is_superuser or can_view_all_churches(user):
        return True
    church = active_church or getattr(user, "church", None)
    if not church:
        return False
    if policy.unit_type == "CHURCH":
        return str(policy.unit_id) == str(church.pk)
    if policy.unit_type == "DISTRICT":
        return str(policy.unit_id) == str(church.district_id)
    if policy.unit_type == "ZONE":
        return str(policy.unit_id) == str(church.district.zone_id)
    if policy.unit_type == "CONFERENCE":
        return str(policy.unit_id) == str(church.district.zone.conference_id)
    return False


@db_transaction.atomic
def post_settlement_batch(batch, user):
    """Post settlement to the ledger and mark the batch as posted."""
    from organization.models import Church
    from transactions.models import Transaction, TransactionLine
    from transactions.services import (
        _get_account,
        _log_audit,
        assert_period_open,
        validate_transaction_balance,
    )

    if batch.status != "DRAFT":
        raise RemittancePolicyError("Only draft batches can be posted.")

    if batch.from_unit_type == "CHURCH":
        church = Church.objects.get(pk=batch.from_unit_id)
        assert_period_open(church, batch.period_end)
        payable_type = (
            "TITHE_REMIT_PAYABLE"
            if batch.offering_type == "TITHE"
            else "COMBINED_REMIT_PAYABLE"
        )
        trx = Transaction.objects.create(
            transaction_type="TRANSFER",
            church=church,
            created_by=user,
            description=(
                f"Settlement {batch.get_offering_type_display()} "
                f"{batch.period_start} to {batch.period_end}"
            ),
            date=batch.period_end,
            approval_status="APPROVED",
            approved_by=user,
            approved_at=timezone.now(),
            locked=True,
        )
        amount = batch.gross_received
        TransactionLine.objects.create(
            transaction=trx,
            account=_get_account(church, payable_type),
            amount=amount,
            fund=f"{batch.offering_type}_TRUST",
        )
        from ledger.services import seed_ledger_accounts
        from transactions.account_codes import get_remit_clearing_account

        seed_ledger_accounts(church)
        credit_account = get_remit_clearing_account(
            church, batch.offering_type, unit_level="DISTRICT"
        )
        TransactionLine.objects.create(
            transaction=trx,
            account=credit_account,
            amount=-amount,
            fund=f"{batch.offering_type}_TRUST",
        )
        validate_transaction_balance(trx)
        _log_audit(
            church,
            "CREATE",
            user,
            transaction=trx,
            details={
                "type": "SETTLEMENT",
                "batch_id": str(batch.pk),
                "offering_type": batch.offering_type,
                "amount": str(amount),
            },
        )
        from remittance.models import SettlementLine

        SettlementLine.objects.create(
            batch=batch,
            source_transaction=trx,
            amount=amount,
            notes=f"{batch.offering_type} settlement",
        )
    elif batch.gross_received <= 0:
        raise RemittancePolicyError("No settlement amount to post.")
    else:
        # District+ settlements: ledger integration for higher units is tracked separately.
        pass

    batch.status = "POSTED"
    batch.posted_at = timezone.now()
    batch.save(update_fields=["status", "posted_at"])
    return batch


@db_transaction.atomic
def create_welfare_case(church, member, amount_requested, reason, user, **kwargs):
    from remittance.welfare_services import create_welfare_case as _create

    return _create(church, member, amount_requested, reason, user, **kwargs)


@db_transaction.atomic
def approve_welfare_case(case, user, amount_approved=None):
    from remittance.welfare_services import approve_welfare_case as _approve

    return _approve(case, user, amount_approved=amount_approved)


@db_transaction.atomic
def reject_welfare_case(case, user, rejection_reason=""):
    from remittance.welfare_services import reject_welfare_case as _reject

    return _reject(case, user, rejection_reason=rejection_reason)


@db_transaction.atomic
def disburse_welfare_case(case, user, payment_account_type="CASH"):
    from remittance.welfare_services import disburse_welfare_case as _disburse

    return _disburse(case, user, payment_account_type=payment_account_type)
