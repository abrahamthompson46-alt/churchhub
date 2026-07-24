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

    from members.models import INACTIVE_MEMBERSHIP_STATUSES, MembershipStatus

    inactive_statuses = [
        s for s in INACTIVE_MEMBERSHIP_STATUSES if s != MembershipStatus.TRANSFERRED
    ]
    inactive_q = (
        Q(is_active=False) | Q(membership_status__in=inactive_statuses)
    ) & ~Q(membership_status=MembershipStatus.TRANSFERRED)

    if church is not None:
        transferred = selectors.completed_transfers_from_church_count(church)
        agg = queryset.aggregate(
            total=Count("pk"),
            active=Count(
                "pk",
                filter=Q(is_active=True, membership_status=MembershipStatus.ACTIVE),
            ),
            inactive=Count("pk", filter=inactive_q),
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
        inactive=Count("pk", filter=inactive_q),
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


def delete_department(department: Department, user, *, reason="") -> None:
    """
    Soft-delete an unused department after dependency checks and audit.
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
            "soft_delete": True,
            "reason": reason,
        },
    )
    department.soft_delete(user=user, reason=reason or "Department removed")


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


EXPORT_MAX_ROWS = 5000


def capped_queryset(qs, *, limit=EXPORT_MAX_ROWS):
    """Return (queryset_or_list_slice, truncated_bool, total_count)."""
    total = qs.count()
    if total <= limit:
        return qs, False, total
    return qs[:limit], True, total


def export_directory_rows(queryset):
    """Flat rows for CSV/Excel directory export (capped)."""
    headers = [
        "Membership Number",
        "First Name",
        "Middle Name",
        "Last Name",
        "Preferred Name",
        "Gender",
        "Marital Status",
        "Date of Birth",
        "Age Group",
        "Phone",
        "Email",
        "Status",
        "Active",
        "Department",
        "Family",
        "Family Role",
        "Date Joined",
        "Baptism Date",
        "Baptism Place",
        "Certificate Number",
        "Emergency Contact",
        "Emergency Phone",
        "Address",
    ]
    capped, truncated, total = capped_queryset(queryset)
    rows = []
    for m in capped.select_related("department", "family"):
        rows.append([
            m.membership_number,
            m.first_name,
            getattr(m, "middle_name", "") or "",
            m.last_name,
            getattr(m, "preferred_name", "") or "",
            m.gender,
            m.marital_status,
            m.date_of_birth.isoformat() if m.date_of_birth else "",
            m.age_group,
            m.phone,
            getattr(m, "email", "") or "",
            m.membership_status,
            "Yes" if m.is_active else "No",
            m.department.name if m.department_id else "",
            m.family.name if m.family_id else "",
            getattr(m, "family_relationship", "") or "",
            m.date_joined.isoformat() if m.date_joined else "",
            m.baptism_date.isoformat() if m.baptism_date else "",
            m.baptism_place,
            m.baptism_certificate_number,
            getattr(m, "emergency_contact_name", "") or "",
            getattr(m, "emergency_contact_phone", "") or "",
            m.address,
        ])
    return headers, rows, truncated, total


@transaction.atomic
def save_record(*, record, user, is_new=False):
    repo.save_record(record)
    log_member_audit(
        record.church,
        "RECORD_CREATE" if is_new else "RECORD_UPDATE",
        performed_by=user,
        member=record.member,
        details={
            "record_id": record.pk,
            "record_type": record.record_type,
            "title": record.title,
        },
    )
    return record


@transaction.atomic
def save_department(*, department, user, is_new=False):
    repo.save_department(department)
    log_member_audit(
        department.church,
        "DEPARTMENT_CREATE" if is_new else "DEPARTMENT_UPDATE",
        performed_by=user,
        details={"department_id": str(department.pk), "name": department.name},
    )
    return department


@transaction.atomic
def save_occupation(*, occupation, user, is_new=False):
    repo.save_occupation(occupation)
    log_member_audit(
        occupation.church,
        "OCCUPATION_CREATE" if is_new else "OCCUPATION_UPDATE",
        performed_by=user,
        details={"occupation_id": str(occupation.pk), "name": occupation.name},
    )
    return occupation


@transaction.atomic
def delete_occupation_record(occupation, user):
    name = occupation.name
    church = occupation.church
    occupation_id = occupation.pk
    repo.delete_occupation(occupation)
    log_member_audit(
        church,
        "OCCUPATION_DELETE",
        performed_by=user,
        details={"occupation_id": str(occupation_id), "name": name},
    )


@transaction.atomic
def save_member_lookup_option(*, option, user, church, is_new=False):
    """Persist a shared member dropdown option and audit against the active church."""
    option.save()
    log_member_audit(
        church,
        "LOOKUP_CREATE" if is_new else "LOOKUP_UPDATE",
        performed_by=user,
        details={
            "lookup_id": str(option.pk),
            "category": option.category,
            "code": option.code,
            "label": option.label,
            "is_active": option.is_active,
        },
    )
    return option


@transaction.atomic
def save_family(*, family, user, is_new=False):
    repo.save_family(family)
    log_member_audit(
        family.church,
        "FAMILY_CREATE" if is_new else "FAMILY_UPDATE",
        performed_by=user,
        details={"family_id": str(family.pk), "name": family.name},
    )
    return family


@transaction.atomic
def assign_leadership_role(*, role, user):
    repo.save_leadership_role(role)
    log_member_audit(
        role.church,
        "LEADERSHIP_ASSIGN",
        performed_by=user,
        member=role.member,
        details={"title": role.title, "role_id": str(role.pk)},
    )
    return role


@transaction.atomic
def end_leadership_role(*, role, user, end_date=None):
    role.is_active = False
    role.end_date = end_date or timezone.localdate()
    repo.save_leadership_role(role, update_fields=["is_active", "end_date"])
    log_member_audit(
        role.church,
        "LEADERSHIP_END",
        performed_by=user,
        member=role.member,
        details={"title": role.title, "role_id": str(role.pk)},
    )
    return role


@transaction.atomic
def assign_spiritual_gift(*, member, gift, user, noted_at=None, notes=""):
    assignment, created = repo.get_or_create_gift_assignment(
        member=member,
        gift=gift,
        defaults={"noted_at": noted_at, "notes": notes or ""},
    )
    if not created:
        raise MemberServiceError("This gift is already assigned to the member.")
    log_member_audit(
        member.church,
        "GIFT_ASSIGN",
        performed_by=user,
        member=member,
        details={"gift": gift.name, "assignment_id": str(assignment.pk)},
    )
    return assignment


@transaction.atomic
def create_spiritual_gift_catalog(*, church, user, **fields):
    gift = repo.create_spiritual_gift(church=church, **fields)
    log_member_audit(
        church,
        "GIFT_CATALOG_CREATE",
        performed_by=user,
        details={"gift_id": str(gift.pk), "name": gift.name},
    )
    return gift


@transaction.atomic
def soft_delete_member(member, user, *, reason=""):
    member.soft_delete(user=user, reason=reason or "Member archived")
    log_member_audit(
        member.church,
        "SOFT_DELETE",
        performed_by=user,
        member=member,
        details={"reason": reason},
    )
    return member


@transaction.atomic
def restore_member(member, user):
    member.restore()
    log_member_audit(
        member.church,
        "RESTORE",
        performed_by=user,
        member=member,
        details={},
    )
    return member


@transaction.atomic
def create_visitor(church, user, **fields):
    from members.models import Visitor

    visitor = Visitor(church=church, created_by=user, **fields)
    visitor.full_clean()
    visitor.save()
    log_member_audit(
        church,
        "VISITOR_CREATE",
        performed_by=user,
        details={"visitor_id": str(visitor.pk), "name": visitor.full_name},
    )
    return visitor


@transaction.atomic
def update_visitor(visitor, user, **fields):
    changed = {}
    for key, value in fields.items():
        old = getattr(visitor, key)
        if old != value:
            changed[key] = {"from": str(old), "to": str(value)}
            setattr(visitor, key, value)
    visitor.full_clean()
    visitor.save()
    if changed:
        log_member_audit(
            visitor.church,
            "VISITOR_UPDATE",
            performed_by=user,
            details={"visitor_id": str(visitor.pk), **changed},
        )
    return visitor


@transaction.atomic
def convert_visitor_to_member(visitor, user, **member_fields):
    """Create an Active member from a visitor and link the conversion."""
    from members.models import VisitorFollowUpStatus

    if visitor.converted_member_id:
        raise MemberServiceError("Visitor already converted.")
    defaults = {
        "first_name": visitor.first_name,
        "last_name": visitor.last_name,
        "phone": visitor.phone,
        "email": visitor.email,
        "address": visitor.address,
        "membership_status": MembershipStatus.ACTIVE,
        "date_joined": timezone.localdate(),
        "gender": member_fields.pop("gender", "Male"),
    }
    defaults.update(member_fields)
    member = create_member(visitor.church, performed_by=user, **defaults)
    visitor.converted_member = member
    visitor.follow_up_status = VisitorFollowUpStatus.CONVERTED
    visitor.save(update_fields=["converted_member", "follow_up_status", "updated_at"])
    log_member_audit(
        visitor.church,
        "VISITOR_CONVERT",
        performed_by=user,
        member=member,
        details={"visitor_id": str(visitor.pk)},
    )
    return member


def migrate_history_rows_to_records(*, church=None) -> int:
    """
    Convert legacy History rows into Record (type Other).

    Idempotent via migrated_from_history_id. Timeline should prefer Records.
    """
    from members.models import History, Record, RecordType

    qs = History.objects.all().select_related("member", "church")
    if church is not None:
        qs = qs.filter(church=church)
    created = 0
    for hist in qs.iterator():
        if Record.all_objects.filter(migrated_from_history_id=hist.pk).exists():
            continue
        Record.objects.create(
            church=hist.church,
            member=hist.member,
            record_type=RecordType.OTHER,
            status="Active",
            title=hist.title,
            description=hist.description or "",
            event_date=hist.date,
            migrated_from_history_id=hist.pk,
            created_by=hist.created_by,
        )
        created += 1
    return created
