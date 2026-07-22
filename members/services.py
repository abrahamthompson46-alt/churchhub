"""Member management services."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from permissions.checks import can_process_transfers
from permissions.org_scope import church_in_user_scope
from permissions.scoping import get_manageable_churches

from members import repositories as repo
from members import selectors
from members.models import (
    Department,
    MembershipStatus,
    MemberSpiritualGift,
    MemberTransfer,
    RecordType,
    TransferStatus,
)


class MemberServiceError(Exception):
    """Business rule violation in member domain services."""


def log_member_audit(church, action, performed_by=None, member=None, details=None):
    return repo.create_audit_log(
        church=church,
        action=action,
        performed_by=performed_by,
        member=member,
        details=details,
    )


def can_process_transfer(user, transfer):
    """User may approve/complete a pending transfer into a church in their org scope."""
    if transfer.status != TransferStatus.PENDING:
        return False
    # can_process_transfers already includes manage_members implies + deny overrides.
    if not can_process_transfers(user):
        return False
    if church_in_user_scope(user, transfer.to_church):
        return True
    return bool(user.church_id and user.church_id == transfer.to_church_id)


def user_can_view_transfer(user, transfer):
    manageable = get_manageable_churches(user)
    return manageable.filter(
        Q(pk=transfer.from_church_id) | Q(pk=transfer.to_church_id)
    ).exists()


def find_duplicate_members(church, first_name, last_name, date_of_birth=None, phone="", exclude_pk=None):
    """Return potential duplicates for soft-match warnings."""
    qs = selectors.members_name_match(
        church, first_name, last_name, exclude_pk=exclude_pk
    )
    matches = []
    if date_of_birth:
        matches.extend(list(qs.filter(date_of_birth=date_of_birth)[:5]))
    phone = (phone or "").strip()
    if phone:
        phone_matches = selectors.members_with_phone(
            church, phone, exclude_pk=exclude_pk
        )
        matches.extend(list(phone_matches[:5]))
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for m in matches:
        if m.pk not in seen:
            seen.add(m.pk)
            unique.append(m)
    return unique


@transaction.atomic
def create_member(church, performed_by=None, **fields):
    """Create a member with validation, duplicate checks, and audit."""
    phone = (fields.get("phone") or "").strip()
    membership_number = (fields.get("membership_number") or "").strip()
    if phone and selectors.members_with_phone(church, phone).exists():
        raise ValidationError({"phone": "A member with this phone number already exists in this church."})
    if membership_number and selectors.members_with_membership_number(
        church, membership_number
    ).exists():
        raise ValidationError({
            "membership_number": "This membership number is already assigned in this church.",
        })

    member = repo.create_member(church=church, created_by=performed_by, **fields)
    log_member_audit(
        church,
        "CREATE",
        performed_by=performed_by,
        member=member,
        details={"name": member.full_name},
    )
    return member


@transaction.atomic
def update_member(member, performed_by=None, **fields):
    phone = (fields.get("phone") if "phone" in fields else member.phone) or ""
    phone = phone.strip()
    membership_number = (
        fields.get("membership_number") if "membership_number" in fields else member.membership_number
    ) or ""
    membership_number = membership_number.strip()

    if phone and selectors.members_with_phone(
        member.church, phone, exclude_pk=member.pk
    ).exists():
        raise ValidationError({"phone": "A member with this phone number already exists in this church."})
    if membership_number and selectors.members_with_membership_number(
        member.church, membership_number, exclude_pk=member.pk
    ).exists():
        raise ValidationError({
            "membership_number": "This membership number is already assigned in this church.",
        })

    changed = {}
    for key, value in fields.items():
        old = getattr(member, key)
        if old != value:
            changed[key] = {"from": str(old) if old is not None else None, "to": str(value) if value is not None else None}
            setattr(member, key, value)
    repo.save_member(member)
    if changed:
        action = "STATUS" if "membership_status" in changed else "UPDATE"
        log_member_audit(
            member.church,
            action,
            performed_by=performed_by,
            member=member,
            details=changed,
        )
    return member


def request_transfer(member, to_church, transfer_date, requested_by, reason=""):
    """Create a pending transfer request."""
    if member.church_id == to_church.pk:
        raise ValueError("Member is already in the destination church.")
    if member.membership_status == MembershipStatus.TRANSFERRED:
        raise ValueError("This member is already marked as transferred.")
    if selectors.pending_transfer_exists(member):
        raise ValueError("This member already has a pending transfer.")

    # Same denomination only when both conferences have denominations set
    from_denom = member.church.denomination
    to_denom = to_church.denomination
    if from_denom and to_denom and from_denom.pk != to_denom.pk:
        raise ValueError("Cannot transfer a member across denominations.")

    transfer = repo.create_transfer(
        member=member,
        from_church=member.church,
        to_church=to_church,
        transfer_date=transfer_date,
        reason=reason,
        requested_by=requested_by,
    )
    log_member_audit(
        member.church,
        "TRANSFER_REQUEST",
        performed_by=requested_by,
        member=member,
        details={
            "to_church_id": str(to_church.pk),
            "to_church": to_church.name,
            "transfer_id": str(transfer.pk),
        },
    )
    return transfer


@transaction.atomic
def complete_transfer(transfer, processed_by, notes=""):
    """Complete a transfer — move member to destination church."""
    if transfer.status != TransferStatus.PENDING:
        raise ValueError("Only pending transfers can be completed.")
    if not can_process_transfer(processed_by, transfer):
        raise PermissionDenied("You are not authorized to complete this transfer.")

    member = transfer.member
    from_church = transfer.from_church

    # End active leadership at the outgoing church
    repo.end_active_leadership_roles(
        member=member,
        church=from_church,
        end_date=transfer.transfer_date,
    )

    # Outgoing church record: member left
    repo.create_record(
        church=from_church,
        member=member,
        record_type=RecordType.TRANSFER,
        title=f"Transferred to {transfer.to_church.name}",
        description=transfer.reason or notes,
        event_date=transfer.transfer_date,
        created_by=processed_by,
    )

    member.church = transfer.to_church
    member.department = None
    member.family = None
    member.membership_status = MembershipStatus.ACTIVE
    member.is_active = True
    repo.save_member(
        member,
        update_fields=[
            "church",
            "department",
            "family",
            "membership_status",
            "is_active",
            "updated_at",
        ],
    )

    repo.create_record(
        church=transfer.to_church,
        member=member,
        record_type=RecordType.TRANSFER,
        title=f"Transfer from {from_church.name}",
        description=transfer.reason or notes,
        event_date=transfer.transfer_date,
        created_by=processed_by,
    )

    transfer.status = TransferStatus.COMPLETED
    transfer.processed_by = processed_by
    transfer.processed_at = timezone.now()
    if notes:
        transfer.notes = notes
    repo.save_transfer(
        transfer,
        update_fields=["status", "processed_by", "processed_at", "notes", "updated_at"],
    )

    log_member_audit(
        transfer.to_church,
        "TRANSFER_COMPLETE",
        performed_by=processed_by,
        member=member,
        details={
            "from_church_id": str(from_church.pk),
            "from_church": from_church.name,
            "transfer_id": str(transfer.pk),
        },
    )
    return transfer


@transaction.atomic
def reject_transfer(transfer, processed_by, notes=""):
    """Reject a pending transfer."""
    if transfer.status != TransferStatus.PENDING:
        raise ValueError("Only pending transfers can be rejected.")
    if not can_process_transfer(processed_by, transfer):
        raise PermissionDenied("You are not authorized to reject this transfer.")

    transfer.status = TransferStatus.REJECTED
    transfer.processed_by = processed_by
    transfer.processed_at = timezone.now()
    transfer.notes = notes
    repo.save_transfer(
        transfer,
        update_fields=["status", "processed_by", "processed_at", "notes", "updated_at"],
    )
    log_member_audit(
        transfer.from_church,
        "TRANSFER_REJECT",
        performed_by=processed_by,
        member=transfer.member,
        details={"transfer_id": str(transfer.pk), "notes": notes},
    )
    return transfer


def get_member_directory_stats(queryset, church=None):
    """Summary counts for member list filters (single aggregate query)."""
    from django.db.models import Count, Q

    from members.models import MembershipStatus

    if church is not None:
        transferred = selectors.completed_transfers_from_church_count(church)
        agg = queryset.aggregate(
            total=Count("pk"),
            active=Count(
                "pk",
                filter=Q(is_active=True, membership_status=MembershipStatus.ACTIVE),
            ),
            inactive=Count(
                "pk",
                filter=(
                    Q(is_active=False) | Q(membership_status=MembershipStatus.INACTIVE)
                )
                & ~Q(membership_status=MembershipStatus.TRANSFERRED),
            ),
        )
        return {
            "total": agg["total"] or 0,
            "active": agg["active"] or 0,
            "inactive": agg["inactive"] or 0,
            "transferred": transferred,
        }

    agg = queryset.aggregate(
        total=Count("pk"),
        active=Count(
            "pk",
            filter=Q(is_active=True, membership_status=MembershipStatus.ACTIVE),
        ),
        inactive=Count(
            "pk",
            filter=(
                Q(is_active=False) | Q(membership_status=MembershipStatus.INACTIVE)
            )
            & ~Q(membership_status=MembershipStatus.TRANSFERRED),
        ),
        transferred=Count(
            "pk",
            filter=Q(membership_status=MembershipStatus.TRANSFERRED),
        ),
    )
    return {
        "total": agg["total"] or 0,
        "active": agg["active"] or 0,
        "inactive": agg["inactive"] or 0,
        "transferred": agg["transferred"] or 0,
    }


def export_directory_rows(queryset):
    """Flat rows for CSV/Excel directory export."""
    headers = [
        "Membership Number",
        "First Name",
        "Last Name",
        "Gender",
        "Marital Status",
        "Date of Birth",
        "Age Group",
        "Phone",
        "Status",
        "Active",
        "Department",
        "Family",
        "Date Joined",
        "Baptism Date",
        "Baptism Place",
        "Certificate Number",
        "Address",
    ]
    rows = []
    for m in queryset.select_related("department", "family"):
        rows.append([
            m.membership_number,
            m.first_name,
            m.last_name,
            m.gender,
            m.marital_status,
            m.date_of_birth.isoformat() if m.date_of_birth else "",
            m.age_group,
            m.phone,
            m.membership_status,
            "Yes" if m.is_active else "No",
            m.department.name if m.department_id else "",
            m.family.name if m.family_id else "",
            m.date_joined.isoformat() if m.date_joined else "",
            m.baptism_date.isoformat() if m.baptism_date else "",
            m.baptism_place,
            m.baptism_certificate_number,
            m.address,
        ])
    return headers, rows


def department_delete_blockers(department: Department) -> list[str]:
    """Human-readable reasons a department cannot be hard-deleted."""
    blockers = []
    if selectors.members_assigned_to_department(department).exists():
        blockers.append("members are assigned")
    if selectors.active_leadership_roles_for_department(department).exists():
        blockers.append("active leadership roles exist")
    if repo.budgets_reference_department(department):
        blockers.append("budget lines reference this department")
    return blockers


def delete_department(department: Department, user) -> None:
    """
    Remove an unused department after dependency checks and audit.

    Hard delete is allowed only when no members, leadership, or budgets reference
    the row. Soft-delete is not implemented for departments (Planned).
    """
    blockers = department_delete_blockers(department)
    if blockers:
        raise MemberServiceError(
            "Cannot delete department: " + "; ".join(blockers) + "."
        )
    log_member_audit(
        department.church,
        "DEPARTMENT_DELETE",
        performed_by=user,
        details={
            "department_id": str(department.pk),
            "department_name": department.name,
        },
    )
    repo.delete_department(department)


def unassign_spiritual_gift(assignment: MemberSpiritualGift, user) -> None:
    """Remove a spiritual-gift assignment with member audit trail."""
    log_member_audit(
        assignment.member.church,
        "GIFT_UNASSIGN",
        performed_by=user,
        member=assignment.member,
        details={
            "gift": assignment.gift.name,
            "assignment_id": str(assignment.pk),
        },
    )
    repo.delete_gift_assignment(assignment)
