"""
Persistence helpers for the members domain.

Services own business rules and call repositories for ORM writes / lookups.
Selectors own read querysets. Do not put authorization or workflow rules here.
"""

from __future__ import annotations

from .models import (
    Department,
    Family,
    LeadershipRole,
    Member,
    MemberAuditLog,
    MemberSpiritualGift,
    MemberTransfer,
    Occupation,
    Record,
    SpiritualGift,
)


def create_audit_log(*, church, action, performed_by=None, member=None, details=None):
    return MemberAuditLog.objects.create(
        church=church,
        member=member,
        action=action,
        performed_by=performed_by,
        details=details or {},
    )


def create_member(*, church, created_by=None, **fields):
    member = Member(church=church, created_by=created_by, **fields)
    member.full_clean()
    member.save()
    return member


def save_member(member, *, update_fields=None):
    if update_fields is not None:
        member.save(update_fields=update_fields)
    else:
        member.full_clean()
        member.save()
    return member


def create_transfer(**fields):
    return MemberTransfer.objects.create(**fields)


def save_transfer(transfer, *, update_fields=None):
    if update_fields is not None:
        transfer.save(update_fields=update_fields)
    else:
        transfer.save()
    return transfer


def create_record(**fields):
    return Record.objects.create(**fields)


def save_record(record, *, update_fields=None):
    if update_fields is not None:
        record.save(update_fields=update_fields)
    else:
        record.save()
    return record


def end_active_leadership_roles(*, member, church, end_date):
    return LeadershipRole.objects.filter(
        member=member,
        church=church,
        is_active=True,
    ).update(is_active=False, end_date=end_date)


def save_leadership_role(role, *, update_fields=None):
    if update_fields is not None:
        role.save(update_fields=update_fields)
    else:
        role.full_clean()
        role.save()
    return role


def create_department(*, church, **fields):
    dept = Department(church=church, **fields)
    dept.save()
    return dept


def save_department(department):
    department.save()
    return department


def delete_department(department):
    department.delete()


def save_occupation(occupation):
    occupation.full_clean()
    occupation.save()
    return occupation


def delete_occupation(occupation):
    occupation.delete()


def create_family(*, church, **fields):
    family = Family(church=church, **fields)
    family.save()
    return family


def save_family(family):
    family.save()
    return family


def create_spiritual_gift(*, church, **fields):
    gift = SpiritualGift(church=church, **fields)
    gift.save()
    return gift


def save_spiritual_gift(gift):
    gift.save()
    return gift


def get_or_create_gift_assignment(*, member, gift, defaults=None):
    return MemberSpiritualGift.objects.get_or_create(
        member=member,
        gift=gift,
        defaults=defaults or {},
    )


def delete_gift_assignment(assignment):
    assignment.delete()


def budgets_reference_department(department) -> bool:
    from transactions.models import Budget

    return Budget.objects.filter(department=department).exists()
