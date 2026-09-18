"""Session epoch, absolute timeout, and password-history helpers."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from permissions.roles import UserRole

SESSION_STARTED_AT = "session_started_at"
SESSION_EPOCH_KEY = "user_session_epoch"
PASSWORD_HISTORY_LIMIT = 5

PRIVILEGED_TRUSTED_DEVICE_DAYS = 7
DEFAULT_TRUSTED_DEVICE_DAYS = 30

PRIVILEGED_HISTORY_ROLES = frozenset(
    {
        UserRole.SUPER_ADMIN,
        UserRole.TREASURY,
        UserRole.DISTRICT_TREASURY,
    }
)
PRIVILEGED_PLATFORM_ROLES = frozenset({"OWNER", "SECURITY"})


def user_requires_password_history(user) -> bool:
    if not user or not getattr(user, "pk", None):
        return False
    if getattr(user, "is_platform_user", False):
        return (getattr(user, "platform_role", "") or "") in PRIVILEGED_PLATFORM_ROLES
    return getattr(user, "role", None) in PRIVILEGED_HISTORY_ROLES


def trusted_device_days_for_user(user) -> int:
    from accounts.mfa import user_requires_mfa

    if user_requires_mfa(user):
        return int(
            getattr(settings, "MFA_PRIVILEGED_TRUSTED_DEVICE_DAYS", PRIVILEGED_TRUSTED_DEVICE_DAYS)
        )
    return int(getattr(settings, "MFA_TRUSTED_DEVICE_DAYS", DEFAULT_TRUSTED_DEVICE_DAYS))


def session_absolute_age_seconds() -> int:
    return int(getattr(settings, "SESSION_ABSOLUTE_AGE", 60 * 60 * 12))


def stamp_session(request, user) -> None:
    """Bind this browser session to the user's current epoch and start time."""
    if not hasattr(request, "session") or not user or not getattr(user, "pk", None):
        return
    request.session[SESSION_EPOCH_KEY] = int(getattr(user, "session_epoch", 0) or 0)
    if not request.session.get(SESSION_STARTED_AT):
        request.session[SESSION_STARTED_AT] = timezone.now().isoformat()
    request.session.modified = True


def bump_session_epoch(user) -> int:
    from accounts import repositories as repo

    next_epoch = int(getattr(user, "session_epoch", 0) or 0) + 1
    user.session_epoch = next_epoch
    repo.save_user(user, update_fields=["session_epoch"])
    return next_epoch


def remember_previous_password(user, previous_hash: str) -> None:
    if not user_requires_password_history(user) or not previous_hash:
        return
    from accounts.models import PasswordHistory

    PasswordHistory.objects.create(user=user, password=previous_hash)
    keep = list(
        PasswordHistory.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("pk", flat=True)[:PASSWORD_HISTORY_LIMIT]
    )
    PasswordHistory.objects.filter(user=user).exclude(pk__in=keep).delete()


def password_was_used_recently(user, raw_password: str) -> bool:
    if not user_requires_password_history(user) or not raw_password:
        return False
    from accounts.models import PasswordHistory

    hashes = [user.password] if user.password else []
    hashes.extend(
        PasswordHistory.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("password", flat=True)[:PASSWORD_HISTORY_LIMIT]
    )
    return any(check_password(raw_password, stored) for stored in hashes if stored)


def on_password_replaced(user, *, previous_hash: str) -> None:
    from accounts.mfa import revoke_all_trusted_devices

    remember_previous_password(user, previous_hash)
    revoke_all_trusted_devices(user)
    bump_session_epoch(user)


def session_exceeded_absolute_age(request) -> bool:
    raw = request.session.get(SESSION_STARTED_AT)
    if not raw:
        return False
    started = parse_datetime(raw) if isinstance(raw, str) else raw
    if started is None:
        return False
    if timezone.is_naive(started):
        started = timezone.make_aware(started, timezone.get_current_timezone())
    limit = timedelta(seconds=session_absolute_age_seconds())
    return timezone.now() - started > limit


def session_epoch_mismatch(request, user) -> bool:
    stored = request.session.get(SESSION_EPOCH_KEY)
    if stored is None:
        return False
    return int(stored) != int(getattr(user, "session_epoch", 0) or 0)
