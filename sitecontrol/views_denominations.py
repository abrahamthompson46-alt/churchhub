"""Platform denomination management — profiles, branding, billing, audit."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from church_system.flash import flash_success
from sitecontrol.billing_services import (
    all_denominations_billing_rollups,
    denomination_audit_log,
    denomination_billing_summary,
    tenant_health_alerts_for_denomination,
)
from sitecontrol.checks import platform_required, require_platform_capability
from sitecontrol.denomination_forms import (
    DenominationBrandingForm,
    DenominationSeedForm,
    DenominationTerminologyForm,
)
from sitecontrol.denomination_services import (
    ensure_builtin_denominations,
    get_terminology_context,
    hierarchy_chain_description,
)
from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.forms import DenominationForm
from sitecontrol.denomination_purge_services import (
    DenominationPurgeError,
    denomination_purge_preview,
    purge_denomination_completely,
    validate_denomination_purge,
)
from sitecontrol.platform_access import operator_can_access_denomination, operator_has_global_access
from sitecontrol.rbac import CAP_MANAGE_DENOMINATIONS, CAP_VIEW, CAP_VIEW_BILLING
from sitecontrol.services import log_platform_action


def _breadcrumbs(*crumbs):
    return [{"label": c[0], **({"url": c[1]} if len(c) > 1 else {})} for c in crumbs]


def _require_denomination_access(request, denomination):
    if not operator_can_access_denomination(request.user, denomination):
        raise PermissionDenied("You do not have access to this denomination.")


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_list(request):
    from sitecontrol.platform_access import get_operator_denominations

    denominations = get_operator_denominations(request.user)
    return render(request, "sitecontrol/denomination_list.html", {
        "denominations": denominations,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Denominations",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_detail(request, pk):
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    terminology = get_terminology_context(denomination)
    conference_count = selectors.conference_count_for_denomination(denomination)
    church_count = selectors.church_count_for_denomination(denomination)
    billing = denomination_billing_summary(denomination)
    alerts = tenant_health_alerts_for_denomination(denomination)
    recent_audit = denomination_audit_log(denomination, limit=8)
    can_purge = operator_has_global_access(request.user)
    purge_blocked_reason = ""
    if can_purge:
        try:
            validate_denomination_purge(denomination)
        except DenominationPurgeError as exc:
            purge_blocked_reason = str(exc)
    return render(request, "sitecontrol/denomination_detail.html", {
        "denomination": denomination,
        "terminology": terminology,
        "hierarchy_chain": hierarchy_chain_description(denomination),
        "conference_count": conference_count,
        "church_count": church_count,
        "billing": billing,
        "alerts": alerts,
        "recent_audit": recent_audit,
        "can_purge": can_purge,
        "purge_blocked_reason": purge_blocked_reason,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name,),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_edit(request, pk=None):
    denomination = selectors.get_denomination_or_404(pk) if pk else None
    if denomination:
        _require_denomination_access(request, denomination)
    form = DenominationForm(request.POST or None, request.FILES or None, instance=denomination)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        repo.save_model(obj)
        log_platform_action(
            request,
            "DENOMINATION_UPDATE" if pk else "DENOMINATION_CREATE",
            f"Denomination {obj.name} saved",
            target_model="Denomination",
            target_id=obj.pk,
            denomination=obj,
        )
        flash_success(request, f"Denomination “{obj.name}” saved.")
        return redirect("sitecontrol:denomination_detail", pk=obj.pk)
    title = f"Edit {denomination.name}" if denomination else "Add Denomination"
    return render(request, "sitecontrol/denomination_form.html", {
        "form": form,
        "denomination": denomination,
        "title": title,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (title,),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_terminology(request, pk):
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    form = DenominationTerminologyForm(denomination, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save(denomination)
        log_platform_action(
            request,
            "DENOMINATION_TERMINOLOGY",
            f"Updated hierarchy labels for {denomination.name}",
            target_model="Denomination",
            target_id=denomination.pk,
            denomination=denomination,
        )
        flash_success(request, "Hierarchy terminology saved.")
        return redirect("sitecontrol:denomination_detail", pk=pk)
    return render(request, "sitecontrol/denomination_terminology.html", {
        "form": form,
        "denomination": denomination,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name, f"/platform/denominations/{pk}/"),
            ("Terminology",),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_seeds(request, pk):
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    form = DenominationSeedForm(denomination, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save(denomination)
        log_platform_action(
            request,
            "DENOMINATION_SEEDS_CONFIG",
            f"Updated seed config for {denomination.name}",
            target_model="Denomination",
            target_id=denomination.pk,
            denomination=denomination,
        )
        flash_success(request, "Seed configuration saved.")
        return redirect("sitecontrol:denomination_detail", pk=pk)
    return render(request, "sitecontrol/denomination_seeds.html", {
        "form": form,
        "denomination": denomination,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name, f"/platform/denominations/{pk}/"),
            ("Seed Config",),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_branding(request, pk):
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    form = DenominationBrandingForm(request.POST or None, request.FILES or None, instance=denomination)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        from sitecontrol.branding_services import clear_branding_caches

        clear_branding_caches()
        log_platform_action(
            request,
            "DENOMINATION_UPDATE",
            f"Updated branding for {denomination.name}",
            target_model="Denomination",
            target_id=denomination.pk,
            denomination=denomination,
        )
        flash_success(
            request,
            "Tenant branding saved. Churches under this denomination will see updated colors on next page load.",
        )
        return redirect("sitecontrol:denomination_branding", pk=pk)
    preview_branding = None
    if denomination:
        from sitecontrol.branding_services import resolve_institution_branding

        preview_branding = resolve_institution_branding(denomination=denomination)
    return render(request, "sitecontrol/denomination_branding.html", {
        "form": form,
        "denomination": denomination,
        "preview_branding": preview_branding,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name, f"/platform/denominations/{pk}/"),
            ("Branding",),
        ),
    })


@platform_required
@require_platform_capability(CAP_VIEW_BILLING)
def denomination_billing(request, pk):
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    summary = denomination_billing_summary(denomination)
    audit = denomination_audit_log(denomination, limit=30)
    log_platform_action(
        request,
        "DENOMINATION_BILLING_VIEW",
        f"Viewed billing for {denomination.name}",
        target_model="Denomination",
        target_id=denomination.pk,
        denomination=denomination,
    )
    return render(request, "sitecontrol/denomination_billing.html", {
        "denomination": denomination,
        "summary": summary,
        "audit_entries": audit,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name, f"/platform/denominations/{pk}/"),
            ("Billing",),
        ),
    })


@platform_required
@require_platform_capability(CAP_VIEW_BILLING)
def denomination_billing_rollups(request):
    from sitecontrol.platform_access import get_operator_denominations

    allowed_ids = set(get_operator_denominations(request.user).values_list("pk", flat=True))
    rollups = [r for r in all_denominations_billing_rollups() if r["denomination"].pk in allowed_ids]
    return render(request, "sitecontrol/denomination_billing_rollups.html", {
        "rollups": rollups,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            ("Billing Roll-ups",),
        ),
    })


@platform_required
@require_platform_capability(CAP_VIEW)
def denomination_set_context(request, pk):
    """Set active platform denomination filter in session."""
    if request.method != "POST":
        return redirect("sitecontrol:denomination_list")
    denomination = selectors.get_active_denomination_or_404(pk)
    _require_denomination_access(request, denomination)
    request.session["active_denomination_id"] = str(denomination.pk)
    flash_success(request, f"Platform context set to {denomination.display_name}.")
    from dashboard.utils import safe_internal_redirect

    next_url = safe_internal_redirect(request.POST.get("next"), None)
    if next_url:
        return redirect(next_url)
    return redirect("sitecontrol:denomination_detail", pk=pk)


@platform_required
@require_platform_capability(CAP_VIEW)
def denomination_clear_context(request):
    """Clear platform denomination session filter."""
    if request.method != "POST":
        return redirect("sitecontrol:denomination_list")
    request.session.pop("active_denomination_id", None)
    flash_success(request, "Platform denomination filter cleared.")
    from dashboard.utils import safe_internal_redirect

    return redirect(
        safe_internal_redirect(request.POST.get("next"), "sitecontrol:denomination_list")
    )


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_purge(request, pk):
    """Multi-step permanent deletion with repeated warnings and password verification."""
    denomination = selectors.get_denomination_or_404(pk)
    _require_denomination_access(request, denomination)

    if not operator_has_global_access(request.user):
        raise PermissionDenied("Only platform owners may permanently delete denominations.")

    session_reason_key = f"denom_purge_reason_{pk}"

    try:
        validate_denomination_purge(denomination)
    except DenominationPurgeError as exc:
        messages.error(request, str(exc))
        return redirect("sitecontrol:denomination_detail", pk=pk)

    preview = denomination_purge_preview(denomination)
    step = 1
    reason = ""

    if request.method == "POST":
        step = int(request.POST.get("step", 1))
        if step == 1:
            required = ("ack_irreversible", "ack_financial", "ack_authority")
            if not all(request.POST.get(key) == "yes" for key in required):
                messages.error(request, "Confirm all warnings before continuing.")
            else:
                step = 2
        elif step == 2:
            confirm_code = request.POST.get("confirm_code", "").strip()
            reason = request.POST.get("reason", "").strip()
            if confirm_code != denomination.code:
                messages.error(request, "Denomination code does not match.")
            elif not reason:
                messages.error(request, "A reason for deletion is required.")
            elif request.POST.get("ack_final") != "yes":
                messages.error(request, "Confirm the final acknowledgement.")
            else:
                request.session[session_reason_key] = reason
                step = 3
        elif step == 3:
            reason = request.session.get(session_reason_key, "").strip()
            if not reason:
                messages.error(request, "Session expired. Start the deletion flow again.")
                return redirect("sitecontrol:denomination_purge", pk=pk)
            if request.POST.get("confirm_phrase", "").strip() != "DELETE PERMANENTLY":
                messages.error(request, 'Type DELETE PERMANENTLY to confirm.')
            elif not request.user.check_password(request.POST.get("password", "")):
                messages.error(request, "Incorrect password.")
            else:
                try:
                    result = purge_denomination_completely(
                        denomination,
                        performed_by=request.user,
                        reason=reason,
                    )
                except DenominationPurgeError as exc:
                    messages.error(request, str(exc))
                    return redirect("sitecontrol:denomination_detail", pk=pk)
                except Exception as exc:
                    from django.db.models.deletion import ProtectedError

                    if isinstance(exc, ProtectedError):
                        messages.error(
                            request,
                            "Deletion blocked by protected related records. "
                            "Contact engineering if this persists.",
                        )
                        return redirect("sitecontrol:denomination_detail", pk=pk)
                    raise

                log_platform_action(
                    request,
                    "DENOMINATION_PURGE",
                    f"Permanently deleted denomination {result['denomination_name']}",
                    target_model="Denomination",
                    target_id=result["denomination_id"],
                    details=result,
                )
                request.session.pop(session_reason_key, None)
                if request.session.get("active_denomination_id") == str(pk):
                    request.session.pop("active_denomination_id", None)
                flash_success(
                    request,
                    f"Denomination “{result['denomination_name']}” and all related data were permanently deleted.",
                )
                return redirect("sitecontrol:denomination_list")
    elif request.GET.get("step") == "2":
        step = 2

    if step == 3:
        reason = request.session.get(session_reason_key, "")

    return render(request, "sitecontrol/denomination_purge_confirm.html", {
        "denomination": denomination,
        "preview": preview,
        "step": step,
        "reason": reason,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Denominations", "/platform/denominations/"),
            (denomination.name, f"/platform/denominations/{denomination.pk}/"),
            ("Permanent deletion",),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_DENOMINATIONS)
def denomination_seed_builtins(request):
    if request.method != "POST":
        return redirect("sitecontrol:denomination_list")
    created = ensure_builtin_denominations()
    log_platform_action(
        request,
        "DENOMINATION_SEED",
        f"Seeded {len(created)} built-in denomination profile(s)",
        target_model="Denomination",
    )
    flash_success(request, "Built-in denomination profiles updated.")
    return redirect("sitecontrol:denomination_list")
