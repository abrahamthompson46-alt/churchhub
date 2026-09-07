"""Dashboard scope — church vs subtree aggregation for all roles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from church_system.church_scope import get_active_church
from permissions.checks import can_view_all_churches
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches

if TYPE_CHECKING:
    from organization.models import Church


@dataclass(frozen=True)
class DashboardScope:
    level: str  # CHURCH | SUBTREE | EMPTY
    church_ids: tuple
    primary_church: Church | None
    label: str
    finance_church_ids: tuple
    finance_scope_label: str


def _explicit_church_id(request):
    session = getattr(request, "session", None)
    if session is None:
        return None
    value = session.get("current_church_id")
    if not value:
        return None
    return str(value)


def resolve_dashboard_scope(request) -> DashboardScope:
    """Single scope object for KPIs, charts, and widgets."""
    user = request.user
    manageable = get_manageable_churches(user)
    church_ids = tuple(manageable.values_list("pk", flat=True))
    active = get_active_church(request)
    focused = _explicit_church_id(request)

    hierarchy_user = getattr(user, "role", "") in UserRole.TREE_ADMIN_ROLES or can_view_all_churches(
        user
    )
    hierarchy_rollup = hierarchy_user and len(church_ids) > 1 and not focused

    if hierarchy_rollup:
        n = len(church_ids)
        return DashboardScope(
            level="SUBTREE",
            church_ids=church_ids,
            primary_church=None,
            label=f"{n} churches in scope",
            finance_church_ids=church_ids,
            finance_scope_label=f"{n} churches",
        )

    if active and active.pk in church_ids:
        return DashboardScope(
            level="CHURCH",
            church_ids=church_ids,
            primary_church=active,
            label=active.name,
            finance_church_ids=(active.pk,),
            finance_scope_label=active.name,
        )

    if active and active.pk not in church_ids:
        active = None

    if len(church_ids) == 1:
        primary = manageable.first()
        return DashboardScope(
            level="CHURCH",
            church_ids=church_ids,
            primary_church=primary,
            label=primary.name if primary else "—",
            finance_church_ids=church_ids,
            finance_scope_label=primary.name if primary else "—",
        )

    if church_ids:
        n = len(church_ids)
        return DashboardScope(
            level="SUBTREE",
            church_ids=church_ids,
            primary_church=None,
            label=f"{n} churches in scope",
            finance_church_ids=church_ids,
            finance_scope_label=f"{n} churches",
        )

    return DashboardScope(
        level="EMPTY",
        church_ids=(),
        primary_church=None,
        label="No churches in scope",
        finance_church_ids=(),
        finance_scope_label="—",
    )


def scope_selection_banner(scope: DashboardScope, user) -> str:
    """Hint when subtree mode hides church-specific panels."""
    from permissions.checks import can_view_all_churches

    if scope.level != "SUBTREE" or scope.primary_church:
        return ""
    if not can_view_all_churches(user) and len(scope.church_ids) <= 1:
        return ""
    return (
        "Showing totals for every church you can manage. "
        "Pick a congregation below (or in the top bar) for teller, attendance, and receipts."
    )


def scope_switcher_context(scope: DashboardScope, request) -> dict | None:
    """Structured congregation picker for the dashboard home."""
    from church_system.church_scope import get_available_churches

    churches = list(get_available_churches(request.user)[:40])
    if len(churches) <= 1:
        return None
    focused_id = str(scope.primary_church.pk) if scope.primary_church else ""
    return {
        "level": scope.level,
        "label": scope.label,
        "focused_id": focused_id,
        "churches": churches,
    }
