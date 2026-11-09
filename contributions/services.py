"""Business rules for contribution campaigns."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

from contributions import repositories as repo
from contributions import selectors
from contributions.models import (
    CampaignKind,
    CampaignStatus,
    ContributionCampaign,
    MemberContribution,
)
from church_system.money import quantize_money
from sitecontrol.services import church_has_feature


class ContributionServiceError(Exception):
    pass


def contributions_enabled(church, user=None) -> bool:
    if not church:
        return False
    return church_has_feature(church, "contribution_campaigns")


def _quantize(amount) -> Decimal:
    return quantize_money(amount)


def _validate_category_for_church(church, offering_category):
    if offering_category.church_id != church.pk:
        raise ValidationError({"offering_category": "Offering category must belong to this church."})
    if not offering_category.is_active:
        raise ValidationError({"offering_category": "Offering category must be active."})


def generate_campaign_code(church, kind=CampaignKind.GENERAL) -> str:
    """Allocate a church-unique campaign code (FUN-YYYY-NN or CMP-YYYY-NN)."""
    year = timezone.localdate().year
    prefix = "FUN" if kind == CampaignKind.DISTRICT_FUNERAL else "CMP"
    stem = f"{prefix}-{year}-"
    existing = ContributionCampaign.objects.filter(
        church=church, code__startswith=stem
    ).values_list("code", flat=True)
    max_seq = 0
    for value in existing:
        tail = value[len(stem) :]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    for seq in range(max_seq + 1, max_seq + 1000):
        candidate = f"{stem}{seq:02d}"
        if not ContributionCampaign.objects.filter(church=church, code=candidate).exists():
            return candidate
    raise ContributionServiceError("Could not allocate a campaign code.")


@db_transaction.atomic
def create_campaign(
    church,
    *,
    performed_by,
    name,
    purpose,
    deadline,
    offering_category,
    code=None,
    target_amount=None,
    default_member_target=None,
    portal_visible=True,
    show_church_progress=True,
    send_email_reminders=True,
    kind=CampaignKind.GENERAL,
) -> ContributionCampaign:
    _validate_category_for_church(church, offering_category)
    kind = kind or CampaignKind.GENERAL
    if kind == CampaignKind.DISTRICT_FUNERAL and offering_category.code == "WELFARE":
        raise ValidationError(
            {"offering_category": "District funeral collections cannot use the Welfare Fund."}
        )
    code = (code or "").strip().upper()
    if not code:
        code = generate_campaign_code(church, kind)
    if ContributionCampaign.objects.filter(church=church, code=code).exists():
        raise ValidationError({"code": "A campaign with this code already exists in this church."})
    campaign = ContributionCampaign(
        church=church,
        name=name.strip(),
        code=code,
        purpose=(purpose or "").strip(),
        deadline=deadline,
        offering_category=offering_category,
        target_amount=_quantize(target_amount) if target_amount not in (None, "") else None,
        default_member_target=_quantize(default_member_target)
        if default_member_target not in (None, "")
        else None,
        portal_visible=portal_visible,
        show_church_progress=show_church_progress,
        send_email_reminders=send_email_reminders,
        kind=kind or CampaignKind.GENERAL,
        status=CampaignStatus.DRAFT,
        created_by=performed_by,
        updated_by=performed_by,
    )
    campaign.full_clean()
    repo.save_campaign(campaign)
    return campaign


@db_transaction.atomic
def update_campaign(campaign, *, performed_by, **fields) -> ContributionCampaign:
    if campaign.status == CampaignStatus.ARCHIVED:
        raise ContributionServiceError("Archived campaigns cannot be edited.")
    next_kind = fields.get("kind", campaign.kind)
    next_category = fields.get("offering_category", campaign.offering_category)
    if next_kind == CampaignKind.DISTRICT_FUNERAL and next_category and next_category.code == "WELFARE":
        raise ValidationError(
            {"offering_category": "District funeral collections cannot use the Welfare Fund."}
        )
    if "offering_category" in fields and fields["offering_category"] is not None:
        _validate_category_for_church(campaign.church, fields["offering_category"])
    if "code" in fields and fields["code"]:
        code = fields["code"].strip().upper()
        if ContributionCampaign.objects.filter(church=campaign.church, code=code).exclude(pk=campaign.pk).exists():
            raise ValidationError({"code": "A campaign with this code already exists in this church."})
        fields["code"] = code
    if "target_amount" in fields and fields["target_amount"] not in (None, ""):
        fields["target_amount"] = _quantize(fields["target_amount"])
    if "default_member_target" in fields and fields["default_member_target"] not in (None, ""):
        fields["default_member_target"] = _quantize(fields["default_member_target"])
    for key, value in fields.items():
        if key in {"name", "purpose"} and isinstance(value, str):
            value = value.strip()
        setattr(campaign, key, value)
    campaign.updated_by = performed_by
    campaign.full_clean()
    repo.save_campaign(campaign)
    return campaign


@db_transaction.atomic
def open_campaign(campaign, *, performed_by) -> ContributionCampaign:
    if campaign.status not in {CampaignStatus.DRAFT, CampaignStatus.CLOSED}:
        raise ContributionServiceError("Only draft or closed campaigns can be opened.")
    campaign.status = CampaignStatus.OPEN
    campaign.opened_at = timezone.now()
    campaign.closed_at = None
    campaign.updated_by = performed_by
    repo.save_campaign(campaign, update_fields=["status", "opened_at", "closed_at", "updated_by", "updated_at"])
    return campaign


@db_transaction.atomic
def close_campaign(campaign, *, performed_by) -> ContributionCampaign:
    if campaign.status != CampaignStatus.OPEN:
        raise ContributionServiceError("Only open campaigns can be closed.")
    campaign.status = CampaignStatus.CLOSED
    campaign.closed_at = timezone.now()
    campaign.updated_by = performed_by
    repo.save_campaign(campaign, update_fields=["status", "closed_at", "updated_by", "updated_at"])
    return campaign


@db_transaction.atomic
def archive_campaign(campaign, *, performed_by) -> ContributionCampaign:
    if campaign.status == CampaignStatus.OPEN:
        raise ContributionServiceError("Close the campaign before archiving.")
    campaign.status = CampaignStatus.ARCHIVED
    campaign.updated_by = performed_by
    repo.save_campaign(campaign, update_fields=["status", "updated_by", "updated_at"])
    return campaign


def build_campaign_summary(campaign) -> dict:
    total = selectors.campaign_total_raised(campaign)
    contributors = selectors.campaign_contributor_count(campaign)
    active_count = selectors.active_members_for_church(campaign.church).count()
    target = campaign.target_amount
    progress_pct = None
    if target and target > 0:
        progress_pct = min(100, float((total / target) * 100))
    remitted = selectors.campaign_remitted_total(campaign)
    outstanding = max(Decimal("0.00"), total - remitted)
    return {
        "total_raised": total,
        "contributor_count": contributors,
        "active_member_count": active_count,
        "non_contributor_count": max(0, active_count - contributors),
        "target_amount": target,
        "progress_pct": progress_pct,
        "days_until_deadline": campaign.days_until_deadline,
        "is_past_deadline": campaign.is_past_deadline,
        "remitted_total": remitted,
        "outstanding_to_district": outstanding,
        "has_pending_remittance": selectors.campaign_has_pending_remittance(campaign),
    }


def contribution_idempotency_key(*parts) -> str:
    """Stable ≤64-char key for CONTRIBUTION idempotency claims."""
    import hashlib

    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


@db_transaction.atomic
def record_member_contribution(
    campaign,
    *,
    member,
    amount,
    performed_by,
    contribution_date=None,
    notes="",
    payment_account_type="CASH",
    idempotency_key=None,
) -> MemberContribution:
    """
    Record a campaign gift and post the receipt (CH-SEC-006 / INV-IDEM-01).

    Requires an idempotency key so retries cannot double-post.
    """
    from transactions.idempotency import (
        IdempotencyReplay,
        claim_financial_idempotency,
        complete_financial_idempotency,
    )
    from transactions.services import record_receipt, resolve_transaction_date

    if campaign.status != CampaignStatus.OPEN:
        raise ContributionServiceError("Contributions can only be recorded while the campaign is open.")
    if member.church_id != campaign.church_id:
        raise ContributionServiceError("Member must belong to the campaign church.")
    amount = _quantize(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    contribution_date = contribution_date or resolve_transaction_date(campaign.church)

    try:
        idem_record = claim_financial_idempotency(
            campaign.church,
            performed_by,
            "CONTRIBUTION",
            idempotency_key,
        )
    except IdempotencyReplay as replay:
        existing = (
            MemberContribution.objects.filter(transaction_id=replay.existing_transaction.pk)
            .select_related("transaction", "member")
            .first()
        )
        if existing:
            return existing
        raise ContributionServiceError(
            "This contribution was already recorded; refresh and continue."
        ) from replay

    category_code = campaign.offering_category.code
    description = notes.strip() or f"{campaign.name} — {member.full_name}"
    try:
        trx = record_receipt(
            church=campaign.church,
            created_by=performed_by,
            special_offerings={category_code: amount},
            member=member,
            payment_account_type=payment_account_type,
            date=contribution_date,
            description=description[:200],
        )
    except ValueError as exc:
        raise ContributionServiceError(str(exc)) from exc
    contribution = repo.create_contribution(
        campaign=campaign,
        member=member,
        amount=amount,
        contribution_date=contribution_date,
        transaction=trx,
        recorded_by=performed_by,
        notes=notes.strip()[:255],
    )
    complete_financial_idempotency(idem_record, trx)
    return contribution


@db_transaction.atomic
def record_bulk_contributions(
    campaign,
    *,
    entries: list[dict],
    performed_by,
    contribution_date=None,
    payment_account_type="CASH",
    batch_idempotency_key=None,
) -> list[MemberContribution]:
    """Record multiple member gifts in one atomic batch."""
    import uuid

    if campaign.status != CampaignStatus.OPEN:
        raise ContributionServiceError("Campaign must be open for bulk entry.")
    if not entries:
        raise ContributionServiceError("Enter at least one amount to record.")
    contribution_date = contribution_date or timezone.localdate()
    batch_key = batch_idempotency_key or str(uuid.uuid4())
    created = []
    for index, entry in enumerate(entries):
        member = entry["member"]
        amount = entry["amount"]
        notes = entry.get("notes") or ""
        line_key = contribution_idempotency_key(
            "bulk",
            campaign.pk,
            batch_key,
            index,
            member.pk,
            amount,
            contribution_date,
        )
        created.append(
            record_member_contribution(
                campaign,
                member=member,
                amount=amount,
                performed_by=performed_by,
                contribution_date=contribution_date,
                notes=notes,
                payment_account_type=payment_account_type,
                idempotency_key=line_key,
            )
        )
    return created


def build_bulk_entry_rows(campaign) -> list[dict]:
    targets = selectors.member_target_map(campaign)
    totals = {
        row["member_id"]: row["total"]
        for row in selectors.campaign_member_totals(campaign)
    }
    rows = []
    for member in selectors.active_members_for_church(campaign.church):
        paid = totals.get(member.pk, Decimal("0.00"))
        override = targets.get(member.pk)
        target = override if override is not None else campaign.default_member_target
        remaining = None
        if target is not None:
            remaining = max(Decimal("0.00"), _quantize(target) - _quantize(paid))
        rows.append(
            {
                "member": member,
                "paid": _quantize(paid),
                "override_target": override,
                "target": _quantize(target) if target is not None else None,
                "remaining": remaining,
            }
        )
    return rows


@db_transaction.atomic
def save_member_targets(campaign, *, targets: dict, performed_by) -> int:
    """Save per-member target overrides. Empty/zero removes override."""
    if campaign.status == CampaignStatus.ARCHIVED:
        raise ContributionServiceError("Archived campaigns cannot be edited.")
    from contributions.models import MemberCampaignTarget

    saved = 0
    for member_id, amount in targets.items():
        member = selectors.active_members_for_church(campaign.church).filter(pk=member_id).first()
        if not member:
            continue
        if amount in (None, "", 0, Decimal("0")):
            MemberCampaignTarget.objects.filter(campaign=campaign, member=member).delete()
            continue
        amount = _quantize(amount)
        if amount <= 0:
            MemberCampaignTarget.objects.filter(campaign=campaign, member=member).delete()
            continue
        repo.upsert_member_target(campaign, member, amount, updated_by=performed_by)
        saved += 1
    return saved


def member_progress(campaign, member) -> dict:
    target = selectors.member_target_for(campaign, member)
    paid = selectors.member_total_for_campaign(campaign, member)
    remaining = None
    progress_pct = None
    if target is not None:
        target = _quantize(target)
        remaining = max(Decimal("0.00"), target - paid)
        if target > 0:
            progress_pct = min(100, float((paid / target) * 100))
    return {
        "target": target,
        "paid": paid,
        "remaining": remaining,
        "progress_pct": progress_pct,
    }


def can_view_member_contributions(user, member) -> bool:
    from permissions.checks import can_manage_finances, can_view_contribution_reports

    if can_manage_finances(user) or can_view_contribution_reports(user):
        return True
    linked = getattr(user, "member_id", None)
    return linked is not None and linked == member.pk


def can_view_own_contributions(user, member) -> bool:
    from permissions.checks import can_view_own_contributions

    if not can_view_own_contributions(user):
        return False
    linked = getattr(user, "member_id", None)
    return linked is not None and linked == member.pk


def portal_open_campaign_cards(member) -> list[dict]:
    campaigns = selectors.open_portal_campaigns(member.church)
    cards = []
    for campaign in campaigns:
        summary = build_campaign_summary(campaign)
        member_total = selectors.member_total_for_campaign(campaign, member)
        progress = member_progress(campaign, member)
        days = campaign.days_until_deadline
        cards.append(
            {
                "campaign": campaign,
                "member_total": member_total,
                "member_target": progress["target"],
                "member_remaining": progress["remaining"],
                "member_progress_pct": progress["progress_pct"],
                "days_until_deadline": days,
                "is_urgent": days is not None and 0 <= days <= 7,
                "is_overdue": campaign.is_past_deadline,
                "show_church_progress": campaign.show_church_progress,
                "church_total": summary["total_raised"] if campaign.show_church_progress else None,
                "progress_pct": summary["progress_pct"] if campaign.show_church_progress else None,
                "target_amount": summary["target_amount"] if campaign.show_church_progress else None,
            }
        )
    return cards


@db_transaction.atomic
def remit_district_funeral_campaign(
    campaign,
    *,
    performed_by,
    amount=None,
    payment_account_type="CASH",
    notes="",
    idempotency_key=None,
):
    """Send designated funeral holdings to cash/bank for district (not welfare)."""
    from transactions.idempotency import (
        IdempotencyReplay,
        claim_financial_idempotency,
        complete_financial_idempotency,
    )
    from transactions.services import record_designated_holding_remittance

    if campaign.kind != CampaignKind.DISTRICT_FUNERAL:
        raise ContributionServiceError(
            "Only district funeral collections can be remitted this way."
        )
    if campaign.status == CampaignStatus.ARCHIVED:
        raise ContributionServiceError("Archived campaigns cannot be remitted.")
    if selectors.campaign_has_pending_remittance(campaign):
        raise ContributionServiceError(
            "A funeral remittance journal is already pending approval."
        )
    summary = build_campaign_summary(campaign)
    outstanding = summary["outstanding_to_district"]
    if outstanding <= 0:
        raise ContributionServiceError("There is nothing outstanding to remit.")
    amount = _quantize(amount if amount is not None else outstanding)
    if amount <= 0 or amount > outstanding:
        raise ContributionServiceError(
            f"Remit amount must be between 0.01 and {outstanding}."
        )
    holding = campaign.offering_category.account
    key = idempotency_key or contribution_idempotency_key(
        "funeral-remit", campaign.pk, amount, payment_account_type
    )
    try:
        idem_record = claim_financial_idempotency(
            campaign.church,
            performed_by,
            "CONTRIBUTION",
            key,
        )
    except IdempotencyReplay as replay:
        existing = selectors.remittance_for_transaction(replay.existing_transaction)
        if existing:
            return existing
        raise ContributionServiceError(
            "This remittance was already recorded; refresh and continue."
        ) from replay
    narration = notes.strip() or f"District funeral remittance — {campaign.name}"
    try:
        trx = record_designated_holding_remittance(
            campaign.church,
            performed_by,
            holding,
            amount,
            payment_account_type=payment_account_type,
            description=narration[:200],
        )
    except ValueError as exc:
        raise ContributionServiceError(str(exc)) from exc
    row = repo.create_campaign_remittance(
        campaign=campaign,
        amount=amount,
        transaction=trx,
        remitted_by=performed_by,
        notes=notes.strip()[:255],
    )
    complete_financial_idempotency(idem_record, trx)
    return row


CAMPAIGN_REGISTER_ROW_LIMIT = 500


def build_campaign_register(churches, start, end) -> dict:
    """Hierarchy-aware campaign snapshot for Report Center (read-only)."""
    from contributions.models import CampaignRemittance, MemberContribution

    church_list = list(churches)
    headers = [
        "Church",
        "District",
        "Campaign",
        "Code",
        "Type",
        "Status",
        "Deadline",
        "Raised",
        "Remitted",
        "Outstanding",
    ]
    if not church_list:
        return {
            "title": "Campaign Register",
            "headers": headers,
            "rows": [],
            "summary": {"church_count": 0, "campaign_count": 0, "raised": Decimal("0.00"), "remitted": Decimal("0.00")},
            "truncated": False,
        }
    gift_ids = MemberContribution.objects.filter(
        campaign__church__in=church_list,
        contribution_date__gte=start,
        contribution_date__lte=end,
        transaction__approval_status="APPROVED",
        transaction__is_voided=False,
    ).values_list("campaign_id", flat=True)
    remit_ids = CampaignRemittance.objects.filter(
        campaign__church__in=church_list,
        transaction__date__gte=start,
        transaction__date__lte=end,
        transaction__is_voided=False,
    ).exclude(transaction__approval_status="REJECTED").values_list("campaign_id", flat=True)
    qs = (
        ContributionCampaign.objects.filter(church__in=church_list)
        .filter(
            Q(deadline__gte=start, deadline__lte=end)
            | Q(pk__in=gift_ids)
            | Q(pk__in=remit_ids)
        )
        .select_related("church", "church__district")
        .order_by("church__name", "deadline", "name")
        .distinct()
    )
    total = qs.count()
    truncated = total > CAMPAIGN_REGISTER_ROW_LIMIT
    raised_total = Decimal("0.00")
    remitted_total = Decimal("0.00")
    rows = []
    for campaign in qs[:CAMPAIGN_REGISTER_ROW_LIMIT]:
        summary = build_campaign_summary(campaign)
        raised_total += summary["total_raised"]
        remitted_total += summary["remitted_total"]
        rows.append(
            [
                campaign.church.name,
                campaign.church.district.name if campaign.church.district_id else "",
                campaign.name,
                campaign.code,
                campaign.get_kind_display(),
                campaign.get_status_display(),
                campaign.deadline,
                summary["total_raised"],
                summary["remitted_total"],
                summary["outstanding_to_district"],
            ]
        )
    if truncated:
        rows.append(["", "", "… truncated", f"Showing {CAMPAIGN_REGISTER_ROW_LIMIT} of {total}", "", "", "", "", "", ""])
    return {
        "title": "Campaign Register",
        "headers": headers,
        "rows": rows,
        "truncated": truncated,
        "summary": {
            "church_count": len(church_list),
            "campaign_count": total,
            "raised": raised_total,
            "remitted": remitted_total,
        },
    }


def build_portal_campaign_page(member, campaign) -> dict:
    summary = build_campaign_summary(campaign)
    contributions = list(
        selectors.contributions_for_campaign(campaign, member=member).order_by("-contribution_date")
    )
    member_total = selectors.member_total_for_campaign(campaign, member)
    progress = member_progress(campaign, member)
    return {
        "campaign": campaign,
        "contributions": contributions,
        "member_total": member_total,
        "member_target": progress["target"],
        "member_remaining": progress["remaining"],
        "member_progress_pct": progress["progress_pct"],
        "summary": summary if campaign.show_church_progress else {
            "total_raised": None,
            "target_amount": None,
            "progress_pct": None,
            "days_until_deadline": summary["days_until_deadline"],
            "is_past_deadline": summary["is_past_deadline"],
        },
        "show_church_progress": campaign.show_church_progress,
    }
