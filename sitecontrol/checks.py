"""Platform authorization helpers."""

from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from church_system.church_scope import get_active_church
from permissions.superadmin import is_superadmin
from sitecontrol.rbac import operator_has_capability, require_platform_capability
from sitecontrol.services import church_has_feature

__all__ = [
    "can_manage_platform",
    "can_access_django_admin",
    "platform_required",
    "require_feature",
    "require_platform_capability",
    "operator_has_capability",
]


def can_manage_platform(user):
    return user.is_authenticated and getattr(user, "is_platform_user", False)


def can_access_django_admin(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_superuser
        and getattr(user, "is_platform_user", False)
    )


def platform_required(view_func):
    @user_passes_test(can_manage_platform, login_url="/accounts/login/")
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_feature(feature):
    """Decorator: active church must have subscription feature."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if is_superadmin(request.user):
                return view_func(request, *args, **kwargs)
            church = get_active_church(request)
            if not church_has_feature(church, feature):
                raise PermissionDenied(
                    f"The {feature.replace('_', ' ')} module is not enabled for this church. "
                    "Contact your platform administrator to upgrade the subscription."
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
