"""
Persistence helpers for the organization hierarchy domain.

Services/views own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or hierarchy rules here.
"""

from __future__ import annotations

from .models import (
    Church,
    Conference,
    District,
    GeneralConference,
    OrganizationAuditLog,
    Union,
    Zone,
)


def create_org_audit(
    *,
    action,
    entity_type,
    entity_id,
    entity_label,
    performed_by=None,
    ip_address=None,
    details=None,
):
    return OrganizationAuditLog.objects.create(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        performed_by=performed_by,
        ip_address=ip_address,
        details=details or {},
    )


def save_church(church, *, update_fields=None):
    if update_fields is not None:
        church.save(update_fields=update_fields)
    else:
        church.save()
    return church


def get_or_create_church(*, district, code, defaults):
    return Church.objects.get_or_create(
        district=district,
        code=code,
        defaults=defaults,
    )


def create_conference(**fields):
    return Conference.objects.create(**fields)


def save_conference(conference, *, update_fields=None):
    if update_fields is not None:
        conference.save(update_fields=update_fields)
    else:
        conference.save()
    return conference


def get_or_create_zone(*, conference, code, defaults):
    return Zone.objects.get_or_create(
        conference=conference,
        code=code,
        defaults=defaults,
    )


def save_zone(zone, *, update_fields=None):
    if update_fields is not None:
        zone.save(update_fields=update_fields)
    else:
        zone.save()
    return zone


def get_or_create_district(*, zone, code, defaults):
    return District.objects.get_or_create(
        zone=zone,
        code=code,
        defaults=defaults,
    )


def save_district(district, *, update_fields=None):
    if update_fields is not None:
        district.save(update_fields=update_fields)
    else:
        district.save()
    return district


def create_general_conference(**fields):
    return GeneralConference.objects.create(**fields)


def save_general_conference(gc, *, update_fields=None):
    if update_fields is not None:
        gc.save(update_fields=update_fields)
    else:
        gc.save()
    return gc


def create_union(**fields):
    return Union.objects.create(**fields)


def save_union(union, *, update_fields=None):
    if update_fields is not None:
        union.save(update_fields=update_fields)
    else:
        union.save()
    return union


def save_model_instance(instance, *, update_fields=None):
    """Persist a ModelForm-built instance (commit=False path)."""
    if update_fields is not None:
        instance.save(update_fields=update_fields)
    else:
        instance.save()
    return instance
