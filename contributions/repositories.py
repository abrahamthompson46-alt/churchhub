"""Persistence helpers for contribution campaigns."""

from contributions.models import ContributionCampaign, MemberCampaignTarget, MemberContribution


def save_campaign(campaign, *, update_fields=None):
    if update_fields:
        campaign.save(update_fields=update_fields)
    else:
        campaign.save()


def create_contribution(**fields):
    return MemberContribution.objects.create(**fields)


def save_contribution(contribution, *, update_fields=None):
    if update_fields:
        contribution.save(update_fields=update_fields)
    else:
        contribution.save()


def upsert_member_target(campaign, member, target_amount, *, updated_by=None):
    obj, _ = MemberCampaignTarget.objects.update_or_create(
        campaign=campaign,
        member=member,
        defaults={"target_amount": target_amount, "updated_by": updated_by},
    )
    return obj


def reminder_exists(campaign, user, reminder_key):
    from contributions.models import CampaignDeadlineReminder

    return CampaignDeadlineReminder.objects.filter(
        campaign=campaign,
        user=user,
        reminder_key=reminder_key,
    ).exists()


def create_reminder_log(campaign, user, reminder_key, *, notification_sent=False, email_sent=False):
    from contributions.models import CampaignDeadlineReminder

    return CampaignDeadlineReminder.objects.create(
        campaign=campaign,
        user=user,
        reminder_key=reminder_key,
        notification_sent=notification_sent,
        email_sent=email_sent,
    )
