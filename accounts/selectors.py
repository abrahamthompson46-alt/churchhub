"""
Read/query helpers for the accounts / identity domain.

Views, services, and forms call selectors for user, invitation, and activity
querysets. Authorization stays in permissions/scoping; writes stay in
repositories.
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404

from accounts.models import User, UserActivityLog, UserInvitation


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def user_by_pk(pk):
    return User.objects.get(pk=pk)


def get_user_or_none(pk):
    try:
        return User.objects.get(pk=pk)
    except User.DoesNotExist:
        return None


def username_exists_iexact(username) -> bool:
    return User.objects.filter(username__iexact=username).exists()


def active_email_exists_iexact(email) -> bool:
    return User.objects.filter(email__iexact=email, is_active=True).exists()


def filter_manageable_users(qs, *, q="", role="", status=""):
    """Apply directory search / role / active filters to a manageable-users qs."""
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    if role:
        qs = qs.filter(role=role)
    if status == "1":
        qs = qs.filter(is_active=True)
    elif status == "0":
        qs = qs.filter(is_active=False)
    return qs


def get_manageable_user_or_404(manager, pk):
    from accounts.permissions import get_manageable_users

    return get_object_or_404(get_manageable_users(manager), pk=pk)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def invitation_by_pk(pk):
    return UserInvitation.objects.get(pk=pk)


def invitation_for_update(pk):
    return UserInvitation.objects.select_for_update().get(pk=pk)


def get_invitation_by_token_or_404(token):
    return get_object_or_404(UserInvitation, token=token)


def invitation_with_scope_or_404(pk):
    return get_object_or_404(
        UserInvitation.objects.select_related(
            "church",
            "scope_district",
            "scope_zone",
            "scope_conference",
            "denomination",
        ),
        pk=pk,
    )


def pending_invitations_for_manager(manager, church_ids, *, limit=50):
    return (
        UserInvitation.objects.filter(
            is_accepted=False,
            revoked_at__isnull=True,
        )
        .filter(
            Q(church_id__in=church_ids)
            | Q(church__isnull=True, invited_by=manager)
            | Q(
                church__isnull=True,
                denomination_id__isnull=False,
                denomination_id=getattr(manager, "denomination_id", None),
            )
        )
        .select_related(
            "church",
            "invited_by",
            "scope_district",
            "scope_conference",
            "denomination",
        )
        .distinct()
        .order_by("-created_at")[:limit]
    )


def pending_invitations_for_church(church, *, limit=20):
    """Open (not accepted / not revoked) invitations for a church tenant."""
    return list(
        UserInvitation.objects.filter(
            church=church,
            is_accepted=False,
            revoked_at__isnull=True,
        )
        .select_related("invited_by")
        .order_by("-created_at")[:limit]
    )


def pending_invitation_for_email(*, email, church=None, denomination=None):
    qs = UserInvitation.objects.filter(
        email=email,
        is_accepted=False,
        revoked_at__isnull=True,
    )
    if church:
        qs = qs.filter(church=church)
    elif denomination:
        qs = qs.filter(denomination=denomination, church__isnull=True)
    else:
        qs = qs.filter(church__isnull=True, denomination__isnull=True)
    return qs.first()


# ---------------------------------------------------------------------------
# Activity logs
# ---------------------------------------------------------------------------


def recent_activity_for_user(user, *, limit=20):
    return user.activity_logs.order_by("-created_at")[:limit]


def activity_logs_for_users(user_qs, *, action="", limit=None):
    qs = (
        UserActivityLog.objects.filter(user__in=user_qs)
        .select_related("user", "performed_by")
        .order_by("-created_at")
    )
    if action:
        qs = qs.filter(action=action)
    return qs


# ---------------------------------------------------------------------------
# Organization / member lookups used by invite & manage forms
# ---------------------------------------------------------------------------


def empty_churches():
    from organization.models import Church

    return Church.objects.none()


def church_by_pk(pk):
    from organization.models import Church

    return Church.objects.filter(pk=pk).first()


def district_by_pk(pk):
    from organization.models import District

    return District.objects.filter(pk=pk).first()


def zone_by_pk(pk):
    from organization.models import Zone

    return Zone.objects.filter(pk=pk).first()


def conference_by_pk(pk):
    from organization.models import Conference

    return Conference.objects.filter(pk=pk).first()


def union_by_pk(pk):
    from organization.models import Union

    return Union.objects.filter(pk=pk).first()


def general_conference_by_pk(pk):
    from organization.models import GeneralConference

    return GeneralConference.objects.filter(pk=pk).first()


def denomination_by_pk(pk):
    from sitecontrol.models import Denomination

    return Denomination.objects.filter(pk=pk).first()


def empty_members():
    from members.models import Member

    return Member.objects.none()


def linkable_members_for_church(church, *, current_member_id=None):
    from members.models import Member

    if not church:
        return Member.objects.none()
    return (
        Member.objects.filter(church=church)
        .filter(Q(user_account__isnull=True) | Q(pk=current_member_id))
        .order_by("last_name", "first_name")
    )
