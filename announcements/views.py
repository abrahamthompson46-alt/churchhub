"""Announcement views — service-layer create/approve/reject/archive."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from announcements import repositories as repo
from announcements import selectors
from church_system.church_scope import get_active_church, get_user_church
from church_system.flash import flash_exception, flash_info, flash_success
from permissions.checks import (
    can_approve_announcements,
    can_create_announcements,
    permission_required,
)
from reports.exporters import export_table_csv, export_table_excel

from .forms import (
    AnnouncementEditForm,
    AnnouncementForm,
    AnnouncementImageFormSet,
    AnnouncementRejectForm,
)
from .services import (
    AnnouncementServiceError,
    approve_announcement,
    archive_announcement,
    can_archive_announcement,
    can_edit_announcement,
    create_announcement,
    export_announcements_table,
    get_announcement_list_queryset,
    get_my_announcements_queryset,
    mark_viewed,
    paginate_queryset,
    pending_for_user,
    reject_announcement,
    update_announcement,
    visible_announcements,
)


def _notify_creator(user, title, message, action_url=""):
    if not user:
        return
    from dashboard.services import notify_user

    notify_user(user, title, message, category="INFO", action_url=action_url)


def create_required(view_func):
    @login_required
    @permission_required("create_announcements")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def approve_required(view_func):
    @login_required
    @permission_required("approve_announcements")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


@create_required
def create_announcement_view(request):
    if request.method == "POST":
        form = AnnouncementForm(request.POST, user=request.user)
        formset = AnnouncementImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            try:
                announcement = create_announcement(
                    request.user,
                    title=form.cleaned_data["title"],
                    content=form.cleaned_data["content"],
                    visibility=form.cleaned_data["visibility"],
                    church=form.cleaned_data.get("church"),
                    event_date=form.cleaned_data.get("event_date"),
                    publish_at=form.cleaned_data.get("publish_at"),
                    auto_expire=form.cleaned_data.get("auto_expire", True),
                )
                formset.instance = announcement
                repo.save_image_formset(formset)
                if announcement.is_approved:
                    flash_success(request, "Announcement published.")
                else:
                    flash_info(request, "Announcement submitted for approval.")
                return redirect("announcements:my_announcements")
            except (PermissionError, AnnouncementServiceError) as exc:
                flash_exception(request, exc, title="Could not create announcement")
    else:
        form = AnnouncementForm(user=request.user)
        formset = AnnouncementImageFormSet()
        church = get_user_church(request.user) or get_active_church(request)
        if church and "church" in form.fields:
            form.fields["church"].initial = church

    return render(request, "announcements/create_announcement.html", {
        "form": form,
        "formset": formset,
        "breadcrumbs": [
            {"label": "Announcements", "url": reverse("announcements:announcement_list")},
            {"label": "Create"},
        ],
    })


@login_required
def announcement_list(request):
    q = (request.GET.get("q") or "").strip()
    pinned_only = request.GET.get("pinned") == "1"
    qs = get_announcement_list_queryset(request.user, q=q, pinned_only=pinned_only)

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel") and can_approve_announcements(request.user):
        payload = export_announcements_table(qs)
        repo.create_audit_log(
            announcement=None,
            church=get_user_church(request.user),
            action="EXPORT",
            performed_by=request.user,
            details={"format": export_fmt, "count": len(payload["rows"])},
        )
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="announcements_list",
            export_format=export_fmt,
            row_count=len(payload["rows"]),
            church=get_user_church(request.user),
            params={"count": len(payload["rows"]), "q": q, "pinned_only": pinned_only},
        )
        if export_fmt == "csv":
            return export_table_csv(payload["headers"], payload["rows"], "announcements.csv")
        return export_table_excel(
            payload["headers"], payload["rows"], "announcements.xlsx", payload["title"]
        )

    page_obj = paginate_queryset(qs, page=request.GET.get("page", 1), per_page=15)
    viewed_ids = selectors.viewed_announcement_ids_for_user(
        request.user, [a.pk for a in page_obj]
    )
    return render(request, "announcements/announcement_list.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
        "viewed_ids": viewed_ids,
        "q": q,
        "pinned_only": pinned_only,
        "can_export": can_approve_announcements(request.user),
        "can_create": can_create_announcements(request.user),
    })


@login_required
def announcement_detail(request, pk):
    announcement = selectors.get_announcement_detail_or_404(pk)
    # Allow creator / approver to see pending/rejected; others only visible published
    can_see = (
        announcement.created_by_id == request.user.id
        or can_approve_announcements(request.user)
        or selectors.announcement_exists_in_qs(visible_announcements(request.user), pk)
    )
    if not can_see:
        raise PermissionDenied

    mark_viewed(request.user, announcement)
    view_count = selectors.announcement_view_count(announcement)
    return render(request, "announcements/detail.html", {
        "announcement": announcement,
        "view_count": view_count,
        "can_edit": can_edit_announcement(request.user, announcement),
        "can_archive": can_archive_announcement(request.user, announcement),
    })


@login_required
def my_announcements(request):
    status = request.GET.get("status", "")
    qs = get_my_announcements_queryset(request.user, status=status)
    page_obj = paginate_queryset(qs, page=request.GET.get("page", 1), per_page=25)
    return render(request, "announcements/my_announcements.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
        "status": status,
    })


@approve_required
def pending_approvals(request):
    pending = pending_for_user(request.user).order_by("-created_at")
    page_obj = paginate_queryset(pending, page=request.GET.get("page", 1), per_page=25)
    return render(request, "announcements/pending.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
        "can_approve": True,
        "reject_form": AnnouncementRejectForm(),
    })


@approve_required
@require_POST
def approve_announcement_view(request, pk):
    announcement = selectors.get_announcement_or_404(
        pk, is_archived=False, is_rejected=False
    )
    try:
        approve_announcement(announcement, request.user)
        flash_success(request, f'"{announcement.title}" approved and published.')
        if announcement.created_by_id and announcement.created_by_id != request.user.id:
            _notify_creator(
                announcement.created_by,
                "Announcement approved",
                f'Your announcement "{announcement.title}" has been approved.',
                f"/announcements/{announcement.pk}/",
            )
    except (PermissionError, AnnouncementServiceError, ValueError) as exc:
        flash_exception(request, str(exc))
    return redirect("announcements:pending_approvals")


@approve_required
@require_POST
def reject_announcement_view(request, pk):
    announcement = selectors.get_announcement_or_404(
        pk, is_archived=False, is_approved=False, is_rejected=False
    )
    form = AnnouncementRejectForm(request.POST)
    if not form.is_valid():
        flash_exception(request, "A rejection reason is required.", title="Reject failed")
        return redirect("announcements:pending_approvals")
    try:
        creator, title, _ann = reject_announcement(
            announcement, request.user, reason=form.cleaned_data["reason"]
        )
        flash_success(request, f'"{title}" rejected.')
        if creator and creator.id != request.user.id:
            _notify_creator(
                creator,
                "Announcement rejected",
                f'Your announcement "{title}" was not approved. Reason: {form.cleaned_data["reason"]}',
            )
    except (PermissionError, AnnouncementServiceError, ValueError) as exc:
        flash_exception(request, str(exc))
    return redirect("announcements:pending_approvals")


@login_required
def edit_announcement(request, pk):
    announcement = selectors.get_announcement_or_404(pk)
    if not can_edit_announcement(request.user, announcement):
        raise PermissionDenied
    if request.method == "POST":
        form = AnnouncementEditForm(request.POST, instance=announcement, user=request.user)
        formset = AnnouncementImageFormSet(request.POST, request.FILES, instance=announcement)
        if form.is_valid() and formset.is_valid():
            try:
                update_announcement(
                    announcement,
                    request.user,
                    title=form.cleaned_data["title"],
                    content=form.cleaned_data["content"],
                    visibility=form.cleaned_data["visibility"],
                    church=form.cleaned_data.get("church"),
                    event_date=form.cleaned_data.get("event_date"),
                    publish_at=form.cleaned_data.get("publish_at"),
                    auto_expire=form.cleaned_data.get("auto_expire"),
                    is_pinned=form.cleaned_data.get("is_pinned")
                    if "is_pinned" in form.cleaned_data
                    else None,
                )
                repo.save_image_formset(formset)
                flash_success(request, "Announcement updated.")
                if announcement.is_approved:
                    return redirect("announcements:announcement_detail", pk=announcement.pk)
                return redirect("announcements:my_announcements")
            except (PermissionError, AnnouncementServiceError) as exc:
                flash_exception(request, exc, title="Could not update")
    else:
        form = AnnouncementEditForm(instance=announcement, user=request.user)
        formset = AnnouncementImageFormSet(instance=announcement)

    return render(request, "announcements/edit.html", {
        "form": form,
        "formset": formset,
        "announcement": announcement,
    })


@login_required
@require_POST
def archive_announcement_view(request, pk):
    announcement = selectors.get_announcement_or_404(pk, is_archived=False)
    try:
        archive_announcement(announcement, request.user)
        flash_success(request, f'"{announcement.title}" archived.')
    except PermissionError as exc:
        flash_exception(request, str(exc))
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("announcements:announcement_list")


@login_required
def track_view(request, pk):
    announcement = selectors.get_from_queryset_or_404(
        visible_announcements(request.user), pk
    )
    mark_viewed(request.user, announcement)
    return redirect("announcements:announcement_list")


def _attach_calendar_urls(items):
    from .calendar_services import attach_calendar_urls

    return attach_calendar_urls(items)


@login_required
def upcoming_calendar(request):
    from datetime import timedelta

    from permissions.checks import can_manage_meetings, can_manage_members, can_view_members

    from .calendar_services import (
        calendar_summary_counts,
        get_communications_calendar,
        group_calendar_by_date,
    )

    try:
        days = int(request.GET.get("days", 60))
    except (TypeError, ValueError):
        days = 60
    days = max(7, min(days, 365))

    category = request.GET.get("category", "all")
    items = get_communications_calendar(request, days=days, category=category)
    _attach_calendar_urls(items)

    if not can_view_members(request.user) and not can_manage_members(request.user):
        for item in items:
            if item["kind"] == "birthday":
                item["url"] = ""

    from django.utils import timezone

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    grouped = group_calendar_by_date(items)

    create_meeting_url = ""
    if can_manage_meetings(request.user):
        try:
            create_meeting_url = reverse("meetings:create")
        except Exception:
            create_meeting_url = ""

    return render(request, "announcements/upcoming_calendar.html", {
        "items": items,
        "grouped_items": grouped,
        "counts": calendar_summary_counts(request, days=days),
        "category": category,
        "days": days,
        "today": today,
        "tomorrow": tomorrow,
        "create_meeting_url": create_meeting_url,
        "breadcrumbs": [
            {"label": "Communications", "url": "/announcements/"},
            {"label": "Upcoming"},
        ],
    })
