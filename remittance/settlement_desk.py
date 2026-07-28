"""Settlement desk context for hierarchy treasurers (district through GC)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from permissions.org_scope import OrgScopeLevel, infer_scope_level
from remittance.services import get_unit_choices, unit_in_user_scope

DESK_UNIT_TYPES = ("DISTRICT", "CONFERENCE", "UNION", "GENERAL_CONFERENCE")

_SCOPE_TO_DESK_TYPE = {
    OrgScopeLevel.DISTRICT: "DISTRICT",
    OrgScopeLevel.ZONE: "DISTRICT",
    OrgScopeLevel.CONFERENCE: "CONFERENCE",
    OrgScopeLevel.UNION: "UNION",
    OrgScopeLevel.GENERAL_CONFERENCE: "GENERAL_CONFERENCE",
    OrgScopeLevel.DENOMINATION: "CONFERENCE",
}


@dataclass(frozen=True)
class SettlementDesk:
    unit_type: str
    unit_id: UUID
    label: str


def _scope_unit_id(user, unit_type: str, church=None):
    """Best-effort org node for the user's scope."""
    if unit_type == "DISTRICT":
        if getattr(user, "scope_district_id", None):
            return user.scope_district_id
        if church and church.district_id:
            return church.district_id
    if unit_type == "CONFERENCE":
        if getattr(user, "scope_conference_id", None):
            return user.scope_conference_id
        if church and church.district_id:
            return church.district.zone.conference_id
    if unit_type == "UNION":
        if getattr(user, "scope_union_id", None):
            return user.scope_union_id
        if church and church.district_id:
            return church.district.zone.conference.union_id
    if unit_type == "GENERAL_CONFERENCE":
        if getattr(user, "scope_general_conference_id", None):
            return user.scope_general_conference_id
        if church and church.district_id:
            conf = church.district.zone.conference
            if conf.union_id:
                return conf.union.general_conference_id
    return None


def list_settlement_desks(user, *, church=None) -> list[SettlementDesk]:
    """Desks the user may operate (from-unit for hierarchy drafts + incoming view)."""
    level = infer_scope_level(user)
    if level == OrgScopeLevel.CHURCH:
        return []

    desks: list[SettlementDesk] = []
    preferred_type = _SCOPE_TO_DESK_TYPE.get(level)
    types_to_scan = [preferred_type] if preferred_type else list(DESK_UNIT_TYPES)
    if level == OrgScopeLevel.ZONE:
        types_to_scan = ["DISTRICT"]
    elif level in (OrgScopeLevel.DENOMINATION, OrgScopeLevel.GENERAL_CONFERENCE):
        types_to_scan = list(DESK_UNIT_TYPES)

    seen: set[tuple[str, str]] = set()
    for unit_type in types_to_scan:
        if not unit_type:
            continue
        for choice_id, label in get_unit_choices(unit_type, user=user, church=church):
            key = (unit_type, choice_id)
            if key in seen:
                continue
            seen.add(key)
            desks.append(
                SettlementDesk(
                    unit_type=unit_type,
                    unit_id=UUID(choice_id),
                    label=label,
                )
            )
    return desks


def resolve_settlement_desk(user, request, *, church=None) -> SettlementDesk | None:
    """
    Active desk from query ?desk_type=&desk_id= or user's primary scope node.
    """
    desks = list_settlement_desks(user, church=church)
    if not desks:
        return None

    req_type = (request.GET.get("desk_type") or "").strip().upper()
    req_id = (request.GET.get("desk_id") or "").strip()
    desk_pick = (request.GET.get("desk") or "").strip()
    if desk_pick and ":" in desk_pick:
        req_type, req_id = desk_pick.split(":", 1)
        req_type = req_type.upper()
    if req_type and req_id:
        for desk in desks:
            if desk.unit_type == req_type and str(desk.unit_id) == req_id:
                return desk

    preferred_type = _SCOPE_TO_DESK_TYPE.get(infer_scope_level(user))
    scoped_id = _scope_unit_id(user, preferred_type, church=church) if preferred_type else None
    if scoped_id:
        for desk in desks:
            if desk.unit_type == preferred_type and desk.unit_id == scoped_id:
                return desk

    return desks[0]


def user_has_hierarchy_settlement_desk(user, *, church=None) -> bool:
    return bool(list_settlement_desks(user, church=church))


def user_can_access_settlement_batch(user, batch, *, church=None) -> bool:
    """View/post permission for a batch within org subtree."""
    from permissions.scoping import get_manageable_churches

    if batch.from_unit_type == "CHURCH":
        church_ids = {
            str(pk)
            for pk in get_manageable_churches(user).values_list("pk", flat=True)
        }
        return str(batch.from_unit_id) in church_ids

    if batch.to_unit_type in DESK_UNIT_TYPES:
        if unit_in_user_scope(user, batch.to_unit_type, batch.to_unit_id, church=church):
            return True
    if batch.from_unit_type in DESK_UNIT_TYPES:
        return unit_in_user_scope(
            user, batch.from_unit_type, batch.from_unit_id, church=church
        )
    return False
