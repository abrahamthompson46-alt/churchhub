"""Read/query helpers for Platform Owner marketing."""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from accounts.models import User
from sitecontrol.models import (
    Denomination,
    MarketingAsset,
    MarketingCampaign,
    MarketingLead,
    MarketingSettings,
)


def marketing_settings():
    return MarketingSettings.objects.filter(singleton_id=1).first()


def campaign_list():
    return MarketingCampaign.objects.annotate(
        lead_count=Count("leads"),
        converted_count=Count("leads", filter=Q(leads__status="CONVERTED")),
    ).order_by("-created_at")


def active_campaigns():
    return MarketingCampaign.objects.filter(status="ACTIVE").order_by("name")


def campaign_by_slug(slug):
    return MarketingCampaign.objects.filter(slug=slug).first()


def get_campaign_or_404(pk):
    return get_object_or_404(MarketingCampaign, pk=pk)


def lead_list():
    return MarketingLead.objects.select_related(
        "campaign", "denomination", "assigned_to"
    ).order_by("-created_at")


def get_lead_or_404(pk):
    return get_object_or_404(
        MarketingLead.objects.select_related(
            "campaign", "denomination", "assigned_to"
        ),
        pk=pk,
    )


def lead_by_pk(pk):
    return MarketingLead.objects.select_related("campaign", "denomination").filter(
        pk=pk
    ).first()


def prior_leads_for_email(email):
    return MarketingLead.objects.filter(contact_email__iexact=email)


def asset_list(*, include_archived=True):
    qs = MarketingAsset.objects.select_related("created_by")
    if not include_archived:
        qs = qs.exclude(status="ARCHIVED")
    return qs.order_by("sort_order", "title")


def get_asset_or_404(pk):
    return get_object_or_404(MarketingAsset, pk=pk)


def public_denominations():
    return Denomination.objects.filter(
        is_active=True, allow_public_registration=True
    ).order_by("name")


def public_denomination_exists(pk):
    return Denomination.objects.filter(
        pk=pk,
        is_active=True,
        allow_public_registration=True,
    ).exists()


def platform_owners():
    return User.objects.filter(
        is_active=True,
        is_platform_user=True,
        platform_role="OWNER",
    ).order_by("first_name", "last_name", "username")


def dashboard_counts():
    leads = MarketingLead.objects.all()
    return {
        "total_leads": leads.count(),
        "new_leads": leads.filter(status="NEW").count(),
        "qualified_leads": leads.filter(status="QUALIFIED").count(),
        "converted_leads": leads.filter(status="CONVERTED").count(),
        "active_campaigns": MarketingCampaign.objects.filter(status="ACTIVE").count(),
        "approved_assets": MarketingAsset.objects.filter(status="APPROVED").count(),
    }


def closed_leads_before(cutoff):
    return MarketingLead.objects.filter(
        status="CLOSED",
        anonymized_at__isnull=True,
        created_at__lt=cutoff,
    )
