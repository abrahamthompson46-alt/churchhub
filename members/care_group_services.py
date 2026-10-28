"""Location care groups and one-to-one member pairing."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from members import repositories as repo
from members.models import (
    CareGroupMembership,
    CareGroupRole,
    CarePartnership,
)
from members.services import MemberServiceError, log_member_audit


def _ordered_members(first, second):
    if first.pk == second.pk:
        raise MemberServiceError("A member cannot be paired with themselves.")
    if first.pk < second.pk:
        return first, second
    return second, first


def active_memberships(group):
    return group.memberships.filter(left_at__isnull=True).select_related("member")


def active_membership_for_member(member):
    return (
        CareGroupMembership.objects.filter(member=member, left_at__isnull=True)
        .select_related("group", "group__location")
        .first()
    )


def active_partnerships(group):
    return group.partnerships.filter(is_active=True).select_related("member_a", "member_b")


def active_partnership_for_member(member, group=None):
    qs = CarePartnership.objects.filter(is_active=True).filter(
        Q(member_a=member) | Q(member_b=member)
    )
    if group is not None:
        qs = qs.filter(group=group)
    return qs.select_related("member_a", "member_b", "group").first()


@transaction.atomic
def save_member_location(*, location, user, is_new=False):
    repo.save_member_location(location)
    log_member_audit(
        location.church,
        "LOCATION_CREATE" if is_new else "LOCATION_UPDATE",
        performed_by=user,
        details={"location_id": str(location.pk), "name": location.name},
    )
    return location


@transaction.atomic
def delete_member_location(location, user):
    if location.care_groups.exists():
        raise MemberServiceError("Cannot remove a location that still has care groups.")
    name = location.name
    church = location.church
    location_id = location.pk
    repo.delete_member_location(location)
    log_member_audit(
        church,
        "LOCATION_DELETE",
        performed_by=user,
        details={"location_id": str(location_id), "name": name},
    )


@transaction.atomic
def save_care_group(*, group, user, is_new=False):
    repo.save_care_group(group)
    log_member_audit(
        group.church,
        "GROUP_CREATE" if is_new else "GROUP_UPDATE",
        performed_by=user,
        details={
            "group_id": str(group.pk),
            "name": group.name,
            "location_id": str(group.location_id),
        },
    )
    if group.leader_id:
        existing = active_memberships(group).filter(member_id=group.leader_id).first()
        if existing:
            if existing.role != CareGroupRole.LEADER:
                existing.role = CareGroupRole.LEADER
                repo.save_care_membership(existing)
        else:
            add_member_to_care_group(group=group, member=group.leader, user=user, role=CareGroupRole.LEADER)
    return group


@transaction.atomic
def delete_care_group(group, user):
    if active_memberships(group).exists():
        raise MemberServiceError("Remove all members before deleting this care group.")
    name = group.name
    church = group.church
    group_id = group.pk
    repo.delete_care_group(group)
    log_member_audit(
        church,
        "GROUP_DELETE",
        performed_by=user,
        details={"group_id": str(group_id), "name": name},
    )


@transaction.atomic
def add_member_to_care_group(*, group, member, user, role=CareGroupRole.MEMBER):
    if not group.is_active:
        raise MemberServiceError("Cannot add members to an inactive care group.")
    if member.church_id != group.church_id:
        raise MemberServiceError("Member must belong to the same church as the care group.")
    current = active_membership_for_member(member)
    if current:
        if current.group_id == group.pk:
            raise MemberServiceError("This member is already in this care group.")
        raise MemberServiceError(
            f"{member.full_name} is already in {current.group.name}. A member may belong to one care group."
        )
    membership = CareGroupMembership(group=group, member=member, role=role)
    repo.save_care_membership(membership)
    log_member_audit(
        group.church,
        "GROUP_JOIN",
        performed_by=user,
        member=member,
        details={"group_id": str(group.pk), "group_name": group.name, "role": role},
    )
    return membership


@transaction.atomic
def remove_member_from_care_group(*, group, member, user):
    membership = (
        CareGroupMembership.objects.filter(group=group, member=member, left_at__isnull=True)
        .select_related("member")
        .first()
    )
    if not membership:
        raise MemberServiceError("This member is not in the care group.")
    now = timezone.now()
    partnership = active_partnership_for_member(member, group=group)
    if partnership:
        _end_partnership(partnership, user=user, now=now)
    membership.left_at = now
    repo.save_care_membership(membership)
    if group.leader_id == member.pk:
        group.leader = None
        repo.save_care_group(group)
    log_member_audit(
        group.church,
        "GROUP_LEAVE",
        performed_by=user,
        member=member,
        details={"group_id": str(group.pk), "group_name": group.name},
    )
    return membership


def _end_partnership(partnership, *, user, now):
    partnership.is_active = False
    partnership.ended_at = now
    repo.save_care_partnership(partnership)
    log_member_audit(
        partnership.group.church,
        "GROUP_UNPAIR",
        performed_by=user,
        member=partnership.member_a,
        details={
            "group_id": str(partnership.group_id),
            "partnership_id": str(partnership.pk),
            "member_a": str(partnership.member_a_id),
            "member_b": str(partnership.member_b_id),
        },
    )


@transaction.atomic
def pair_care_members(*, group, first, second, user, notes=""):
    if not group.is_active:
        raise MemberServiceError("Cannot pair members in an inactive care group.")
    member_a, member_b = _ordered_members(first, second)
    for person in (member_a, member_b):
        membership = active_memberships(group).filter(member=person).first()
        if not membership:
            raise MemberServiceError(f"{person.full_name} is not in this care group.")
        existing = active_partnership_for_member(person, group=group)
        if existing:
            partner = existing.other_member(person)
            raise MemberServiceError(
                f"{person.full_name} is already paired with {partner.full_name}."
            )
    partnership = CarePartnership(
        group=group,
        member_a=member_a,
        member_b=member_b,
        notes=(notes or "")[:255],
        created_by=user,
        is_active=True,
    )
    repo.save_care_partnership(partnership)
    log_member_audit(
        group.church,
        "GROUP_PAIR",
        performed_by=user,
        member=member_a,
        details={
            "group_id": str(group.pk),
            "partnership_id": str(partnership.pk),
            "member_a": str(member_a.pk),
            "member_b": str(member_b.pk),
        },
    )
    return partnership


@transaction.atomic
def unpair_care_members(*, partnership, user):
    if not partnership.is_active:
        raise MemberServiceError("This partnership has already ended.")
    _end_partnership(partnership, user=user, now=timezone.now())
    return partnership
