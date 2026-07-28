from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import can_approve_transactions, can_manage_finances
from announcements.services import pending_for_user
from church_system.church_scope import get_active_church
from church_system.flash import flash_exception, flash_success, flash_warning
from dashboard import repositories as repo
from dashboard import selectors
from dashboard.services import (
    _compute_remittance_payable_mtd,
    build_home_context,
    get_quick_actions,
)
from dashboard.utils import safe_internal_redirect
from transactions.models import MonthlyCutoff
from transactions.services import generate_monthly_cutoff


def _apply_church_switch(request, church_param):
    """
    Set or clear session church from a query/form value.

    Empty string or 'all' clears current_church_id. A valid UUID among
    manageable churches sets it.
    """
    if church_param is None:
        return
    value = str(church_param).strip()
    if value == "" or value.lower() == "all":
        request.session.pop("current_church_id", None)
        return
    church = selectors.manageable_church_by_pk(request.user, value)
    if church:
        request.session["current_church_id"] = str(church.id)


@login_required
def teller_console_api(request):
    """JSON feed for live teller daily summary (auto-refresh on dashboard)."""
    from permissions.checks import can_manage_finances, can_view_transactions
    from transactions.treasury import get_cash_position, get_teller_daily_summary

    if not (can_manage_finances(request.user) or can_view_transactions(request.user)):
        return JsonResponse({"error": "forbidden"}, status=403)

    church = get_active_church(request)
    if not church:
        return JsonResponse({"error": "no_church", "tellers": [], "totals": {}})

    summary = get_teller_daily_summary(church)
    cash = get_cash_position(church)

    def _dec(value):
        return f"{value:.2f}"

    return JsonResponse({
        "business_date": summary["business_date"].isoformat() if summary["business_date"] else None,
        "working_day_open": summary["working_day_open"],
        "tellers": [
            {
                **{k: v for k, v in row.items() if k not in ("receipts", "expenses", "transfers")},
                "receipts": _dec(row["receipts"]),
                "expenses": _dec(row["expenses"]),
                "transfers": _dec(row["transfers"]),
            }
            for row in summary["tellers"]
        ],
        "totals": {
            "entries": summary["totals"].get("entries", 0),
            "receipts": _dec(summary["totals"].get("receipts", 0)),
            "expenses": _dec(summary["totals"].get("expenses", 0)),
            "transfers": _dec(summary["totals"].get("transfers", 0)),
            "pending": summary["totals"].get("pending", 0),
        },
        "cash_position": {
            "cash": _dec(cash["cash"]),
            "bank": _dec(cash["bank"]),
            "petty_cash": _dec(cash["petty_cash"]),
            "total_liquid": _dec(cash["total_liquid"]),
        },
    })


@login_required
def home(request):
    if "church" in request.GET:
        _apply_church_switch(request, request.GET.get("church"))
        # Redirect so get_active_church never sees church=all / empty as a UUID
        return redirect("dashboard:home")

    context = build_home_context(request)
    return render(request, "dashboard/home.html", context)


@login_required
@require_POST
def pin_quick_action(request):
    """Pin or unpin a quick-action label in session (max 3)."""
    label = (request.POST.get("label") or "").strip()
    actions = get_quick_actions(request.user)
    valid = {a.get("label") for a in actions if a.get("label")}
    pinned = list(request.session.get("dashboard_pinned_labels") or [])
    if label in valid:
        if label in pinned:
            pinned = [entry for entry in pinned if entry != label]
        else:
            pinned = [label] + [entry for entry in pinned if entry != label]
            pinned = pinned[:3]
        request.session["dashboard_pinned_labels"] = pinned
    return redirect("dashboard:home")


@login_required
def switch_church(request):
    if "church" in request.GET:
        _apply_church_switch(request, request.GET.get("church"))
    return redirect("dashboard:home")


@login_required
def notification_list(request):
    unread_only = request.GET.get("unread") == "1"
    category = (request.GET.get("category") or "").strip().upper()
    qs = selectors.notifications_for_user(
        request.user, unread_only=unread_only, category=category
    )
    unread = selectors.unread_notification_count(request.user)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    from dashboard.models import Notification

    return render(request, "dashboard/notifications.html", {
        "notifications": page_obj,
        "page_obj": page_obj,
        "unread_count": unread,
        "unread_only": unread_only,
        "category": category,
        "categories": Notification.CATEGORY_CHOICES,
    })


@login_required
@require_POST
def notification_mark_read(request, pk):
    notification = selectors.notification_for_user(request.user, pk)
    repo.mark_notification_read(notification)

    follow = request.POST.get("follow")
    if follow and notification.action_url:
        target = safe_internal_redirect(notification.action_url, None)
        if target:
            return redirect(target)

    next_url = request.POST.get("next") or ""
    safe_next = safe_internal_redirect(next_url, None)
    if safe_next:
        return redirect(safe_next)

    return redirect("dashboard:notifications")


@login_required
@require_POST
def notification_delete(request, pk):
    notification = selectors.notification_for_user(request.user, pk)
    repo.delete_notification(notification)
    flash_success(request, "Notification removed.")
    return redirect("dashboard:notifications")


@login_required
@require_POST
def notification_mark_all_read(request):
    repo.mark_all_notifications_read(request.user)
    flash_success(request, "All notifications marked as read.", title="Inbox updated")
    return redirect("dashboard:notifications")


@login_required
def notification_count(request):
    count = selectors.unread_notification_count(request.user)
    return JsonResponse({"count": count})


@login_required
def custom_logout(request):
    from church_system.denomination_scope import get_active_denomination

    denomination = get_active_denomination(request)
    denomination_id = str(denomination.pk) if denomination else None
    logout(request)
    if denomination_id:
        request.session["active_denomination_id"] = denomination_id
    return render(request, "logged_out.html")


@login_required
def cutoff(request):
    if not can_manage_finances(request.user):
        return HttpResponseForbidden("Finance permission required.")

    try:
        church = get_active_church(request)
        if not church:
            flash_warning(
                request,
                "Choose a church from the toolbar to view cut-off totals.",
                title="Church required",
            )
            return render(request, "dashboard/cutoff.html", {
                "monthly_total": 0,
                "can_recompute": False,
            })

        now = timezone.now()
        month_start = now.date().replace(day=1)

        if request.method == "POST" and (
            request.POST.get("recompute") == "1" or request.GET.get("recompute") == "1"
        ):
            cutoff_obj = generate_monthly_cutoff(church, now.date())
            flash_success(
                request,
                "Monthly cut-off totals recomputed from remittance payable accounts.",
                title="Cut-off updated",
            )
            return redirect("dashboard:cutoff")

        # GET — display only; never create/mutate MonthlyCutoff
        cutoff_obj = selectors.monthly_cutoff_for_church_month(church, month_start)
        if cutoff_obj:
            monthly_total = cutoff_obj.total_payable
            total_tithe = cutoff_obj.total_tithe
            total_combined = cutoff_obj.total_combined
        else:
            total_tithe, total_combined, monthly_total = _compute_remittance_payable_mtd(
                church, month_start
            )
            # Lightweight display object without saving
            cutoff_obj = MonthlyCutoff(
                church=church,
                month=month_start,
                total_tithe=total_tithe,
                total_combined=total_combined,
                transferred=False,
            )

        return render(request, "dashboard/cutoff.html", {
            "monthly_total": monthly_total,
            "cutoff": cutoff_obj,
            "cutoff_persisted": cutoff_obj.pk is not None,
            "can_recompute": True,
            "can_remit": (
                can_manage_finances(request.user)
                and can_approve_transactions(request.user)
                and not cutoff_obj.transferred
                and cutoff_obj.pk is not None
            ),
        })
    except Exception as exc:
        flash_exception(request, exc, title="Cut-off unavailable")
        return render(request, "dashboard/cutoff.html", {
            "monthly_total": 0,
            "can_recompute": False,
        })


@login_required
def pending_announcements_ajax(request):
    from accounts.permissions import can_approve_announcements

    count = pending_for_user(request.user).count() if can_approve_announcements(request.user) else 0
    return JsonResponse({"count": count})
