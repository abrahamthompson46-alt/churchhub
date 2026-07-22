"""Subtree organization scope — denomination wall + no sideways jumps."""

from __future__ import annotations

from django.db import models

from permissions.roles import UserRole


class OrgScopeLevel:
    CHURCH = "CHURCH"
    DISTRICT = "DISTRICT"
    ZONE = "ZONE"
    CONFERENCE = "CONFERENCE"
    UNION = "UNION"
    GENERAL_CONFERENCE = "GENERAL_CONFERENCE"
    DENOMINATION = "DENOMINATION"

    CHOICES = [
        (CHURCH, "Local Church"),
        (DISTRICT, "District"),
        (ZONE, "Zone"),
        (CONFERENCE, "Conference"),
        (UNION, "Union"),
        (GENERAL_CONFERENCE, "General Conference"),
        (DENOMINATION, "Denomination"),
    ]

    # Wider scopes first — used for invite rank checks
    RANK = {
        DENOMINATION: 0,
        GENERAL_CONFERENCE: 1,
        UNION: 2,
        CONFERENCE: 3,
        ZONE: 4,
        DISTRICT: 5,
        CHURCH: 6,
    }

    @classmethod
    def label(cls, level: str) -> str:
        return dict(cls.CHOICES).get(level, level or "—")

    @classmethod
    def default_for_role(cls, role: str) -> str:
        return {
            UserRole.SUPER_ADMIN: cls.DENOMINATION,
            UserRole.GENERAL_OVERSEER: cls.DENOMINATION,
            UserRole.UNION_ADMIN: cls.UNION,
            UserRole.CONFERENCE_ADMIN: cls.CONFERENCE,
            UserRole.ZONE_DIRECTOR: cls.ZONE,
            UserRole.DISTRICT_PASTOR: cls.DISTRICT,
            UserRole.LOCAL_PASTOR: cls.CHURCH,
            UserRole.SECRETARY: cls.CHURCH,
            UserRole.TREASURY: cls.CHURCH,
            UserRole.BOARD_MEMBER: cls.CHURCH,
            UserRole.MEMBER: cls.CHURCH,
        }.get(role, cls.CHURCH)

    @classmethod
    def allowed_for_role(cls, role: str) -> set[str]:
        """Scope levels a role may legitimately hold."""
        default = cls.default_for_role(role)
        if role in {UserRole.SUPER_ADMIN, UserRole.GENERAL_OVERSEER}:
            return {
                cls.DENOMINATION,
                cls.GENERAL_CONFERENCE,
                cls.UNION,
                cls.CONFERENCE,
            }
        if role == UserRole.UNION_ADMIN:
            return {cls.UNION, cls.CONFERENCE}
        if role == UserRole.CONFERENCE_ADMIN:
            return {cls.CONFERENCE, cls.ZONE, cls.DISTRICT}
        if role == UserRole.ZONE_DIRECTOR:
            return {cls.ZONE, cls.DISTRICT}
        if role == UserRole.DISTRICT_PASTOR:
            return {cls.DISTRICT, cls.CHURCH}
        return {cls.CHURCH, default}


def infer_scope_level(user) -> str:
    """Resolve effective scope level (stored value, else role default)."""
    level = getattr(user, "scope_level", None) or ""
    if level:
        return level
    return OrgScopeLevel.default_for_role(getattr(user, "role", "") or UserRole.MEMBER)


def clear_scope_fks(user) -> None:
    user.scope_district = None
    user.scope_zone = None
    user.scope_conference = None
    user.scope_union = None
    user.scope_general_conference = None


def apply_org_scope(
    user,
    *,
    role=None,
    scope_level=None,
    church=None,
    district=None,
    zone=None,
    conference=None,
    union=None,
    general_conference=None,
    denomination=None,
):
    """
    Attach *user* to an organization node.
    Clears conflicting scope FKs and syncs denomination when possible.
    """
    role = role or user.role
    user.role = role
    level = scope_level or OrgScopeLevel.default_for_role(role)
    user.scope_level = level
    clear_scope_fks(user)

    if church is not None:
        user.church = church

    if level == OrgScopeLevel.CHURCH:
        if not user.church_id and church:
            user.church = church
        if user.church_id:
            denomination = denomination or getattr(user.church, "denomination", None)
    elif level == OrgScopeLevel.DISTRICT:
        district = district or (user.church.district if user.church_id else None)
        user.scope_district = district
        if district and not user.church_id:
            # Prefer a home church in-district when available later
            pass
        denomination = denomination or (
            district.zone.conference.denomination if district and district.zone_id else None
        )
    elif level == OrgScopeLevel.ZONE:
        zone = zone or (
            user.church.district.zone if user.church_id and user.church.district_id else None
        )
        user.scope_zone = zone
        denomination = denomination or (
            zone.conference.denomination if zone and zone.conference_id else None
        )
    elif level == OrgScopeLevel.CONFERENCE:
        conference = conference or (
            user.church.district.zone.conference
            if user.church_id and user.church.district_id
            else None
        )
        user.scope_conference = conference
        denomination = denomination or (conference.denomination if conference else None)
    elif level == OrgScopeLevel.UNION:
        if union is None and user.church_id:
            conf = user.church.district.zone.conference
            union = conf.union if conf else None
        user.scope_union = union
        if denomination is None and union is not None:
            from permissions import selectors

            conf = selectors.first_conference_for_union(union)
            denomination = conf.denomination if conf else None
    elif level == OrgScopeLevel.GENERAL_CONFERENCE:
        user.scope_general_conference = general_conference
    elif level == OrgScopeLevel.DENOMINATION:
        pass

    if denomination is not None:
        user.denomination = denomination
    elif user.church_id:
        user.denomination = getattr(user.church, "denomination", user.denomination)

    return user


def scope_display(user) -> dict:
    """UI-friendly scope summary."""
    level = infer_scope_level(user)
    name = "—"
    breadcrumb = []

    if level == OrgScopeLevel.CHURCH and user.church_id:
        church = user.church
        name = church.name
        breadcrumb = [
            church.district.zone.conference.name,
            church.district.zone.name,
            church.district.name,
            church.name,
        ]
    elif level == OrgScopeLevel.DISTRICT:
        district = user.scope_district or (user.church.district if user.church_id else None)
        if district:
            name = district.name
            breadcrumb = [
                district.zone.conference.name,
                district.zone.name,
                district.name,
            ]
    elif level == OrgScopeLevel.ZONE:
        zone = user.scope_zone
        if not zone and user.church_id:
            zone = user.church.district.zone
        if zone:
            name = zone.name
            breadcrumb = [zone.conference.name, zone.name]
    elif level == OrgScopeLevel.CONFERENCE:
        conference = user.scope_conference
        if not conference and user.church_id:
            conference = user.church.district.zone.conference
        if conference:
            name = conference.name
            breadcrumb = [conference.name]
    elif level == OrgScopeLevel.UNION:
        union = user.scope_union
        if union:
            name = union.name
            breadcrumb = [union.name]
    elif level == OrgScopeLevel.GENERAL_CONFERENCE:
        gc = user.scope_general_conference
        if gc:
            name = gc.name
            breadcrumb = [gc.name]
    elif level == OrgScopeLevel.DENOMINATION:
        denom = user.denomination or (
            user.church.denomination if user.church_id else None
        )
        if denom:
            name = denom.name
            breadcrumb = [denom.name]

    return {
        "level": level,
        "level_label": OrgScopeLevel.label(level),
        "name": name,
        "breadcrumb": " · ".join(breadcrumb) if breadcrumb else name,
    }


def church_q_for_scope(user) -> models.Q | None:
    """
    Return a Q filter for Church rows inside the user's subtree.
    None means “no restriction beyond denomination” should not be used —
    callers should treat None as deny-all unless superuser path.
    Returns empty Q() that matches nothing via pk__in=[] pattern using None sentinel:
    actually return models.Q(pk__in=[]) for no access.
    """
    if not user or not getattr(user, "is_authenticated", True):
        return models.Q(pk__in=[])

    level = infer_scope_level(user)

    if level == OrgScopeLevel.DENOMINATION:
        denom = user.denomination or (
            user.church.denomination if getattr(user, "church_id", None) else None
        )
        if not denom:
            # Unscoped denomination admin — deny by default (safer than all-tenant)
            if getattr(user, "is_superuser", False):
                return models.Q()
            return models.Q(pk__in=[])
        return models.Q(district__zone__conference__denomination=denom)

    if level == OrgScopeLevel.GENERAL_CONFERENCE:
        gc_id = getattr(user, "scope_general_conference_id", None)
        if not gc_id:
            return models.Q(pk__in=[])
        return models.Q(district__zone__conference__union__general_conference_id=gc_id)

    if level == OrgScopeLevel.UNION:
        union_id = getattr(user, "scope_union_id", None)
        if not union_id:
            return models.Q(pk__in=[])
        return models.Q(district__zone__conference__union_id=union_id)

    if level == OrgScopeLevel.CONFERENCE:
        conf_id = getattr(user, "scope_conference_id", None)
        if not conf_id and user.church_id:
            conf_id = user.church.district.zone.conference_id
        if not conf_id:
            return models.Q(pk__in=[])
        return models.Q(district__zone__conference_id=conf_id)

    if level == OrgScopeLevel.ZONE:
        zone_id = getattr(user, "scope_zone_id", None)
        if not zone_id and user.church_id:
            zone_id = user.church.district.zone_id
        if not zone_id:
            return models.Q(pk__in=[])
        return models.Q(district__zone_id=zone_id)

    if level == OrgScopeLevel.DISTRICT:
        district_id = getattr(user, "scope_district_id", None)
        if not district_id and user.church_id:
            district_id = user.church.district_id
        if not district_id:
            return models.Q(pk__in=[])
        return models.Q(district_id=district_id)

    # CHURCH
    if user.church_id:
        return models.Q(pk=user.church_id)
    return models.Q(pk__in=[])


def church_in_user_scope(user, church) -> bool:
    if not church:
        return False
    from permissions import selectors

    return selectors.church_exists_with_q(church_q_for_scope(user), church.pk)


def manageable_scope_units(user, level: str):
    """Org nodes the *manager* may assign when inviting at *level*."""
    from church_system.denomination_scope import get_user_denomination
    from permissions import selectors
    from permissions.scoping import get_manageable_churches

    denom = get_user_denomination(user)
    churches = get_manageable_churches(user)

    if level == OrgScopeLevel.CHURCH:
        return churches.select_related("district__zone__conference").order_by("name")
    if level == OrgScopeLevel.DISTRICT:
        ids = churches.values_list("district_id", flat=True).distinct()
        return selectors.districts_by_ids(ids)
    if level == OrgScopeLevel.ZONE:
        ids = churches.values_list("district__zone_id", flat=True).distinct()
        return selectors.zones_by_ids(ids)
    if level == OrgScopeLevel.CONFERENCE:
        ids = churches.values_list("district__zone__conference_id", flat=True).distinct()
        return selectors.conferences_by_ids(ids)
    if level == OrgScopeLevel.UNION:
        ids = churches.values_list(
            "district__zone__conference__union_id", flat=True
        ).distinct()
        return selectors.unions_by_ids(ids)
    if level == OrgScopeLevel.GENERAL_CONFERENCE:
        ids = churches.values_list(
            "district__zone__conference__union__general_conference_id", flat=True
        ).distinct()
        return selectors.general_conferences_by_ids(ids)
    if level == OrgScopeLevel.DENOMINATION:
        if denom:
            return selectors.denominations_by_pk(denom.pk)
        # Break-glass: denominations that appear in manageable churches
        denom_ids = churches.values_list(
            "district__zone__conference__denomination_id", flat=True
        ).distinct()
        return selectors.denominations_by_ids(denom_ids)
    return selectors.empty_churches()
