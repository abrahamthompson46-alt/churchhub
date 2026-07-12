"""Project-level views."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render

from church_system.flash import flash_denied
from church_system.health import run_health_checks


def health_check(request):
    payload, status = run_health_checks()
    return JsonResponse(payload, status=status)


def permission_denied(request, exception=None):
    """Professional 403 page for permission violations."""
    if request.user.is_authenticated and not messages.get_messages(request):
        flash_denied(request)
    return render(request, "403.html", status=403)
