"""
Read/query helpers for the remittance domain.

Views and services call selectors for scoped querysets.
Business rules stay in services; persistence writes stay in repositories.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from church_system.church_scope import filter_by_church
from members.models import Member

from .models import (
    RemittancePolicy,
    SettlementBatch,
    WelfareAssistanceCase,
    WelfareContribution,
    WelfareMemberLedger,
)


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


def policies_for_unit(unit_type, unit_id):
    if not unit_id:
        return RemittancePolicy.objects.none()
    return RemittancePolicy.objects.filter(
        unit_type=unit_type,
        unit_id=unit_id,
    ).order_by("offering_type", "application_scope", "-effective_from")


def policy_by_pk(pk):
    return get_object_or_404(RemittancePolicy, pk=pk)


def active_policy_qs(unit_type, unit_id, offering_type, application_scope, as_of_date):
    return (
        RemittancePolicy.objects.filter(
            unit_type=unit_type,
            unit_id=unit_id,
            offering_type=offering_type,
            application_scope=application_scope,
            is_active=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from")
    )


def active_policy(unit_type, unit_id, offering_type, application_scope, as_of_date):
    return active_policy_qs(
        unit_type, unit_id, offering_type, application_scope, as_of_date
    ).first()


def active_policy_exists(unit_type, unit_id, offering_type, application_scope):
    return RemittancePolicy.objects.filter(
        unit_type=unit_type,
        unit_id=unit_id,
        offering_type=offering_type,
        application_scope=application_scope,
        is_active=True,
    ).exists()


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------


def settlements_for_church(church, limit=50):
    return SettlementBatch.objects.filter(
        Q(from_unit_type="CHURCH", from_unit_id=church.pk)
        | Q(to_unit_type="CHURCH", to_unit_id=church.pk)
    ).order_by("-period_end", "-created_at")[:limit]


def settlements_incoming_to_unit(
    unit_type,
    unit_id,
    limit=50,
    *,
    status="POSTED",
    offering_type=None,
):
    """Settlement batches received by a hierarchy unit (default: posted only)."""
    if not unit_id:
        return SettlementBatch.objects.none()
    qs = SettlementBatch.objects.filter(
        to_unit_type=unit_type,
        to_unit_id=unit_id,
    )
    if status:
        qs = qs.filter(status=status)
    if offering_type:
        qs = qs.filter(offering_type=offering_type)
    return qs.order_by("-posted_at", "-period_end", "-created_at")[:limit]


def settlements_outgoing_from_unit(
    unit_type,
    unit_id,
    limit=50,
    *,
    status=None,
    offering_type=None,
):
    if not unit_id:
        return SettlementBatch.objects.none()
    qs = SettlementBatch.objects.filter(
        from_unit_type=unit_type,
        from_unit_id=unit_id,
    )
    if status:
        qs = qs.filter(status=status)
    if offering_type:
        qs = qs.filter(offering_type=offering_type)
    return qs.order_by("-period_end", "-created_at")[:limit]


def settlements_for_churches(church_ids, limit=100, *, status=None):
    if not church_ids:
        return SettlementBatch.objects.none()
    qs = SettlementBatch.objects.filter(
        from_unit_type="CHURCH",
        from_unit_id__in=list(church_ids),
    )
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-period_end", "-created_at")[:limit]


def settlement_desk_batches(
    *,
    desk_type,
    desk_id,
    church_ids,
    tab="all",
    status=None,
    offering_type=None,
    limit=100,
):
    """
    Scoped settlement list for a hierarchy desk.

    tab: incoming | outgoing | churches | all
    """
    if not desk_id:
        return SettlementBatch.objects.none()

    incoming_q = Q(to_unit_type=desk_type, to_unit_id=desk_id)
    outgoing_q = Q(from_unit_type=desk_type, from_unit_id=desk_id)
    church_q = Q()
    if church_ids:
        church_q = Q(from_unit_type="CHURCH", from_unit_id__in=list(church_ids))

    if tab == "incoming":
        base = incoming_q
    elif tab == "outgoing":
        base = outgoing_q
    elif tab == "churches":
        base = church_q if church_ids else Q(pk__in=[])
    else:
        base = incoming_q | outgoing_q | church_q

    qs = SettlementBatch.objects.filter(base)
    if status:
        qs = qs.filter(status=status)
    if offering_type:
        qs = qs.filter(offering_type=offering_type)
    return qs.order_by("-period_end", "-created_at").distinct()[:limit]


def settlement_desk_summary(desk_type, desk_id, church_ids):
    """Light KPI counts for the desk header."""
    if not desk_id:
        return {
            "incoming_posted": 0,
            "outgoing_draft": 0,
            "church_draft": 0,
            "church_posted_mtd_gross": Decimal("0.00"),
        }
    incoming_posted = SettlementBatch.objects.filter(
        to_unit_type=desk_type,
        to_unit_id=desk_id,
        status="POSTED",
    ).count()
    outgoing_draft = SettlementBatch.objects.filter(
        from_unit_type=desk_type,
        from_unit_id=desk_id,
        status="DRAFT",
    ).count()
    church_draft = 0
    church_posted_mtd_gross = Decimal("0.00")
    if church_ids:
        church_draft = SettlementBatch.objects.filter(
            from_unit_type="CHURCH",
            from_unit_id__in=list(church_ids),
            status="DRAFT",
        ).count()
        from django.utils import timezone

        month_start = timezone.now().date().replace(day=1)
        church_posted_mtd_gross = (
            SettlementBatch.objects.filter(
                from_unit_type="CHURCH",
                from_unit_id__in=list(church_ids),
                status="POSTED",
                period_end__gte=month_start,
            ).aggregate(total=Sum("gross_received"))["total"]
            or Decimal("0.00")
        )
    return {
        "incoming_posted": incoming_posted,
        "outgoing_draft": outgoing_draft,
        "church_draft": church_draft,
        "church_posted_mtd_gross": church_posted_mtd_gross,
    }


def settlement_by_pk(pk):
    return get_object_or_404(SettlementBatch, pk=pk)


def settlement_batch_exists_for_period(
    *, from_unit_type, from_unit_id, offering_type, period_start, period_end
):
    return SettlementBatch.objects.filter(
        from_unit_type=from_unit_type,
        from_unit_id=from_unit_id,
        offering_type=offering_type,
        period_start=period_start,
        period_end=period_end,
        status__in=("DRAFT", "POSTED"),
    ).exists()


def posted_settlements_received_total(
    unit_type, unit_id, offering_type, period_start, period_end
) -> Decimal:
    total = SettlementBatch.objects.filter(
        to_unit_type=unit_type,
        to_unit_id=unit_id,
        offering_type=offering_type,
        status="POSTED",
        period_start__lte=period_end,
        period_end__gte=period_start,
    ).aggregate(total=Sum("gross_received"))["total"]
    return total or Decimal("0.00")


def posted_church_settlement_overlaps(church, month_start, month_end, offering_types):
    return SettlementBatch.objects.filter(
        from_unit_type="CHURCH",
        from_unit_id=church.pk,
        offering_type__in=offering_types,
        status="POSTED",
        period_start__lte=month_end,
        period_end__gte=month_start,
    ).exists()


# ---------------------------------------------------------------------------
# Org unit lookups (labels / parent chain)
# ---------------------------------------------------------------------------


def org_unit_by_type(unit_type, unit_id):
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
        return None
    return model.objects.filter(pk=unit_id).first()


def church_with_hierarchy(unit_id):
    from organization.models import Church

    return Church.objects.select_related("district__zone__conference__union").get(
        pk=unit_id
    )


def district_with_hierarchy(unit_id):
    from organization.models import District

    return District.objects.select_related("zone__conference__union").get(pk=unit_id)


def conference_with_union(unit_id):
    from organization.models import Conference

    return Conference.objects.select_related("union").get(pk=unit_id)


def union_with_gc(unit_id):
    from organization.models import Union

    return Union.objects.select_related("general_conference").get(pk=unit_id)


def church_by_pk(unit_id):
    from organization.models import Church

    return Church.objects.get(pk=unit_id)


# ---------------------------------------------------------------------------
# Platform / scoped unit pickers (raw querysets; scoping rules in services)
# ---------------------------------------------------------------------------


def platform_denomination_qs(denomination):
    from sitecontrol.models import Denomination

    return Denomination.objects.filter(pk=denomination.pk)


def empty_church_qs():
    from organization.models import Church

    return Church.objects.none()


def platform_churches_base_qs():
    from organization.models import Church

    return Church.objects.filter(is_active=True).select_related(
        "district__zone__conference__denomination"
    )


def districts_for_denominations(denoms):
    from organization.models import District

    return (
        District.objects.filter(zone__conference__denomination__in=denoms)
        .select_related("zone__conference")
        .order_by("name")
    )


def conferences_for_denominations(denoms):
    from organization.models import Conference

    return Conference.objects.filter(denomination__in=denoms).order_by("name")


def unions_for_denominations(denoms):
    from organization.models import Union

    return (
        Union.objects.filter(conferences__denomination__in=denoms)
        .distinct()
        .order_by("name")
    )


def general_conferences_for_denominations(denoms):
    from organization.models import GeneralConference

    return (
        GeneralConference.objects.filter(unions__conferences__denomination__in=denoms)
        .distinct()
        .order_by("name")
    )


# ---------------------------------------------------------------------------
# Fund / remit payable reads (transaction lines)
# ---------------------------------------------------------------------------


def fund_balance_rows(church):
    from transactions.models import TransactionLine

    return (
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


def remit_payable_total(church, account_type, period_start, period_end) -> Decimal:
    from transactions.models import TransactionLine

    total = TransactionLine.objects.filter(
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        transaction__date__gte=period_start,
        transaction__date__lte=period_end,
        account__account_type=account_type,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(total)


def account_by_type(church, account_type):
    from transactions.models import Account

    return Account.objects.filter(church=church, account_type=account_type).first()


def welfare_fund_line_total(church, account) -> Decimal:
    from transactions.models import TransactionLine

    total = TransactionLine.objects.filter(
        transaction__church=church,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
        account=account,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(total)


# ---------------------------------------------------------------------------
# Welfare
# ---------------------------------------------------------------------------


def welfare_contributions_for_year(church, year, limit=50):
    return (
        WelfareContribution.objects.filter(church=church, contribution_date__year=year)
        .select_related("member", "transaction")
        .order_by("-contribution_date")[:limit]
    )


def welfare_cases_for_year(church, year, limit=50):
    return (
        WelfareAssistanceCase.objects.filter(church=church, created_at__year=year)
        .select_related("member", "created_by", "approved_by", "disbursed_by")
        .order_by("-created_at")[:limit]
    )


def welfare_case_for_church(church, pk, *, detail=False):
    qs = WelfareAssistanceCase.objects.all()
    if detail:
        qs = qs.select_related(
            "member",
            "created_by",
            "approved_by",
            "reviewed_by",
            "disbursed_by",
            "disbursement_transaction",
        )
    return get_object_or_404(qs, pk=pk, church=church)


def welfare_case_ledger_entries(case):
    return case.ledger_entries.select_related("transaction", "created_by").order_by(
        "-entry_date"
    )


def welfare_case_attachments(case):
    return case.attachments.select_related("uploaded_by")


def last_case_number_for_prefix(church, prefix):
    return (
        WelfareAssistanceCase.objects.filter(
            church=church, case_number__startswith=prefix
        )
        .order_by("-case_number")
        .values_list("case_number", flat=True)
        .first()
    )


def contributions_for_transaction(transaction):
    return WelfareContribution.objects.filter(transaction=transaction).select_related(
        "member", "church"
    )


def contribution_for_transaction_member(transaction, member):
    return WelfareContribution.objects.filter(
        transaction=transaction, member=member
    ).first()


def member_ledger_qs(member, year=None, start_date=None, end_date=None):
    qs = WelfareMemberLedger.objects.filter(member=member).select_related(
        "contribution", "case", "transaction", "created_by"
    )
    if year:
        qs = qs.filter(entry_date__year=year)
    if start_date:
        qs = qs.filter(entry_date__gte=start_date)
    if end_date:
        qs = qs.filter(entry_date__lte=end_date)
    return qs


def member_ledger_before_date(member, before_date):
    return WelfareMemberLedger.objects.filter(
        member=member, entry_date__lt=before_date
    )


def member_cases_qs(member):
    return WelfareAssistanceCase.objects.filter(member=member).select_related(
        "created_by", "approved_by", "disbursed_by", "disbursement_transaction"
    )


def member_contributions_qs(member, year=None):
    qs = WelfareContribution.objects.filter(
        member=member,
        transaction__is_voided=False,
    )
    if year:
        qs = qs.filter(contribution_date__year=year)
    return qs.select_related("transaction")


def church_contributions_year_qs(church, year):
    return WelfareContribution.objects.filter(
        church=church, contribution_date__year=year
    )


def church_cases_year_qs(church, year):
    return WelfareAssistanceCase.objects.filter(church=church, created_at__year=year)


def member_for_request(request, member_id):
    return get_object_or_404(
        filter_by_church(Member.objects.all(), request), pk=member_id
    )


def welfare_case_lock_for_disburse(case_id):
    # PostgreSQL rejects FOR UPDATE on the nullable side of an OUTER JOIN.
    # Only join required FKs (church, member) while the case row is locked.
    return (
        WelfareAssistanceCase.objects.select_for_update()
        .select_related("church", "member")
        .get(pk=case_id)
    )


def welfare_case_for_audit(case_id):
    return (
        WelfareAssistanceCase.objects.filter(pk=case_id)
        .select_related("church")
        .first()
    )


def contributions_with_member_iterator():
    return WelfareContribution.objects.filter(member__isnull=False).iterator()


def all_welfare_cases_iterator():
    return WelfareAssistanceCase.objects.iterator()


def cases_by_status_counts(cases_qs):
    return dict(cases_qs.values("status").annotate(c=Count("id")).values_list("status", "c"))
