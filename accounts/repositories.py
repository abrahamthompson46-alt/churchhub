"""
Persistence helpers for the accounts / identity domain.

Services and forms own business rules and call repositories for ORM writes.
Selectors own read querysets. Do not put authorization or invitation rules here.
"""

from __future__ import annotations

from accounts.models import User, UserActivityLog, UserInvitation


def create_activity_log(*, user, action, performed_by=None, ip_address=None, details=None):
    return UserActivityLog.objects.create(
        user=user,
        action=action,
        performed_by=performed_by,
        ip_address=ip_address,
        details=details or {},
    )


def save_user(user, *, update_fields=None):
    if update_fields is not None:
        user.save(update_fields=update_fields)
    else:
        user.save()
    return user


def create_user(**fields):
    return User.objects.create_user(**fields)


def create_invitation(**fields):
    return UserInvitation.objects.create(**fields)


def save_invitation(invitation, *, update_fields=None):
    if update_fields is not None:
        invitation.save(update_fields=update_fields)
    else:
        invitation.save()
    return invitation
