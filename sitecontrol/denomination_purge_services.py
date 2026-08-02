"""Irreversible denomination purge — hard-delete tenant boundary and related data."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from accounts.models import User
from organization.models import Church, Conference
from sitecontrol import selectors
from sitecontrol.models import Denomination, TenantApplication


class DenominationPurgeError(Exception):
    """Raised when a denomination cannot be purged."""


@dataclass(frozen=True)
class DenominationPurgePreview:
    conference_count: int
    church_count: int
    institution_user_count: int
    application_count: int


def denomination_purge_preview(denomination: Denomination) -> DenominationPurgePreview:
    churches = selectors.churches_for_denomination(denomination)
    church_ids = churches.values_list("pk", flat=True)
    conference_ids = Conference.objects.filter(denomination=denomination).values_list(
        "pk", flat=True
    )
    institution_users = User.objects.filter(is_platform_user=False).filter(
        Q(church_id__in=church_ids)
        | Q(denomination=denomination)
        | Q(scope_conference_id__in=conference_ids)
        | Q(scope_zone__conference__denomination=denomination)
        | Q(scope_district__zone__conference__denomination=denomination)
    )
    return DenominationPurgePreview(
        conference_count=selectors.conference_count_for_denomination(denomination),
        church_count=churches.count(),
        institution_user_count=institution_users.distinct().count(),
        application_count=TenantApplication.objects.filter(denomination=denomination).count(),
    )


def validate_denomination_purge(denomination: Denomination) -> None:
    if denomination.is_default:
        raise DenominationPurgeError(
            "The default denomination cannot be permanently deleted."
        )
    if (
        Denomination.objects.filter(is_active=True).count() <= 1
        and denomination.is_active
    ):
        raise DenominationPurgeError(
            "Cannot delete the only active denomination on the platform."
        )


def _raw_delete_queryset(qs) -> None:
    if qs.exists():
        qs._raw_delete(qs.db)


def _purge_church(church: Church) -> None:
    """Remove a church and dependent rows that block CASCADE deletion."""
    from contributions.models import ContributionCampaign
    from ledger.models import LedgerCategory
    from members.models import Member
    from portal.models import SpiritualSubmission, SpiritualSubmissionAuditLog
    from sitecontrol.models import TenantSubscription
    from transactions.models import (
        Account,
        FinancialAuditLog,
        OfferingCategory,
        Transaction,
        TransactionLine,
    )

    church_id = church.pk
    db = church._state.db

    submission_ids = SpiritualSubmission.objects.filter(church_id=church_id).values_list(
        "pk", flat=True
    )
    _raw_delete_queryset(
        SpiritualSubmissionAuditLog.objects.filter(submission_id__in=submission_ids)
    )
    SpiritualSubmission.objects.filter(church_id=church_id).delete()
    _raw_delete_queryset(FinancialAuditLog.objects.filter(church_id=church_id))

    ContributionCampaign.objects.filter(church_id=church_id).delete()
    TransactionLine.objects.filter(transaction__church_id=church_id).delete()
    Transaction.objects.filter(church_id=church_id).delete()
    LedgerCategory.objects.filter(church_id=church_id).delete()
    OfferingCategory.objects.filter(church_id=church_id).delete()
    TenantSubscription.objects.filter(church_id=church_id).delete()
    Account.objects.filter(church_id=church_id).delete()
    Member.all_objects.filter(church_id=church_id).delete()

    Church.objects.filter(pk=church_id).delete()


@transaction.atomic
def purge_denomination_completely(
    denomination: Denomination,
    *,
    performed_by,
    reason: str = "",
) -> dict:
    """
    Permanently delete a denomination, its org tree, churches, and institution users.

    Platform audit entries are retained with denomination set to NULL. This action
    cannot be undone.
    """
    validate_denomination_purge(denomination)

    preview = denomination_purge_preview(denomination)
    churches = list(selectors.churches_for_denomination(denomination))
    church_ids = [church.pk for church in churches]
    conference_ids = list(
        Conference.objects.filter(denomination=denomination).values_list("pk", flat=True)
    )

    institution_users = User.objects.filter(is_platform_user=False).filter(
        Q(church_id__in=church_ids)
        | Q(denomination=denomination)
        | Q(scope_conference_id__in=conference_ids)
        | Q(scope_zone__conference__denomination=denomination)
        | Q(scope_district__zone__conference__denomination=denomination)
    )
    deleted_users = institution_users.distinct().count()
    institution_users.delete()

    deleted_applications = TenantApplication.objects.filter(
        denomination=denomination
    ).delete()[0]

    for church in churches:
        _purge_church(church)

    denom_name = denomination.name
    denom_code = denomination.code
    denom_pk = denomination.pk

    Conference.objects.filter(denomination=denomination).delete()
    denomination.delete()

    return {
        "denomination_id": str(denom_pk),
        "denomination_name": denom_name,
        "denomination_code": denom_code,
        "reason": reason,
        "performed_by_id": str(performed_by.pk) if performed_by else None,
        "deleted_conferences": preview.conference_count,
        "deleted_churches": preview.church_count,
        "deleted_institution_users": deleted_users,
        "deleted_applications": deleted_applications,
    }
