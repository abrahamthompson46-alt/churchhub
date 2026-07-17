"""Member portal views — self-service home for linked members."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from announcements.services import visible_announcements
from church_system.flash import flash_info
from permissions.roles import UserRole


def user_can_use_member_portal(user):
    if not user.is_authenticated or getattr(user, "is_platform_user", False):
        return False
    return bool(getattr(user, "member_id", None) or user.role == UserRole.MEMBER)


def _portal_member_or_redirect(request):
    """Return (member, redirect_response). member may be None for unlinked MEMBER role."""
    if not user_can_use_member_portal(request.user):
        flash_info(
            request,
            "The member portal is for members with a linked profile. Use the staff dashboard instead.",
            title="Staff account",
        )
        return None, redirect("dashboard:home")
    return getattr(request.user, "member", None), None


@login_required
def home(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied

    year = timezone.localdate().year
    giving_summary = None
    giving_lines = []
    has_payslips = bool(getattr(request.user, "employee_profile", None))

    if member:
        from giving.services import member_giving_lines, member_giving_summary

        giving_summary = member_giving_summary(member, year=year)
        giving_lines = list(member_giving_lines(member, year=year)[:8])

    announcements = list(visible_announcements(request.user).order_by("-created_at")[:5])
    upcoming = []
    try:
        from announcements.calendar_services import attach_calendar_urls, get_communications_calendar

        upcoming = attach_calendar_urls(get_communications_calendar(request, days=30, limit=6))
    except Exception:
        upcoming = []

    return render(request, "portal/home.html", {
        "member": member,
        "giving_summary": giving_summary,
        "giving_lines": giving_lines,
        "giving_year": year,
        "has_payslips": has_payslips,
        "announcements": announcements,
        "upcoming_preview": upcoming,
    })


@login_required
def profile(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if member is None:
        flash_info(
            request,
            "Your account is not linked to a member record yet. Contact your church office.",
        )
    return render(request, "portal/profile.html", {"member": member})
