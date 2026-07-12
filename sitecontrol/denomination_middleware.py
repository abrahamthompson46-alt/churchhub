"""Enforce denomination context on each request."""

from django.utils.deprecation import MiddlewareMixin

from church_system.denomination_scope import get_active_denomination, get_user_denomination


class DenominationContextMiddleware(MiddlewareMixin):
    """
    Attach denomination to request and persist institution context in session.
    Platform operators may filter by denomination via session/GET.
    """

    def process_request(self, request):
        request.denomination = get_active_denomination(request)
        if (
            request.user.is_authenticated
            and not getattr(request.user, "is_platform_user", False)
            and request.denomination
            and hasattr(request, "session")
        ):
            request.session["active_denomination_id"] = str(request.denomination.pk)
        return None

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or getattr(user, "is_platform_user", False):
            return None

        user_denom = get_user_denomination(user)
        if not user_denom or not request.denomination:
            return None

        if user_denom.pk != request.denomination.pk:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Your account is not authorized for this denomination.")
        return None
