"""Member portal views — self-service home for linked members."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
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


def confirm_device(request, path_token=None):
    from urllib.parse import unquote

    raw = path_token or request.GET.get("token", "")
    token = unquote(raw).strip()
    if not token:
        flash_error(request, "This confirmation link is invalid or has expired.")
        return redirect("portal:login")
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
    year_param = request.GET.get("year")
    if year_param:
        try:
            year = int(year_param)
        except (TypeError, ValueError):
            pass

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
    welfare_enabled = False
    welfare_summary = None
    if member:
        from remittance.welfare_services import member_welfare_summary, welfare_module_enabled

        welfare_enabled = welfare_module_enabled(member.church, request.user)
        if welfare_enabled:
            welfare_summary = member_welfare_summary(member, year=year)

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
            "giving_year_choices": list(
                range(timezone.localdate().year, timezone.localdate().year - 6, -1)
            ),
            "has_payslips": has_payslips,
            "announcements": announcements,
            "upcoming_preview": upcoming,
            "live_meetings": live_meetings,
            "welfare_enabled": welfare_enabled,
            "welfare_summary": welfare_summary,
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


def _require_portal_submissions_view(user):
    from permissions.checks import can_view_portal_submissions

    return can_view_portal_submissions(user)


@login_required
@user_passes_test(_require_portal_submissions_view)
def staff_submission_list(request):
    import csv

    from django.http import HttpResponse

    from permissions.checks import can_manage_portal_submissions

    from .models import SpiritualSubmissionKind, SpiritualSubmissionStatus
    from .spiritual_services import mark_submission_reviewed, submissions_for_staff_queryset

    kind = (request.GET.get("kind") or "").strip().upper()
    status = (request.GET.get("status") or SpiritualSubmissionStatus.NEW).strip().upper()
    qs = submissions_for_staff_queryset(request.user, request)
    if kind in SpiritualSubmissionKind.values:
        qs = qs.filter(kind=kind)
    if status in SpiritualSubmissionStatus.values:
        qs = qs.filter(status=status)

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="portal_submissions.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "created_at",
                "church",
                "kind",
                "status",
                "from",
                "title",
                "body",
                "anonymous",
            ]
        )
        for row in qs.order_by("-created_at")[:2000]:
            if row.is_anonymous and row.kind == SpiritualSubmissionKind.PRAYER:
                who = "Anonymous"
            elif row.member_id:
                who = row.member.full_name
            else:
                who = ""
            writer.writerow(
                [
                    row.created_at.isoformat(),
                    row.church.name,
                    row.kind,
                    row.status,
                    who,
                    row.title,
                    row.body,
                    "yes" if row.is_anonymous else "no",
                ]
            )
        return response

    if request.method == "POST" and can_manage_portal_submissions(request.user):
        pk = request.POST.get("submission_id")
        sub = submissions_for_staff_queryset(request.user, request).filter(pk=pk).first()
        if sub:
            mark_submission_reviewed(sub, request.user)
            flash_success(request, "Marked as reviewed.")
            return redirect(request.get_full_path())

    submissions = list(qs[:100])
    return render(
        request,
        "portal/staff_submissions.html",
        {
            "submissions": submissions,
            "filter_kind": kind,
            "filter_status": status,
            "kind_choices": SpiritualSubmissionKind.choices,
            "status_choices": SpiritualSubmissionStatus.choices,
            "can_manage": can_manage_portal_submissions(request.user),
            "filter_qs": request.GET.urlencode(),
        },
    )


@login_required
def praise_wall(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")

    from .spiritual_services import praise_wall_for_church

    church = member.church if member and member.church_id else getattr(request.user, "church", None)
    entries = list(praise_wall_for_church(church))
    return render(
        request,
        "portal/praise_wall.html",
        {"member": member, "church": church, "entries": entries},
    )


@login_required
@require_http_methods(["GET", "POST"])
def prayer_request(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if member is None:
        flash_info(request, "Link your account to a member profile before submitting prayer requests.")
        return redirect("portal:home")

    from .spiritual_forms import PrayerRequestForm
    from .spiritual_services import create_spiritual_submission, member_submissions_for_user
    from .models import SpiritualSubmissionKind

    form = PrayerRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            from .spiritual_services import PortalSubmitRateLimitError, assert_portal_submit_allowed

            assert_portal_submit_allowed(request)
            create_spiritual_submission(
                user=request.user,
                member=member,
                kind=SpiritualSubmissionKind.PRAYER,
                body=form.cleaned_data["body"],
                is_anonymous=form.cleaned_data.get("is_anonymous", False),
            )
            flash_success(request, "Your prayer request was shared with the pastoral care team.")
            return redirect("portal:prayer_request")
        except PortalSubmitRateLimitError as exc:
            flash_error(request, str(exc))
        except ValueError as exc:
            flash_error(request, str(exc))

    history = list(member_submissions_for_user(request.user, member, kind=SpiritualSubmissionKind.PRAYER, limit=10))
    return render(
        request,
        "portal/prayer_request.html",
        {"form": form, "member": member, "history": history},
    )


@login_required
@require_http_methods(["GET", "POST"])
def thanksgiving_testimony(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if member is None:
        flash_info(request, "Link your account to a member profile before sharing thanksgiving or testimony.")
        return redirect("portal:home")

    from .spiritual_forms import ThanksgivingTestimonyForm
    from .models import SpiritualSubmission, SpiritualSubmissionKind
    from .spiritual_services import create_spiritual_submission, member_submissions_for_user

    form = ThanksgivingTestimonyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            from .spiritual_services import PortalSubmitRateLimitError, assert_portal_submit_allowed

            assert_portal_submit_allowed(request)
            create_spiritual_submission(
                user=request.user,
                member=member,
                kind=form.cleaned_data["kind"],
                title=form.cleaned_data.get("title", ""),
                body=form.cleaned_data["body"],
            )
            flash_success(request, "Thank you — your message was shared with church leadership.")
            return redirect("portal:thanksgiving_testimony")
        except PortalSubmitRateLimitError as exc:
            flash_error(request, str(exc))
        except ValueError as exc:
            flash_error(request, str(exc))

    history = list(
        SpiritualSubmission.objects.filter(
            member=member,
            kind__in=(SpiritualSubmissionKind.THANKSGIVING, SpiritualSubmissionKind.TESTIMONY),
        ).order_by("-created_at")[:10]
    )
    return render(
        request,
        "portal/thanksgiving_testimony.html",
        {"form": form, "member": member, "history": history},
    )


@login_required
def my_welfare(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if not member:
        flash_info(request, "Link your account to a member profile to view welfare.")
        return redirect("portal:home")

    from django.core.exceptions import PermissionDenied

    from portal.welfare_services import (
        build_portal_welfare_page,
        parse_portal_welfare_filters,
        require_portal_welfare_access,
        welfare_statement_export_rows,
    )
    from reports.exporters import export_table_csv, export_table_excel, export_table_pdf
    from reports.services import audit_export

    try:
        require_portal_welfare_access(request.user, member)
    except PermissionDenied:
        flash_info(request, "Welfare self-service is not available for your church yet.")
        return redirect("portal:home")

    filters = parse_portal_welfare_filters(request.GET)
    page = build_portal_welfare_page(member, filters)

    export_fmt = (request.GET.get("export") or "").strip().lower()
    if export_fmt in ("csv", "excel", "pdf"):
        headers, rows = welfare_statement_export_rows(page["statement"])
        slug = f"my-welfare-{member.pk}"
        audit_export(
            user=request.user,
            report_key="portal_welfare_statement",
            export_format=export_fmt,
            row_count=len(rows),
            church=member.church,
            params=filters.query_dict(),
        )
        title = f"My Welfare — {member.full_name}"
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        if export_fmt == "excel":
            return export_table_excel(headers, rows, f"{slug}.xlsx", "Welfare")
        return export_table_pdf(headers, rows, "My Welfare Statement", member.full_name, f"{slug}.pdf")

    return render(
        request,
        "portal/welfare.html",
        {
            "member": member,
            "export_csv_href": "?" + filters.export_query("csv"),
            "export_excel_href": "?" + filters.export_query("excel"),
            "export_pdf_href": "?" + filters.export_query("pdf"),
            **page,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def welfare_request(request):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if not member:
        return redirect("portal:home")

    from django.core.exceptions import PermissionDenied

    from portal.forms import PortalWelfareRequestForm
    from portal.welfare_services import require_portal_welfare_access
    from remittance.services import RemittancePolicyError
    from remittance.welfare_services import create_welfare_case

    try:
        require_portal_welfare_access(request.user, member)
    except PermissionDenied:
        flash_info(request, "Welfare requests are not available for your church yet.")
        return redirect("portal:home")

    form = PortalWelfareRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            case = create_welfare_case(
                member.church,
                member,
                form.cleaned_data["amount_requested"],
                form.cleaned_data["reason"],
                request.user,
                assistance_type=form.cleaned_data["assistance_type"],
                priority=form.cleaned_data["priority"],
            )
            flash_success(
                request,
                f"Your request {case.case_number} was submitted. The welfare team will review it.",
            )
            return redirect("portal:welfare_case", pk=case.pk)
        except RemittancePolicyError as exc:
            flash_error(request, str(exc))

    return render(
        request,
        "portal/welfare_request.html",
        {"form": form, "member": member},
    )


@login_required
def welfare_case_detail(request, pk):
    member, denied = _portal_member_or_redirect(request)
    if denied:
        return denied
    if getattr(request.user, "must_change_password", False):
        return redirect("portal:password_change")
    if not member:
        return redirect("portal:home")

    from django.core.exceptions import PermissionDenied

    from portal.welfare_services import (
        member_safe_case_detail,
        portal_welfare_case_for_member,
        require_portal_welfare_access,
    )

    try:
        require_portal_welfare_access(request.user, member)
    except PermissionDenied:
        return redirect("portal:home")

    case = portal_welfare_case_for_member(member, pk)
    if not case:
        raise PermissionDenied
    detail = member_safe_case_detail(case)
    return render(
        request,
        "portal/welfare_case.html",
        {"member": member, **detail},
    )
