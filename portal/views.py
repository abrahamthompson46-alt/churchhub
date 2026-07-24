"""Member portal views — self-service home for linked members."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from announcements.services import visible_announcements
from church_system.flash import flash_error, flash_info, flash_success, flash_warning
from permissions.roles import UserRole

from .forms import (
    MemberPortalLoginForm,
    PortalPasswordChangeForm,
    PortalPasswordResetForm,
    PortalSetPasswordForm,
)
from .services import (
    PortalAuthError,
    apply_trusted_device_cookie,
    complete_portal_login,
    portal_needs_device_confirmation,
    resolve_confirm_token,
    send_portal_device_confirmation,
)


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


def _portal_post_login_redirect(request):
    user = request.user
    if getattr(user, "must_change_password", False):
        flash_warning(
            request,
            "For your security, please choose a new password before continuing.",
            title="Change password",
        )
        return redirect("portal:password_change")
    return redirect("portal:home")


@require_http_methods(["GET", "POST"])
def portal_login(request):
    """Email + DOB/password login with device confirmation for new browsers."""
    if request.user.is_authenticated and user_can_use_member_portal(request.user):
        return _portal_post_login_redirect(request)

    form = MemberPortalLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        try:
            if portal_needs_device_confirmation(request, user):
                send_portal_device_confirmation(request, user)
                request.session["portal_pending_email"] = user.email
                request.session.modified = True
                return redirect("portal:confirm_sent")
            token = complete_portal_login(request, user, trust_device=True)
            response = _portal_post_login_redirect(request)
            return apply_trusted_device_cookie(response, token)
        except PortalAuthError as exc:
            flash_error(request, str(exc))

    from church_system.auth import _branding_context

    context = {"form": form}
    context.update(_branding_context())
    return render(request, "portal/login.html", context)


def confirm_sent(request):
    email = request.session.get("portal_pending_email", "")
    from church_system.auth import _branding_context

    context = {
        "email": email,
        "dev_confirm_url": request.session.get("portal_dev_confirm_url", ""),
    }
    context.update(_branding_context())
    return render(request, "portal/confirm_sent.html", context)


def confirm_device(request, token):
    try:
        user = resolve_confirm_token(token)
        device_token = complete_portal_login(request, user, trust_device=True)
        request.session.pop("portal_pending_email", None)
        request.session.pop("portal_dev_confirm_url", None)
        flash_success(request, "Device confirmed. Welcome to the member portal.")
        response = _portal_post_login_redirect(request)
        return apply_trusted_device_cookie(response, device_token)
    except PortalAuthError as exc:
        flash_error(request, str(exc))
        return redirect("portal:login")


@login_required
def home(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")

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
    live_meetings = []
    try:
        from announcements.calendar_services import attach_calendar_urls, get_communications_calendar

        upcoming = attach_calendar_urls(get_communications_calendar(request, days=30, limit=6))
    except Exception:
        upcoming = []

    church = getattr(member, "church", None) or getattr(request.user, "church", None)
    if church:
        from meetings import selectors as meeting_selectors

        live_meetings = list(meeting_selectors.portal_live_meetings_for_church(church, limit=5))

    return render(
        request,
        "portal/home.html",
        {
            "member": member,
            "giving_summary": giving_summary,
            "giving_lines": giving_lines,
            "giving_year": year,
            "has_payslips": has_payslips,
            "announcements": announcements,
            "upcoming_preview": upcoming,
            "live_meetings": live_meetings,
        },
    )


@login_required
def profile(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if member is None:
        flash_info(
            request,
            "Your account is not linked to a member record yet. Contact your church office.",
        )
    return render(request, "portal/profile.html", {"member": member})


@login_required
def announcement_detail(request, pk):
    """Portal-safe announcement reader (no staff chrome actions)."""
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    from announcements.services import mark_viewed, visible_announcements
    from announcements import selectors as ann_selectors

    announcement = ann_selectors.get_from_queryset_or_404(
        visible_announcements(request.user).prefetch_related("images"),
        pk,
    )
    mark_viewed(request.user, announcement)
    return render(
        request,
        "portal/announcement_detail.html",
        {"announcement": announcement, "member": member},
    )


@login_required
def meeting_live(request, pk):
    """Portal-safe Zoom join page for meetings marked show_on_portal."""
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")

    church = getattr(member, "church", None) or getattr(request.user, "church", None)
    if church is None:
        flash_info(request, "No church is linked to your portal account.")
        return redirect("portal:home")

    from meetings import selectors as meeting_selectors

    meeting = meeting_selectors.portal_live_meeting_or_404(church, pk)
    return render(
        request,
        "portal/meeting_live.html",
        {"meeting": meeting, "member": member},
    )


@login_required
@require_http_methods(["GET", "POST"])
def password_change(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    form = PortalPasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        flash_success(request, "Your password has been updated.")
        return redirect("portal:home")
    return render(
        request,
        "portal/password_change.html",
        {
            "form": form,
            "member": member,
            "forced": bool(getattr(request.user, "must_change_password", False)),
        },
    )


class PortalPasswordResetView(PasswordResetView):
    template_name = "portal/password_reset.html"
    email_template_name = "emails/portal_password_reset.txt"
    html_email_template_name = "emails/portal_password_reset.html"
    subject_template_name = "emails/portal_password_reset_subject.txt"
    form_class = PortalPasswordResetForm
    success_url = reverse_lazy("portal:password_reset_done")


class PortalPasswordResetDoneView(PasswordResetDoneView):
    template_name = "portal/password_reset_done.html"


class PortalPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "portal/password_reset_confirm.html"
    form_class = PortalSetPasswordForm
    success_url = reverse_lazy("portal:password_reset_complete")


class PortalPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "portal/password_reset_complete.html"
