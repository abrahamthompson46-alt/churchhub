"""Persistence helpers for the platform marketing domain."""

from sitecontrol.models import (
    MarketingAsset,
    MarketingCampaign,
    MarketingLead,
    MarketingSettings,
)


def get_or_create_marketing_settings():
    return MarketingSettings.objects.get_or_create(singleton_id=1)


def create_campaign(**fields):
    return MarketingCampaign.objects.create(**fields)


def create_lead(**fields):
    return MarketingLead.objects.create(**fields)


def create_asset(**fields):
    return MarketingAsset.objects.create(**fields)


def save(instance, *, update_fields=None):
    if update_fields is None:
        instance.save()
    else:
        instance.save(update_fields=update_fields)
    return instance
