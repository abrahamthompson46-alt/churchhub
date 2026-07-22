"""Public registration and platform application review views."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from church_system.flash import flash_error, flash_success
from sitecontrol.checks import platform_required, require_platform_capability
from sitecontrol.forms import ApplicationReviewForm, RegistrationSettingsForm, TenantApplicationForm
from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.models import TenantApplication
from sitecontrol.rbac import CAP_MANAGE_APPLICATIONS, CAP_MANAGE_REGISTRATION
from sitecontrol.registration_services import (
    approve_tenant_application,
    institution_invites_allowed,
    institution_onboarding_allowed,
    public_registration_allowed,
    reject_tenant_application,
    submit_tenant_application,
)
from sitecontrol.services import clear_settings_cache, get_site_settings, log_platform_action


def _breadcrumbs(*crumbs):
    return [{"label": c[0], **({"url": c[1]} if len(c) > 1 else {})} for c in crumbs]


def church_apply(request):
    """Public church registration application (gated by platform setting)."""
    if not public_registration_allowed():
        return HttpResponseForbidden(
            "Church registration is not open. Contact the platform administrator."
        )

    settings_obj = get_site_settings()

    denom_code = request.GET.get("denomination")
    initial_denom = (
        selectors.denomination_by_code(
            code=denom_code, active_only=True, allow_public_registration=True
        )
        if denom_code
        else None
    )
    form = TenantApplicationForm(request.POST or None, denomination=initial_denom)
    if request.method == "POST" and form.is_valid():
        try:
            application = submit_tenant_application(
                form.cleaned_data,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            if request.user.is_authenticated and getattr(request.user, "is_platform_user", False):
                log_platform_action(
                    request,
                    "APPLICATION_SUBMIT",
                    f"Application submitted for {application.church_name}",
                    target_model="TenantApplication",
                    target_id=application.pk,
                )
            return redirect("church_apply_success")
        except ValueError as exc:
            flash_error(request, str(exc), title="Application not submitted")

    intro = settings_obj.registration_intro
    if initial_denom and initial_denom.registration_intro:
        intro = initial_denom.registration_intro
    display_name = initial_denom.display_name if initial_denom else settings_obj.site_name

    return render(request, "registration/apply.html", {
        "form": form,
        "registration_intro": intro,
        "site_name": display_name,
        "active_denomination": initial_denom,
    })


def church_apply_success(request):
    if not public_registration_allowed():
        return redirect("login")
    return render(request, "registration/apply_success.html", {
        "site_name": get_site_settings().site_name,
    })


@platform_required
@require_platform_capability(CAP_MANAGE_REGISTRATION)
def registration_settings(request):
    settings_obj = get_site_settings()
    form = RegistrationSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        settings_obj = form.save(commit=False)
        repo.save_model(settings_obj)
        clear_settings_cache()
        log_platform_action(request, "REGISTRATION_UPDATE", "Registration access controls updated")
        flash_success(request, "Registration settings saved.")
        return redirect("sitecontrol:registration_settings")
    return render(request, "sitecontrol/registration_settings.html", {
        "form": form,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Registration Controls",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_APPLICATIONS)
def application_list(request):
    from sitecontrol.platform_access import filter_platform_denomination

    qs = selectors.applications_list_base()
    qs = filter_platform_denomination(qs, request.user)
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "sitecontrol/application_list.html", {
        "page_obj": page,
        "status_filter": status,
        "status_choices": TenantApplication.STATUS_CHOICES,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Applications",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_APPLICATIONS)
def application_detail(request, pk):
    from django.core.exceptions import PermissionDenied
    from sitecontrol.platform_access import operator_can_access_denomination

    application = selectors.get_application_or_404(pk)
    if application.denomination_id and not operator_can_access_denomination(request.user, application.denomination):
        raise PermissionDenied("You do not have access to this application.")
    form = ApplicationReviewForm()
    from sitecontrol.services import ensure_default_payment_methods

    ensure_default_payment_methods()
    return render(request, "sitecontrol/application_detail.html", {
        "application": application,
        "form": form,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Applications", "/platform/applications/"),
            (application.church_name,),
        ),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_APPLICATIONS)
def application_approve(request, pk):
    application = selectors.get_pending_application_or_404(pk)
    form = ApplicationReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            application, church, invitation = approve_tenant_application(
                application,
                reviewer=request.user,
                review_notes=form.cleaned_data.get("review_notes", ""),
                plan=form.cleaned_data.get("plan"),
                status=form.cleaned_data.get("status", "ACTIVE"),
                billing_interval=form.cleaned_data.get("billing_interval", "MONTHLY"),
                payment_method=form.cleaned_data.get("payment_method"),
                payment_reference=form.cleaned_data.get("payment_reference", ""),
                trial_days=form.cleaned_data.get("trial_days"),
                role=form.cleaned_data.get("admin_role"),
            )
            log_platform_action(
                request,
                "APPLICATION_APPROVE",
                f"Approved application for {church.name}",
                target_model="TenantApplication",
                target_id=application.pk,
                denomination=application.denomination,
                details={
                    "church_id": str(church.pk),
                    "invitation_id": str(invitation.pk),
                    "denomination_id": str(application.denomination_id) if application.denomination_id else "",
                },
            )
            flash_success(
                request,
                f"Church “{church.name}” created. Share the invite link with {application.contact_email}.",
                title="Application approved",
            )
            return redirect("sitecontrol:application_detail", pk=application.pk)
        except ValueError as exc:
            flash_error(request, str(exc), title="Approval failed")
    return redirect("sitecontrol:application_detail", pk=pk)


@platform_required
@require_platform_capability(CAP_MANAGE_APPLICATIONS)
def application_reject(request, pk):
    application = selectors.get_pending_application_or_404(pk)
    form = ApplicationReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reject_tenant_application(
            application,
            reviewer=request.user,
            review_notes=form.cleaned_data.get("review_notes", ""),
        )
        log_platform_action(
            request,
            "APPLICATION_REJECT",
            f"Rejected application for {application.church_name}",
            target_model="TenantApplication",
            target_id=application.pk,
            denomination=application.denomination,
            details={"denomination_id": str(application.denomination_id) if application.denomination_id else ""},
        )
        flash_success(request, "Application rejected.")
        return redirect("sitecontrol:application_list")
    return redirect("sitecontrol:application_detail", pk=pk)
