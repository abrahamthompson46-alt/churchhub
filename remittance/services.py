"""Remittance policy resolution and offering split posting."""

from decimal import Decimal

from django.db.models import Sum
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from organization.services import get_church_financial_chain
from remittance import repositories as repo
from remittance import selectors
from remittance.constants import CHURCH_DEFAULT_POLICIES, SETTLEMENT_DEFAULT_POLICIES
from remittance.models import RemittancePolicy
from transactions import repositories as txn_repo


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
    from church_system.money import quantize_money

    return quantize_money(amount)


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
    return selectors.active_policy(
        unit_type, unit_id, offering_type, application_scope, as_of_date
    )


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
    account = selectors.account_by_type(church, account_type)
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
        txn_repo.create_transaction_line(
            transaction=transaction,
            account=_get_account_by_type(church, mapping["retain"]),
            amount=-retain,
            fund=funds["retain"],
        )
    if remit > 0:
        txn_repo.create_transaction_line(
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
        exists = selectors.active_policy_exists(
            "CHURCH",
            church.pk,
            row["offering_type"],
            row["application_scope"],
        )
        if exists:
            continue
        policy = repo.create_policy(
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
        exists = selectors.active_policy_exists(
            unit_type,
            unit_id,
            row["offering_type"],
            row["application_scope"],
        )
        if exists:
            continue
        policy = repo.create_policy(
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
    repo.create_policy_audit(
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


def save_remittance_policy(form_data, user, policy=None, church=None):
    """Create or update a remittance policy with audit trail."""
    unit_type = form_data.get("unit_type")
    unit_id = form_data.get("unit_id")
    if unit_type and unit_id and not unit_in_user_scope(
        user, unit_type, unit_id, church=church
    ):
        log_remittance_scope_violation(
            user,
            unit_type,
            unit_id,
            reason="save_remittance_policy rejected out-of-scope unit",
            church=church,
        )
        raise RemittancePolicyError(
            "Selected organization unit is outside your remittance scope."
        )
    return _save_remittance_policy(form_data, user, policy=policy, church=church)


@db_transaction.atomic
def _save_remittance_policy(form_data, user, policy=None, church=None):
    """Create or update a remittance policy with audit trail (after scope checks)."""
    from remittance.forms import RemittancePolicyForm

    if policy:
        instance = policy
        action = "UPDATE"
    else:
        instance = RemittancePolicy()
        action = "CREATE"

    form = RemittancePolicyForm(form_data, instance=instance, church=church, user=user)
    if not form.is_valid():
        raise RemittancePolicyError(form.errors.as_text())

    instance = form.save(commit=False)
    instance.created_by = instance.created_by or user
    repo.save_policy(instance)
    log_policy_change(instance, action, user)
    return instance


def get_fund_balances(church):
    """Summarize ledger lines by fund dimension for treasury display."""
    from transactions.models import TransactionLine

    rows = selectors.fund_balance_rows(church)
    labels = dict(TransactionLine.FUND_CHOICES)
    return [
        {"fund": row["fund"], "label": labels.get(row["fund"], row["fund"]), "balance": abs(row["balance"] or 0)}
        for row in rows
    ]


def resolve_unit_label(unit_type, unit_id):
    """Human-readable label for a financial unit."""
    obj = selectors.org_unit_by_type(unit_type, unit_id)
    if obj is None and unit_type not in (
        "CHURCH",
        "DISTRICT",
        "CONFERENCE",
        "UNION",
        "GENERAL_CONFERENCE",
    ):
        return unit_type
    return str(obj) if obj else f"{unit_type} ({unit_id})"


_UNIT_TYPE_TO_SCOPE = {
    "CHURCH": "CHURCH",
    "DISTRICT": "DISTRICT",
    "ZONE": "ZONE",
    "CONFERENCE": "CONFERENCE",
    "UNION": "UNION",
    "GENERAL_CONFERENCE": "GENERAL_CONFERENCE",
}


def _filter_units_by_denomination(queryset, unit_type, denomination):
    """Intersect org units with a denomination wall."""
    if not denomination:
        return queryset
    if unit_type == "CHURCH":
        return queryset.filter(district__zone__conference__denomination=denomination)
    if unit_type == "DISTRICT":
        return queryset.filter(zone__conference__denomination=denomination)
    if unit_type == "ZONE":
        return queryset.filter(conference__denomination=denomination)
    if unit_type == "CONFERENCE":
        return queryset.filter(denomination=denomination)
    if unit_type == "UNION":
        return queryset.filter(conferences__denomination=denomination).distinct()
    if unit_type == "GENERAL_CONFERENCE":
        return queryset.filter(
            unions__conferences__denomination=denomination
        ).distinct()
    return queryset.none()


def _platform_unit_queryset(unit_type, user, denomination=None):
    """Platform operators: managed denominations (or all for OWNER/superuser)."""
    from sitecontrol.platform_access import (
        filter_churches_for_operator,
        get_operator_denominations,
        operator_can_access_denomination,
        operator_has_global_access,
    )

    if denomination is not None and not operator_can_access_denomination(user, denomination):
        return selectors.empty_church_qs()

    if denomination is not None:
        denoms = selectors.platform_denomination_qs(denomination)
    else:
        denoms = get_operator_denominations(user)
    if not denoms.exists() and not operator_has_global_access(user):
        return selectors.empty_church_qs()

    if unit_type == "CHURCH":
        qs = filter_churches_for_operator(
            selectors.platform_churches_base_qs(),
            user,
        )
        if denomination is not None:
            qs = qs.filter(district__zone__conference__denomination=denomination)
        return qs.order_by("name")
    if unit_type == "DISTRICT":
        return selectors.districts_for_denominations(denoms)
    if unit_type == "CONFERENCE":
        return selectors.conferences_for_denominations(denoms)
    if unit_type == "UNION":
        return selectors.unions_for_denominations(denoms)
    if unit_type == "GENERAL_CONFERENCE":
        return selectors.general_conferences_for_denominations(denoms)
    return selectors.empty_church_qs()


def log_remittance_scope_violation(user, unit_type, unit_id, *, reason="", church=None):
    """Record attempted remittance access outside the caller's org scope."""
    repo.create_policy_audit(
        policy=None,
        action="SCOPE_VIOLATION",
        changed_by=user,
        snapshot={
            "unit_type": unit_type,
            "unit_id": str(unit_id) if unit_id else "",
            "reason": reason or "Unit outside caller scope",
            "church_id": str(church.pk) if church else "",
        },
    )


def unit_in_user_scope(user, unit_type, unit_id, *, church=None, denomination=None) -> bool:
    """True when unit_id appears in the caller's scoped remittance unit picker."""
    if not user or not unit_id:
        return False
    allowed = {
        choice_id
        for choice_id, _label in get_unit_choices(
            unit_type,
            user=user,
            church=church,
            denomination=denomination,
        )
    }
    return str(unit_id) in allowed


def get_unit_choices(unit_type, church=None, *, user=None, denomination=None):
    """
    Return (uuid, label) tuples for remittance policy unit pickers.

    Always filtered by the caller's manageable org subtree and denomination wall.
    Never falls back to a global unscoped queryset.
    """
    from church_system.denomination_scope import (
        get_church_denomination,
        get_user_denomination,
    )
    from permissions.org_scope import manageable_scope_units

    if not user or not getattr(user, "is_authenticated", False):
        return []

    if unit_type not in _UNIT_TYPE_TO_SCOPE:
        return []

    if getattr(user, "is_platform_user", False):
        denom = denomination
        if denom is None and church is not None:
            denom = get_church_denomination(church)
        qs = _platform_unit_queryset(unit_type, user, denomination=denom)
        return [(str(obj.pk), str(obj)) for obj in qs[:200]]

    level = _UNIT_TYPE_TO_SCOPE[unit_type]
    qs = manageable_scope_units(user, level)

    denom = denomination
    if denom is None and church is not None:
        denom = get_church_denomination(church)
    if denom is None:
        denom = get_user_denomination(user)
    if denom is not None:
        qs = _filter_units_by_denomination(qs, unit_type, denom)

    return [(str(obj.pk), str(obj)) for obj in qs.order_by("name")[:200]]


REMIT_PAYABLE_ACCOUNT = {
    "TITHE": "TITHE_REMIT_PAYABLE",
    "COMBINED": "COMBINED_REMIT_PAYABLE",
}


def _approved_line_balance(church, account) -> Decimal:
    from transactions.models import TransactionLine

    total = (
        TransactionLine.objects.filter(
            transaction__church=church,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account=account,
        ).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    return total


def remittance_outstanding_on_account(church, account) -> Decimal:
    """
    Positive amount still to pay via bank for remittance payable or district clearing.
    Obligations sit on net credit balances (negative line sum).
    """
    total = _approved_line_balance(church, account)
    if total < 0:
        return abs(total)
    return Decimal("0.00")


def outstanding_district_remittance_parts(church):
    """Tithe/combined still owed to district (payable bucket + clearing bucket)."""
    from ledger.services import seed_ledger_accounts
    from transactions.account_codes import get_remit_clearing_account
    from transactions.services import _get_account

    seed_ledger_accounts(church)
    breakdown = {}
    for offering in ("TITHE", "COMBINED"):
        payable = _get_account(church, REMIT_PAYABLE_ACCOUNT[offering])
        clearing = get_remit_clearing_account(church, offering, "DISTRICT")
        payable_out = remittance_outstanding_on_account(church, payable)
        clearing_out = remittance_outstanding_on_account(church, clearing)
        breakdown[offering] = {
            "payable": payable_out,
            "clearing": clearing_out,
            "total": payable_out + clearing_out,
        }
    tithe = breakdown["TITHE"]["total"]
    combined = breakdown["COMBINED"]["total"]
    return {
        "tithe": tithe,
        "combined": combined,
        "total": tithe + combined,
        "breakdown": breakdown,
    }


def build_remittance_payment_debits(church, offering_type, amount):
    """Allocate bank remittance debits: district clearing first, then payable."""
    from ledger.services import seed_ledger_accounts
    from transactions.account_codes import get_remit_clearing_account
    from transactions.services import _get_account

    amount = Decimal(str(amount))
    if amount <= 0:
        return []
    seed_ledger_accounts(church)
    payable = _get_account(church, REMIT_PAYABLE_ACCOUNT[offering_type])
    clearing = get_remit_clearing_account(church, offering_type, "DISTRICT")
    clearing_out = remittance_outstanding_on_account(church, clearing)
    payable_out = remittance_outstanding_on_account(church, payable)
    available = clearing_out + payable_out
    if amount > available + Decimal("0.01"):
        raise ValueError(
            f"Remittance amount {amount} exceeds outstanding {offering_type} balance ({available})."
        )
    debits = []
    remaining = amount
    if clearing_out > 0:
        take = min(remaining, clearing_out)
        debits.append((clearing, take))
        remaining -= take
    if remaining > 0 and payable_out > 0:
        take = min(remaining, payable_out)
        debits.append((payable, take))
        remaining -= take
    if remaining > Decimal("0.01"):
        raise ValueError(
            f"Could not allocate {offering_type} remittance debits ({remaining} unallocated)."
        )
    return debits


HIERARCHY_PARENT = {
    "CHURCH": ("DISTRICT", lambda church: church.district),
    "DISTRICT": ("CONFERENCE", lambda district: district.zone.conference),
    "CONFERENCE": ("UNION", lambda conference: conference.union),
    "UNION": ("GENERAL_CONFERENCE", lambda union: union.general_conference),
}


def _parent_unit(unit_type, unit_id):
    """Return (parent_type, parent_id) for the next level up."""
    if unit_type == "CHURCH":
        church = selectors.church_with_hierarchy(unit_id)
        return "DISTRICT", church.district.pk
    if unit_type == "DISTRICT":
        district = selectors.district_with_hierarchy(unit_id)
        return "CONFERENCE", district.zone.conference.pk
    if unit_type == "CONFERENCE":
        conference = selectors.conference_with_union(unit_id)
        if conference.union_id:
            return "UNION", conference.union.pk
        return None, None
    if unit_type == "UNION":
        union = selectors.union_with_gc(unit_id)
        return "GENERAL_CONFERENCE", union.general_conference.pk
    return None, None


def compute_period_remit_payable(church, offering_type, period_start, period_end):
    """Sum remittance payable credits posted in the period for an offering."""
    account_type = REMIT_PAYABLE_ACCOUNT.get(offering_type)
    if not account_type:
        return Decimal("0.00")
    return selectors.remit_payable_total(
        church, account_type, period_start, period_end
    )


def compute_received_from_below(unit_type, unit_id, offering_type, period_start, period_end):
    """Gross received by a unit from posted child settlements in the period."""
    return selectors.posted_settlements_received_total(
        unit_type, unit_id, offering_type, period_start, period_end
    )


@db_transaction.atomic
def create_settlement_draft(from_unit_type, from_unit_id, offering_type, period_start, period_end, user, church=None):
    """
    Create a draft settlement batch between hierarchy levels.

    CH-SEC-L3: lock any existing period rows and enforce one active
    (DRAFT/POSTED) batch per business key.
    """
    from remittance.models import SettlementBatch

    to_unit_type, to_unit_id = _parent_unit(from_unit_type, from_unit_id)
    if not to_unit_type:
        raise RemittancePolicyError("No parent unit exists for this settlement.")

    # Serialize concurrent creates for the same obligation key.
    list(
        SettlementBatch.objects.select_for_update().filter(
            from_unit_type=from_unit_type,
            from_unit_id=from_unit_id,
            offering_type=offering_type,
            period_start=period_start,
            period_end=period_end,
        )
    )

    if from_unit_type == "CHURCH":
        church = church or selectors.church_by_pk(from_unit_id)
        from remittance.cross_path import assert_settlement_not_blocked_by_bank_remit

        assert_settlement_not_blocked_by_bank_remit(
            church, period_start, period_end, offering_type=offering_type
        )
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

    if selectors.settlement_batch_exists_for_period(
        from_unit_type=from_unit_type,
        from_unit_id=from_unit_id,
        offering_type=offering_type,
        period_start=period_start,
        period_end=period_end,
    ):
        raise RemittancePolicyError("A settlement batch already exists for this period.")

    try:
        return repo.create_settlement_batch(
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
    except IntegrityError as exc:
        raise RemittancePolicyError(
            "A settlement batch already exists for this period."
        ) from exc


def user_can_edit_remittance_policy(user, policy, active_church=None):
    """Ensure remittance policy edits stay within the user's hierarchy scope."""
    from permissions.checks import can_manage_remittance_policy

    if not can_manage_remittance_policy(user):
        return False
    if unit_in_user_scope(
        user,
        policy.unit_type,
        policy.unit_id,
        church=active_church,
    ):
        return True
    log_remittance_scope_violation(
        user,
        policy.unit_type,
        policy.unit_id,
        reason="user_can_edit_remittance_policy denied",
        church=active_church,
    )
    return False


@db_transaction.atomic
def post_settlement_batch(batch, user):
    """Post settlement to the ledger and mark the batch as posted."""
    from remittance.models import SettlementBatch
    from transactions.services import (
        _get_account,
        _log_audit,
        approve_module_journal,
        assert_period_open,
        validate_transaction_balance,
    )

    locked = SettlementBatch.objects.select_for_update().get(pk=batch.pk)
    if locked.status == "POSTED":
        return locked
    if locked.status != "DRAFT":
        raise RemittancePolicyError("Only draft batches can be posted.")
    batch = locked

    if batch.from_unit_type == "CHURCH":
        church = selectors.church_by_pk(batch.from_unit_id)
        from remittance.cross_path import assert_settlement_not_blocked_by_bank_remit

        assert_settlement_not_blocked_by_bank_remit(
            church,
            batch.period_start,
            batch.period_end,
            offering_type=batch.offering_type,
        )
        assert_period_open(church, batch.period_end)
        payable_type = (
            "TITHE_REMIT_PAYABLE"
            if batch.offering_type == "TITHE"
            else "COMBINED_REMIT_PAYABLE"
        )
        trx = txn_repo.create_transaction(
            transaction_type="TRANSFER",
            church=church,
            created_by=batch.created_by or user,
            description=(
                f"Settlement {batch.get_offering_type_display()} "
                f"{batch.period_start} to {batch.period_end}"
            ),
            date=batch.period_end,
        )
        amount = batch.gross_received
        txn_repo.create_transaction_line(
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
        txn_repo.create_transaction_line(
            transaction=trx,
            account=credit_account,
            amount=-amount,
            fund=f"{batch.offering_type}_TRUST",
        )
        validate_transaction_balance(trx)
        trx = approve_module_journal(trx, user)
        if trx.approval_status != "APPROVED":
            raise RemittancePolicyError(
                "Settlement journal requires approval by an officer other than "
                "the batch creator before posting."
            )
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
        repo.create_settlement_line(
            batch=batch,
            source_transaction=trx,
            amount=amount,
            notes=f"{batch.offering_type} settlement",
        )
    elif batch.gross_received <= 0:
        raise RemittancePolicyError("No settlement amount to post.")
    else:
        # Higher-unit (district+) GL posting is not implemented. Never mark POSTED
        # without a balanced journal — refuse until CoA/clearing for those units exists.
        raise RemittancePolicyError(
            "Ledger posting for district and higher settlement batches is not yet "
            "implemented. The batch remains DRAFT until higher-unit GL posting is available."
        )

    batch.status = "POSTED"
    batch.posted_at = timezone.now()
    repo.save_settlement_batch(batch, update_fields=["status", "posted_at"])
    if batch.from_unit_type == "CHURCH":
        church = selectors.church_by_pk(batch.from_unit_id)
        try:
            from remittance.notifications import notify_district_settlement_posted

            notify_district_settlement_posted(batch, church=church)
        except Exception:
            pass
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


def disburse_welfare_case(case, user, payment_account_type="CASH", idempotency_key=None):
    from remittance.welfare_services import disburse_welfare_case as _disburse

    return _disburse(
        case,
        user,
        payment_account_type=payment_account_type,
        idempotency_key=idempotency_key,
    )
