"""Scoped reads for risk alerts and policy."""

from __future__ import annotations

from intelligence.models import RiskAlert, RiskPolicy
from church_system.church_scope import filter_by_church
from permissions.scoping import get_manageable_churches


def scoped_alerts_qs(user, request=None):
    churches = get_manageable_churches(user)
    if not churches.exists():
        return RiskAlert.objects.none()
    qs = RiskAlert.objects.select_related("transaction", "church", "reviewed_by").filter(
        church__in=churches
    )
    if request is not None:
        qs = filter_by_church(qs, request)
    return qs


def alert_for_user(user, pk, request=None):
    return scoped_alerts_qs(user, request=request).filter(pk=pk).first()


def policy_for_church(church):
    return RiskPolicy.objects.filter(church=church).first()
