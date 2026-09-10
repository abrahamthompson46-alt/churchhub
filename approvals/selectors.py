"""Scoped reads for approval cases and delegations."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from approvals.models import ApprovalCase, ApprovalDelegation, ApprovalPolicy
from church_system.church_scope import filter_by_church
from permissions.scoping import get_manageable_churches


def scoped_cases_qs(user, request=None):
    churches = get_manageable_churches(user)
    if not churches.exists():
        return ApprovalCase.objects.none()
    qs = ApprovalCase.objects.select_related("transaction", "church", "maker").filter(
        church__in=churches
    )
    if request is not None:
        qs = filter_by_church(qs, request)
    return qs


def case_for_user(user, pk, request=None):
    return scoped_cases_qs(user, request=request).filter(pk=pk).first()


def policy_for_church(church):
    return ApprovalPolicy.objects.filter(church=church).first()


def active_delegations_for_grantee(user, church):
    today = timezone.localdate()
    return ApprovalDelegation.objects.filter(
        grantee=user,
        church=church,
        is_revoked=False,
        valid_from__lte=today,
        valid_until__gte=today,
        permission_codename="approve_transactions",
    ).select_related("grantor")


def scoped_delegations_qs(user, request=None):
    churches = get_manageable_churches(user)
    if not churches.exists():
        return ApprovalDelegation.objects.none()
    qs = ApprovalDelegation.objects.select_related("grantor", "grantee", "church").filter(
        Q(church__in=churches) & (Q(grantor=user) | Q(grantee=user))
    )
    if request is not None:
        qs = filter_by_church(qs, request)
    return qs
