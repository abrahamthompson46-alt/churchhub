"""Platform tenant user administration (role changes from control room)."""

from __future__ import annotations

from accounts.models import User
from accounts.services import get_client_ip, update_user_role
from permissions.roles import UserRole

# Roles platform operators may assign on the tenant detail page (not portal MEMBER).
TENANT_ASSIGNABLE_ROLES: tuple[str, ...] = tuple(
    code for code, _label in UserRole.CHOICES if code != UserRole.MEMBER
)


def tenant_role_choices():
    return [(code, label) for code, label in UserRole.CHOICES if code in TENANT_ASSIGNABLE_ROLES]


def get_institution_user_for_church(church, user_id):
    return User.objects.filter(
        pk=user_id,
        church=church,
        is_platform_user=False,
    ).first()


def set_tenant_user_role(*, church, user_id, new_role, operator, request=None):
    """
    Change an institution user's role within a church tenant.
    Raises ValueError for validation failures.
    """
    if new_role not in TENANT_ASSIGNABLE_ROLES:
        raise ValueError("That role cannot be assigned from the platform console.")

    target = get_institution_user_for_church(church, user_id)
    if target is None:
        raise ValueError("User not found for this church.")

    if target.role == new_role:
        return target, False

    ip = get_client_ip(request) if request else None
    update_user_role(
        target,
        new_role,
        performed_by=operator,
        ip_address=ip,
        realign_scope=True,
    )
    return target, True
