"""Project-level views."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from church_system.flash import flash_denied
from church_system.health import (
    basic_metrics,
    run_health_checks,
    run_liveness_checks,
    run_readiness_checks,
)
from church_system.health_auth import health_check_authorized


def _health_unauthorized():
    return JsonResponse({"detail": "health check token required"}, status=401)


@require_GET
def health_check(request):
    if not health_check_authorized(request):
        return _health_unauthorized()
    payload, status = run_health_checks()
    return JsonResponse(payload, status=status)


@require_GET
def live_check(request):
    if not health_check_authorized(request):
        return _health_unauthorized()
    payload, status = run_liveness_checks()
    return JsonResponse(payload, status=status)


@require_GET
def ready_check(request):
    if not health_check_authorized(request):
        return _health_unauthorized()
    payload, status = run_readiness_checks()
    return JsonResponse(payload, status=status)


@require_GET
def metrics_check(request):
    """Basic JSON metrics — authenticated operators only (avoid unauthenticated fingerprinting)."""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "authentication required"}, status=401)
    if not (
        getattr(request.user, "is_platform_user", False)
        or request.user.is_staff
        or request.user.is_superuser
    ):
        return JsonResponse({"detail": "forbidden"}, status=403)
    return JsonResponse(basic_metrics())


def permission_denied(request, exception=None):
    """Professional 403 page for permission violations."""
    if request.user.is_authenticated and not messages.get_messages(request):
        flash_denied(request)
    return render(request, "403.html", status=403)


@require_GET
def public_home(request):
    """Public landing page at `/`. Signed-in users continue to their workspace."""
    if request.user.is_authenticated:
        if getattr(request.user, "is_platform_user", False):
            return redirect("sitecontrol:dashboard")
        from permissions.roles import UserRole

        if getattr(request.user, "role", None) == UserRole.MEMBER:
            return redirect("portal:home")
        return redirect("dashboard:home")

    from sitecontrol.marketing_services import marketing_inquiry_is_ready

    return render(
        request,
        "public/home.html",
        {"show_marketing_inquiry": marketing_inquiry_is_ready()},
    )
