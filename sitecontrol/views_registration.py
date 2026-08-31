"""Public registration and platform application review views."""

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from church_system.flash import flash_error, flash_success, flash_warning
from accounts.services import send_invitation_email
from sitecontrol.checks import platform_required, require_platform_capability
from sitecontrol.forms import (
    ApplicationReviewForm,
    RegistrationSettingsForm,
    SubscriptionActivationRequestForm,
    TenantApplicationForm,
)
from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.models import SubscriptionActivationRequest, TenantApplication
from sitecontrol.rbac import CAP_MANAGE_APPLICATIONS, CAP_MANAGE_REGISTRATION, CAP_VIEW
from sitecontrol.activation_services import (
    pending_request_for_church,
    submit_activation_request,
)
from sitecontrol.registration_services import (
    approve_tenant_application,
    institution_invites_allowed,
    institution_onboarding_allowed,
    public_demo_auto_provision_enabled,
    public_demo_trial_days,
    public_registration_allowed,
    reject_tenant_application,
    submit_tenant_application,
)
from sitecontrol.services import (
    clear_settings_cache,
    get_church_subscription,
    get_site_settings,
    log_platform_action,
)

User = get_user_model()


def _breadcrumbs(*crumbs):
    return [{"label": c[0], **({"url": c[1]} if len(c) > 1 else {})} for c in crumbs]


def church_apply(request):
    """Public church registration application (gated by platform setting)."""
    if not public_registration_allowed():
        return HttpResponseForbidden(
            "Church registration is not open. Contact the platform administrator."
        )

    settings_obj = get_site_settings()
    auto_demo = public_demo_auto_provision_enabled()
    form = TenantApplicationForm(
        request.POST or None,
        require_password=auto_demo,
    )
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
            if auto_demo and application.status == "APPROVED":
                user = User.objects.get(username__iexact=application.applicant_username)
                login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                church = application.created_church
                sub = get_church_subscription(church) if church else None
                days = public_demo_trial_days()
                expiry = sub.expires_at.isoformat() if sub and sub.expires_at else ""
                flash_success(
                    request,
                    f"Your {days}-day demo is active"
                    + (f" until {expiry}." if expiry else "."),
                    title="Demo workspace ready",
                )
                return redirect("dashboard:home")
            return redirect("church_apply_success")
        except ValueError as exc:
            flash_error(request, str(exc), title="Application not submitted")

    intro = settings_obj.registration_intro
    demo = getattr(form, "demo_denomination", None)
    if demo and demo.registration_intro:
        intro = demo.registration_intro
    display_name = settings_obj.site_name

    return render(request, "registration/apply.html", {
        "form": form,
        "registration_intro": intro,
        "site_name": display_name,
        "active_denomination": demo,
        "auto_demo": auto_demo,
        "demo_trial_days": public_demo_trial_days() if auto_demo else None,
        "demo_denomination_label": "DEMO",
    })


def church_apply_success(request):
    if not public_registration_allowed():
        return redirect("login")
    return render(request, "registration/apply_success.html", {
        "site_name": get_site_settings().site_name,
        "auto_demo": public_demo_auto_provision_enabled(),
    })


@login_required
def subscription_expired(request):
    """Hard stop for non-operational church subscriptions (including ended demos)."""
    user = request.user
    if getattr(user, "is_platform_user", False):
        return redirect("sitecontrol:dashboard")
    church = getattr(user, "church", None)
    sub = get_church_subscription(church) if church else None
    if sub and sub.is_operational:
        return redirect("dashboard:home")
    settings_obj = get_site_settings()
    plan = sub.plan if sub else None
    pending = pending_request_for_church(church)
    return render(
        request,
        "registration/subscription_expired.html",
        {
            "site_name": settings_obj.site_name,
            "subscription": sub,
            "church": church,
            "plan": plan,
            "pending_request": pending,
            "billing_currency": settings_obj.default_billing_currency,
            "billing_payment_instructions": (
                settings_obj.billing_payment_instructions or ""
            ).strip(),
        },
    )


@login_required
def subscription_subscribe(request):
    """Church user submits payment reference and church details (no email)."""
    user = request.user
    if getattr(user, "is_platform_user", False):
        return redirect("sitecontrol:dashboard")
    church = getattr(user, "church", None)
    if church is None:
        flash_error(request, "Your account is not linked to a church.", title="Cannot subscribe")
        return redirect("subscription_expired")
    sub = get_church_subscription(church)
    if sub and sub.is_operational:
        return redirect("dashboard:home")

    settings_obj = get_site_settings()
    pending = pending_request_for_church(church)
    initial = {
        "church_name": church.name,
        "church_code": church.code,
        "church_address": church.address,
        "contact_name": user.get_full_name() or user.username,
        "contact_email": user.email or "",
        "contact_phone": getattr(user, "phone", "") or "",
    }
    application = (
        TenantApplication.objects.filter(created_church=church)
        .order_by("-created_at")
        .first()
    )
    if application:
        if not initial["contact_email"]:
            initial["contact_email"] = application.contact_email
        if not initial["contact_phone"]:
            initial["contact_phone"] = application.contact_phone
        if not user.get_full_name():
            initial["contact_name"] = application.contact_name
    if pending:
        initial.update(
            {
                "church_name": pending.church_name,
                "church_code": pending.church_code,
                "church_address": pending.church_address,
                "contact_name": pending.contact_name,
                "contact_email": pending.contact_email,
                "contact_phone": pending.contact_phone,
                "payment_reference": pending.payment_reference,
                "notes": pending.notes,
            }
        )

    form = SubscriptionActivationRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        submit_activation_request(
            church=church,
            subscription=sub,
            user=user,
            cleaned_data=form.cleaned_data,
            request=request,
        )
        flash_success(
            request,
            "Platform administrators have been notified. We will activate this same church after we confirm payment.",
            title="Request received",
        )
        return redirect("subscription_subscribe")

    plan = sub.plan if sub else None
    return render(
        request,
        "registration/subscription_subscribe.html",
        {
            "form": form,
            "site_name": settings_obj.site_name,
            "church": church,
            "subscription": sub,
            "plan": plan,
            "pending_request": pending,
            "billing_currency": settings_obj.default_billing_currency,
            "billing_payment_instructions": (
                settings_obj.billing_payment_instructions or ""
            ).strip(),
        },
    )


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
            invite_note = ""
            if invitation:
                try:
                    emailed = send_invitation_email(
                        invitation,
                        request=request,
                        fail_silently=False,
                    )
                    if emailed:
                        invite_note = f" Invitation email sent to {application.contact_email}."
                    else:
                        flash_warning(
                            request,
                            f"Invitation created for {application.contact_email}, but SMTP is not configured.",
                            title="Invite not emailed",
                        )
                except Exception as exc:
                    flash_warning(
                        request,
                        f"Invitation created, but email failed: {exc}. Resend from the tenant page.",
                        title="Invite email failed",
                    )
            flash_success(
                request,
                f"Church “{church.name}” created.{invite_note}",
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


@platform_required
@require_platform_capability(CAP_VIEW)
def activation_request_list(request):
    from sitecontrol.platform_access import filter_platform_denomination

    qs = filter_platform_denomination(selectors.activation_requests_list_base(), request.user)
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "sitecontrol/activation_request_list.html", {
        "page_obj": page,
        "status_filter": status,
        "status_choices": SubscriptionActivationRequest.STATUS_CHOICES,
        "breadcrumbs": _breadcrumbs(("Platform", "/platform/"), ("Activation requests",)),
    })


@platform_required
@require_platform_capability(CAP_VIEW)
def activation_request_detail(request, pk):
    from django.core.exceptions import PermissionDenied
    from dashboard.models import Notification
    from sitecontrol.platform_access import operator_can_access_denomination

    activation_request = selectors.get_activation_request_or_404(pk)
    if activation_request.denomination_id and not operator_can_access_denomination(
        request.user, activation_request.denomination
    ):
        raise PermissionDenied("You do not have access to this request.")
    Notification.objects.filter(
        user=request.user,
        action_url__contains=str(activation_request.pk),
        read=False,
    ).update(read=True)
    return render(request, "sitecontrol/activation_request_detail.html", {
        "activation_request": activation_request,
        "breadcrumbs": _breadcrumbs(
            ("Platform", "/platform/"),
            ("Activation requests", "/platform/activation-requests/"),
            (activation_request.church_name,),
        ),
    })
