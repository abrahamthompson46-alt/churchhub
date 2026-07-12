"""Member management services."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from permissions.checks import can_view_all_churches
from permissions.scoping import get_manageable_churches

from members.models import (
    LeadershipRole,
    Member,
    MemberAuditLog,
    MembershipStatus,
    MemberTransfer,
    Record,
    RecordType,
    TransferStatus,
)


def log_member_audit(church, action, performed_by=None, member=None, details=None):
    return MemberAuditLog.objects.create(
        church=church,
        member=member,
        action=action,
        performed_by=performed_by,
        details=details or {},
    )


def can_process_transfer(user, transfer):
    """User may approve/complete a pending transfer into their manageable churches."""
    if transfer.status != TransferStatus.PENDING:
        return False
    if can_view_all_churches(user):
        manageable = get_manageable_churches(user)
        return manageable.filter(pk=transfer.to_church_id).exists()
    return bool(user.church_id and user.church_id == transfer.to_church_id)


def user_can_view_transfer(user, transfer):
    manageable = get_manageable_churches(user)
    return manageable.filter(
        Q(pk=transfer.from_church_id) | Q(pk=transfer.to_church_id)
    ).exists()


def find_duplicate_members(church, first_name, last_name, date_of_birth=None, phone="", exclude_pk=None):
    """Return potential duplicates for soft-match warnings."""
    qs = Member.objects.filter(
        church=church,
        first_name__iexact=(first_name or "").strip(),
        last_name__iexact=(last_name or "").strip(),
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    matches = []
    if date_of_birth:
        matches.extend(list(qs.filter(date_of_birth=date_of_birth)[:5]))
    phone = (phone or "").strip()
    if phone:
        phone_matches = Member.objects.filter(church=church, phone=phone)
        if exclude_pk:
            phone_matches = phone_matches.exclude(pk=exclude_pk)
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
    if phone and Member.objects.filter(church=church, phone=phone).exists():
        raise ValidationError({"phone": "A member with this phone number already exists in this church."})
    if membership_number and Member.objects.filter(
        church=church, membership_number=membership_number
    ).exists():
        raise ValidationError({
            "membership_number": "This membership number is already assigned in this church.",
        })

    member = Member(church=church, created_by=performed_by, **fields)
    member.full_clean()
    member.save()
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

    if phone and Member.objects.filter(church=member.church, phone=phone).exclude(pk=member.pk).exists():
        raise ValidationError({"phone": "A member with this phone number already exists in this church."})
    if membership_number and Member.objects.filter(
        church=member.church, membership_number=membership_number
    ).exclude(pk=member.pk).exists():
        raise ValidationError({
            "membership_number": "This membership number is already assigned in this church.",
        })

    changed = {}
    for key, value in fields.items():
        old = getattr(member, key)
        if old != value:
            changed[key] = {"from": str(old) if old is not None else None, "to": str(value) if value is not None else None}
            setattr(member, key, value)
    member.full_clean()
    member.save()
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
    pending = MemberTransfer.objects.filter(
        member=member,
        status=TransferStatus.PENDING,
    ).exists()
    if pending:
        raise ValueError("This member already has a pending transfer.")

    # Same denomination only when both conferences have denominations set
    from_denom = member.church.denomination
    to_denom = to_church.denomination
    if from_denom and to_denom and from_denom.pk != to_denom.pk:
        raise ValueError("Cannot transfer a member across denominations.")

    transfer = MemberTransfer.objects.create(
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
    LeadershipRole.objects.filter(
        member=member,
        church=from_church,
        is_active=True,
    ).update(is_active=False, end_date=transfer.transfer_date)

    # Outgoing church record: member left
    Record.objects.create(
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
    member.save(update_fields=[
        "church", "department", "family", "membership_status", "is_active", "updated_at",
    ])

    Record.objects.create(
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
    transfer.save(update_fields=["status", "processed_by", "processed_at", "notes", "updated_at"])

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
    transfer.save(update_fields=["status", "processed_by", "processed_at", "notes", "updated_at"])
    log_member_audit(
        transfer.from_church,
        "TRANSFER_REJECT",
        performed_by=processed_by,
        member=transfer.member,
        details={"transfer_id": str(transfer.pk), "notes": notes},
    )
    return transfer


def get_member_directory_stats(queryset, church=None):
    """Summary counts for member list filters."""
    transferred = 0
    if church is not None:
        transferred = MemberTransfer.objects.filter(
            from_church=church,
            status=TransferStatus.COMPLETED,
        ).count()
    else:
        transferred = queryset.filter(membership_status=MembershipStatus.TRANSFERRED).count()
    return {
        "total": queryset.count(),
        "active": queryset.filter(is_active=True, membership_status=MembershipStatus.ACTIVE).count(),
        "inactive": queryset.filter(
            Q(is_active=False) | Q(membership_status=MembershipStatus.INACTIVE)
        ).exclude(membership_status=MembershipStatus.TRANSFERRED).count(),
        "transferred": transferred,
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
