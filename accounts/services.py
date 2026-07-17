"""Account management services."""

from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from permissions.roles import UserRole
from permissions.services import get_client_ip, sync_role_groups

from .models import User, UserActivityLog, UserInvitation

__all__ = [
    "get_client_ip",
    "sync_role_groups",
    "log_activity",
    "assert_can_assign_role",
    "assign_user_to_church",
    "create_invitation",
    "send_invitation_email",
    "accept_invitation",
    "revoke_invitation",
    "resend_invitation",
    "deactivate_user",
    "activate_user",
    "update_user_role",
    "update_user_profile",
]


def log_activity(user, action, performed_by=None, ip_address=None, details=None):
    return UserActivityLog.objects.create(
        user=user,
        action=action,
        performed_by=performed_by,
        ip_address=ip_address,
        details=details or {},
    )


def assert_can_assign_role(actor, role):
    """Raise ValueError if actor may not assign *role*."""
    if getattr(actor, "is_platform_user", False):
        return
    if not UserRole.can_assign_role(
        getattr(actor, "role", None),
        role,
        actor_is_superuser=getattr(actor, "is_superuser", False),
    ):
        raise ValueError(f"You are not allowed to assign the role {UserRole.label(role)}.")


def assign_user_to_church(user, church, performed_by=None, ip_address=None):
    user.church = church
    update_fields = ["church"]
    denom = getattr(church, "denomination", None) if church else None
    if denom and user.denomination_id != denom.pk:
        user.denomination = denom
        update_fields.append("denomination")
    user.save(update_fields=update_fields)
    log_activity(
        user,
        "CHURCH_ASSIGN",
        performed_by=performed_by,
        ip_address=ip_address,
        details={"church_id": str(church.id), "church_name": church.name},
    )
    return user


def create_invitation(email, username, role, church, invited_by, days_valid=7):
    assert_can_assign_role(invited_by, role)

    username = username.strip()
    email = email.lower().strip()

    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("Username is already taken.")
    if User.objects.filter(email__iexact=email, is_active=True).exists():
        raise ValueError("An active user with this email already exists.")

    invitation = UserInvitation.objects.create(
        email=email,
        username=username,
        role=role,
        church=church,
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=days_valid),
    )
    log_activity(
        invited_by,
        "INVITE_SENT",
        performed_by=invited_by,
        details={
            "email": email,
            "username": username,
            "role": role,
            "invitation_id": str(invitation.id),
        },
    )
    return invitation


def send_invitation_email(invitation, request=None, *, fail_silently=True):
    """
    Deliver an invitation email.

    Sends synchronously by default so the UI can report real SMTP success/failure.
    Async (Celery) only when CHURCHHUB_ASYNC_EMAIL is enabled and a broker is usable.
    Returns True if accepted by SMTP (or queued when async), False if SMTP is not configured.
    Raises on SMTP delivery errors when fail_silently is False.
    """
    from django.conf import settings

    from church_system.email_service import send_user_invitation_email

    use_async = getattr(settings, "CHURCHHUB_ASYNC_EMAIL", False) and not getattr(
        settings, "CELERY_TASK_ALWAYS_EAGER", False
    )
    if use_async:
        try:
            from church_system.tasks import send_invitation_email_task

            send_invitation_email_task.delay(str(invitation.pk))
            return True
        except Exception:
            # Fall through to synchronous send when the broker/worker path fails.
            pass

    return send_user_invitation_email(
        invitation,
        request=request,
        fail_silently=fail_silently,
    )


@transaction.atomic
def accept_invitation(invitation, password, first_name="", last_name=""):
    invitation = UserInvitation.objects.select_for_update().get(pk=invitation.pk)

    if not invitation.is_valid:
        raise ValueError("This invitation is no longer valid.")

    from sitecontrol.services import can_add_user_to_church

    allowed, message = can_add_user_to_church(invitation.church)
    if not allowed:
        raise ValueError(message)

    if User.objects.filter(username__iexact=invitation.username).exists():
        raise ValueError("Username is already taken.")
    if User.objects.filter(email__iexact=invitation.email, is_active=True).exists():
        raise ValueError("An active user with this email already exists.")

    validate_password(password, user=User(username=invitation.username, email=invitation.email))

    denom = getattr(invitation.church, "denomination", None)
    user = User.objects.create_user(
        username=invitation.username,
        email=invitation.email,
        password=password,
        role=invitation.role,
        church=invitation.church,
        first_name=first_name,
        last_name=last_name,
        is_staff=False,
        denomination=denom,
    )
    sync_role_groups(user)

    invitation.is_accepted = True
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["is_accepted", "accepted_at"])

    log_activity(
        user,
        "INVITE_ACCEPTED",
        details={"invitation_id": str(invitation.id)},
    )
    log_activity(user, "USER_CREATE", performed_by=invitation.invited_by)
    return user


def revoke_invitation(invitation, performed_by=None, ip_address=None):
    if invitation.is_accepted:
        raise ValueError("Accepted invitations cannot be revoked.")
    if invitation.is_revoked:
        return invitation

    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    actor = performed_by or invitation.invited_by
    if actor:
        log_activity(
            actor,
            "INVITE_REVOKED",
            performed_by=performed_by,
            ip_address=ip_address,
            details={
                "email": invitation.email,
                "username": invitation.username,
                "invitation_id": str(invitation.id),
            },
        )
    return invitation


def resend_invitation(invitation, performed_by=None, ip_address=None, days_valid=7, request=None):
    if invitation.is_accepted:
        raise ValueError("Accepted invitations cannot be resent.")
    if invitation.is_revoked:
        raise ValueError("Revoked invitations cannot be resent.")

    invitation.expires_at = timezone.now() + timedelta(days=days_valid)
    invitation.save(update_fields=["expires_at"])
    actor = performed_by or invitation.invited_by
    if actor:
        log_activity(
            actor,
            "INVITE_RESENT",
            performed_by=performed_by,
            ip_address=ip_address,
            details={
                "email": invitation.email,
                "username": invitation.username,
                "invitation_id": str(invitation.id),
                "expires_at": invitation.expires_at.isoformat(),
            },
        )
    emailed = send_invitation_email(invitation, request=request, fail_silently=True)
    return invitation, emailed


def deactivate_user(user, performed_by=None, ip_address=None):
    if performed_by is not None and performed_by.pk == user.pk:
        raise ValueError("You cannot deactivate your own account.")
    user.is_active = False
    user.save(update_fields=["is_active"])
    log_activity(user, "USER_DEACTIVATE", performed_by=performed_by, ip_address=ip_address)
    return user


def activate_user(user, performed_by=None, ip_address=None):
    user.is_active = True
    user.save(update_fields=["is_active"])
    log_activity(user, "USER_ACTIVATE", performed_by=performed_by, ip_address=ip_address)
    return user


def update_user_role(user, new_role, performed_by=None, ip_address=None):
    old_role = user.role
    if old_role == new_role:
        return user

    if performed_by is not None:
        assert_can_assign_role(performed_by, new_role)

    user.role = new_role
    user.save(update_fields=["role"])
    sync_role_groups(user)
    log_activity(
        user,
        "ROLE_CHANGE",
        performed_by=performed_by,
        ip_address=ip_address,
        details={"old_role": old_role, "new_role": new_role},
    )
    return user


def update_user_profile(user, cleaned_data, performed_by=None, ip_address=None):
    """Apply profile field updates and log changes (including email)."""
    track_fields = ("first_name", "last_name", "email", "phone")
    changes = {}
    old_email = user.email

    for field in track_fields:
        if field not in cleaned_data:
            continue
        new_val = cleaned_data[field]
        old_val = getattr(user, field)
        if (old_val or "") != (new_val or ""):
            changes[field] = {"old": old_val, "new": new_val}
            setattr(user, field, new_val)

    if not changes:
        return user

    user.save(update_fields=list(changes.keys()))

    log_activity(
        user,
        "PROFILE_UPDATE",
        performed_by=performed_by,
        ip_address=ip_address,
        details={"changed_fields": changes},
    )
    if "email" in changes:
        log_activity(
            user,
            "EMAIL_CHANGE",
            performed_by=performed_by,
            ip_address=ip_address,
            details={"old_email": old_email, "new_email": user.email},
        )
    return user
