"""Church-scoped reads for contribution campaigns."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404

from church_system.church_scope import filter_by_church
from contributions.models import CampaignStatus, ContributionCampaign, MemberContribution
from members.models import Member, MembershipStatus


def campaigns_for_church(church, *, status=None):
    qs = ContributionCampaign.objects.filter(church=church).select_related(
        "offering_category",
        "created_by",
    )
    if status:
        if isinstance(status, (list, tuple, set)):
            qs = qs.filter(status__in=status)
        else:
            qs = qs.filter(status=status)
    return qs


def get_campaign_or_404(request, pk):
    qs = filter_by_church(ContributionCampaign.objects.all(), request, church_field="church")
    return get_object_or_404(qs.select_related("offering_category", "church"), pk=pk)


def open_portal_campaigns(church):
    return campaigns_for_church(
        church,
        status=CampaignStatus.OPEN,
    ).filter(portal_visible=True)


def contributions_for_campaign(campaign, *, member=None, approved_only=True):
    qs = MemberContribution.objects.filter(campaign=campaign).select_related(
        "member",
        "transaction",
        "recorded_by",
    )
    if member is not None:
        qs = qs.filter(member=member)
    if approved_only:
        qs = qs.filter(
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
        )
    return qs


def campaign_total_raised(campaign, *, approved_only=True) -> Decimal:
    qs = contributions_for_campaign(campaign, approved_only=approved_only)
    total = qs.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
    return Decimal(str(total or "0")).quantize(Decimal("0.01"))


def member_total_for_campaign(campaign, member, *, approved_only=True) -> Decimal:
    qs = contributions_for_campaign(campaign, member=member, approved_only=approved_only)
    total = qs.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
    return Decimal(str(total or "0")).quantize(Decimal("0.01"))


def campaign_contributor_count(campaign, *, approved_only=True) -> int:
    qs = contributions_for_campaign(campaign, approved_only=approved_only)
    return qs.values("member_id").distinct().count()


def campaign_member_totals(campaign, *, approved_only=True):
    qs = contributions_for_campaign(campaign, approved_only=approved_only)
    return (
        qs.values("member_id", "member__first_name", "member__last_name", "member__membership_number")
        .annotate(total=Sum("amount"), gift_count=Count("id"))
        .order_by("-total", "member__last_name", "member__first_name")
    )


def active_members_for_church(church):
    inactive = {
        MembershipStatus.TRANSFERRED,
        MembershipStatus.DECEASED,
        MembershipStatus.FORMER,
    }
    return Member.objects.filter(church=church, is_deleted=False).exclude(
        membership_status__in=inactive,
    )


def members_without_contribution(campaign, *, approved_only=True):
    contributed_ids = (
        contributions_for_campaign(campaign, approved_only=approved_only)
        .values_list("member_id", flat=True)
        .distinct()
    )
    return active_members_for_church(campaign.church).exclude(pk__in=contributed_ids).order_by(
        "last_name",
        "first_name",
    )


def get_portal_campaign_for_member(member, campaign_id):
    try:
        campaign = ContributionCampaign.objects.select_related("offering_category").get(
            pk=campaign_id,
            church=member.church,
            status=CampaignStatus.OPEN,
            portal_visible=True,
        )
    except ContributionCampaign.DoesNotExist as exc:
        raise Http404 from exc
    return campaign


def member_target_map(campaign) -> dict:
    from contributions.models import MemberCampaignTarget

    return {
        row["member_id"]: row["target_amount"]
        for row in MemberCampaignTarget.objects.filter(campaign=campaign).values("member_id", "target_amount")
    }


def member_target_for(campaign, member):
    from contributions.models import MemberCampaignTarget

    override = MemberCampaignTarget.objects.filter(campaign=campaign, member=member).first()
    if override:
        return override.target_amount
    return campaign.default_member_target


def open_campaigns_for_reminders():
    return ContributionCampaign.objects.filter(
        status=CampaignStatus.OPEN,
        portal_visible=True,
    ).select_related("church")
