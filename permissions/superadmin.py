"""Institution super-admin bypass — single definition for full permission access."""

from permissions.roles import UserRole


def is_superadmin(user):
    """
    Return True when the user should bypass all institution permission checks.

    Covers Django superusers on the institution lane and users with the
    SUPER_ADMIN role. Platform operators (is_platform_user) are excluded;
    they use the platform control room lane instead.
    """
    if not user.is_authenticated:
        return False
    if getattr(user, "is_platform_user", False):
        return False
    if user.is_superuser:
        return True
    return user.role == UserRole.SUPER_ADMIN
