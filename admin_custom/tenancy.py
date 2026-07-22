"""Django admin tenancy helpers — reduce cross-tenant blast radius.

Platform OWNER retains full break-glass visibility. Other platform admin
operators are limited to ``managed_denominations`` even when ``is_superuser``.
"""

from __future__ import annotations

from django.db import models

from sitecontrol.rbac import ROLE_OWNER


def admin_operator_is_global(user) -> bool:
    """True when this user may see all churches in Django admin."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_platform_user", False):
        # Institution users are blocked from /admin/ by middleware; deny if reached.
        return False
    return getattr(user, "platform_role", "") == ROLE_OWNER


def scoped_admin_churches(user):
    """Church queryset visible to this operator in Django admin."""
    from organization.models import Church

    qs = Church.objects.all()
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if not getattr(user, "is_platform_user", False):
        return qs.none()
    if admin_operator_is_global(user):
        return qs
    managed = user.managed_denominations.all()
    if not managed.exists():
        return qs.none()
    return qs.filter(district__zone__conference__denomination__in=managed)


def filter_admin_qs_by_church(qs, user, church_field: str = "church"):
    """Filter a queryset that has a church FK (or church path)."""
    if admin_operator_is_global(user):
        return qs
    churches = scoped_admin_churches(user)
    return qs.filter(**{f"{church_field}__in": churches})


def filter_admin_qs_by_org_unit(
    qs,
    user,
    *,
    unit_type_field: str = "unit_type",
    unit_id_field: str = "unit_id",
):
    """
    Filter remittance policy/settlement rows keyed by unit_type + unit_id.
    Matches CHURCH / DISTRICT / ZONE / CONFERENCE / UNION / GENERAL_CONFERENCE.
    """
    if admin_operator_is_global(user):
        return qs

    churches = scoped_admin_churches(user)
    if not churches.exists():
        return qs.none()

    church_ids = list(churches.values_list("pk", flat=True))
    district_ids = list(churches.values_list("district_id", flat=True).distinct())
    zone_ids = list(churches.values_list("district__zone_id", flat=True).distinct())
    conference_ids = list(
        churches.values_list("district__zone__conference_id", flat=True).distinct()
    )
    union_ids = list(
        churches.values_list(
            "district__zone__conference__union_id", flat=True
        ).distinct()
    )
    gc_ids = list(
        churches.values_list(
            "district__zone__conference__union__general_conference_id", flat=True
        ).distinct()
    )

    q = models.Q(**{unit_type_field: "CHURCH", f"{unit_id_field}__in": church_ids})
    if district_ids:
        q |= models.Q(
            **{unit_type_field: "DISTRICT", f"{unit_id_field}__in": district_ids}
        )
    if zone_ids:
        q |= models.Q(**{unit_type_field: "ZONE", f"{unit_id_field}__in": zone_ids})
    if conference_ids:
        q |= models.Q(
            **{unit_type_field: "CONFERENCE", f"{unit_id_field}__in": conference_ids}
        )
    if any(union_ids):
        q |= models.Q(
            **{
                unit_type_field: "UNION",
                f"{unit_id_field}__in": [u for u in union_ids if u],
            }
        )
    if any(gc_ids):
        q |= models.Q(
            **{
                unit_type_field: "GENERAL_CONFERENCE",
                f"{unit_id_field}__in": [g for g in gc_ids if g],
            }
        )
    return qs.filter(q)


def filter_admin_settlement_batches(qs, user):
    """Settlement batches visible when either from_ or to_ unit is in scope."""
    if admin_operator_is_global(user):
        return qs
    from_ids = filter_admin_qs_by_org_unit(
        qs, user, unit_type_field="from_unit_type", unit_id_field="from_unit_id"
    ).values_list("pk", flat=True)
    to_ids = filter_admin_qs_by_org_unit(
        qs, user, unit_type_field="to_unit_type", unit_id_field="to_unit_id"
    ).values_list("pk", flat=True)
    return qs.filter(models.Q(pk__in=from_ids) | models.Q(pk__in=to_ids))
