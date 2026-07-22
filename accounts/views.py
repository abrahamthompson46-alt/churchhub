"""Account views — profile, user management, invitations."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from church_system.flash import (
    flash_error,
    flash_exception,
    flash_success,
    flash_validation_errors,
    flash_warning,
)

from accounts import repositories as repo
from accounts import selectors
from accounts.forms import (
    AcceptInvitationForm,
    ProfileForm,
    UserInviteForm,
    UserManageForm,
)
from accounts.models import UserActivityLog
from accounts.permissions import (
    can_manage_permissions,
    can_manage_users,
    can_view_activity_logs,
    get_manageable_churches,
    get_manageable_users,
)
from accounts.services import (
    accept_invitation,
    activate_user,
    assert_can_assign_role,
    create_invitation,
    deactivate_user,
    get_client_ip,
    log_activity,
    resend_invitation,
    revoke_invitation,
    send_invitation_email,
    update_user_profile,
)
from sitecontrol.services import can_add_user_to_church


@login_required
def profile(request):
    profile_form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                update_user_profile(
                    request.user,
                    profile_form.changed_profile_data(),
                    performed_by=request.user,
                    ip_address=get_client_ip(request),
                )
                flash_success(request, "Your profile has been saved.", title="Profile updated")
                return redirect("accounts:profile")
            flash_validation_errors(request, profile_form, title="Profile could not be saved")
        elif action == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save(commit=False)
                repo.save_user(user)
                update_session_auth_hash(request, user)
                log_activity(user, "PASSWORD_CHANGE", ip_address=get_client_ip(request))
                flash_success(request, "Sign in again on other devices if needed.", title="Password changed")
                return redirect("accounts:profile")
            flash_validation_errors(request, password_form, title="Password could not be changed")

    return render(request, "accounts/profile.html", {
        "user_obj": request.user,
        "profile_form": profile_form,
        "password_form": password_form,
        "is_platform_user": getattr(request.user, "is_platform_user", False),
    })


@login_required
def user_list(request):
    if not can_manage_users(request.user):
        raise PermissionDenied
    users = get_manageable_users(request.user)
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    status = request.GET.get("is_active", "").strip()

    users = selectors.filter_manageable_users(users, q=q, role=role, status=status)

    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    church_ids = list(get_manageable_churches(request.user).values_list("pk", flat=True))
    pending_invites = selectors.pending_invitations_for_manager(
        request.user, church_ids
    )

    from accounts.control_center import ucc_context
    from permissions.roles import UserRole

    return render(request, "accounts/user_list.html", {
        "users": page_obj,
        "page_obj": page_obj,
        "pending_invites": pending_invites,
        "q": q,
        "role_filter": role,
        "status_filter": status,
        "role_choices": UserRole.CHOICES,
        "can_manage_permissions": can_manage_permissions(request.user),
        **ucc_context(request.user, active="directory"),
    })


@login_required
def user_detail(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    user_obj = selectors.get_manageable_user_or_404(request.user, pk)
    form = UserManageForm(instance=user_obj, manager=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        ip = get_client_ip(request)

        if action == "deactivate" and user_obj.is_active:
            if user_obj.pk == request.user.pk:
                flash_error(request, "You cannot deactivate your own account.", title="Not allowed")
                return redirect("accounts:user_detail", pk=pk)
            try:
                deactivate_user(user_obj, performed_by=request.user, ip_address=ip)
            except ValueError as exc:
                flash_exception(request, exc, title="Could not deactivate")
                return redirect("accounts:user_detail", pk=pk)
            flash_success(request, f"{user_obj.username} can no longer sign in.", title="User deactivated")
            return redirect("accounts:user_list")
        if action == "activate" and not user_obj.is_active:
            activate_user(user_obj, performed_by=request.user, ip_address=ip)
            flash_success(request, f"{user_obj.username} can sign in again.", title="User activated")
            return redirect("accounts:user_detail", pk=pk)

        old_role = user_obj.role
        old_scope = (
            user_obj.scope_level,
            user_obj.church_id,
            user_obj.scope_district_id,
            user_obj.scope_zone_id,
            user_obj.scope_conference_id,
            user_obj.scope_union_id,
        )

        form = UserManageForm(request.POST, instance=user_obj, manager=request.user)
        if form.is_valid():
            try:
                if form.cleaned_data["role"] != old_role:
                    assert_can_assign_role(request.user, form.cleaned_data["role"])
                saved = form.save(commit=False)
                repo.save_user(saved)
                form.save_m2m()
            except ValueError as exc:
                flash_exception(request, exc, title="User could not be updated")
                return redirect("accounts:user_detail", pk=pk)

            new_scope = (
                saved.scope_level,
                saved.church_id,
                saved.scope_district_id,
                saved.scope_zone_id,
                saved.scope_conference_id,
                saved.scope_union_id,
            )
            if saved.role != old_role:
                log_activity(
                    saved,
                    "ROLE_CHANGE",
                    performed_by=request.user,
                    ip_address=ip,
                    details={"old_role": old_role, "new_role": saved.role},
                )
            if new_scope != old_scope:
                log_activity(
                    saved,
                    "SCOPE_CHANGE",
                    performed_by=request.user,
                    ip_address=ip,
                    details={
                        "scope_level": saved.scope_level,
                        "church_id": str(saved.church_id) if saved.church_id else None,
                        "scope_district_id": str(saved.scope_district_id) if saved.scope_district_id else None,
                        "scope_conference_id": str(saved.scope_conference_id) if saved.scope_conference_id else None,
                    },
                )
            flash_success(request, "Profile, role, and organization scope saved.", title="User updated")
            return redirect("accounts:user_detail", pk=pk)
        flash_validation_errors(request, form, title="User could not be updated")

    activity = selectors.recent_activity_for_user(user_obj)
    from accounts.control_center import ucc_context
    from permissions.checks import can_manage_permissions as _can_manage_permissions

    return render(request, "accounts/user_detail.html", {
        "user_obj": user_obj,
        "form": form,
        "activity": activity,
        "is_self": user_obj.pk == request.user.pk,
        "can_view_effective": _can_manage_permissions(request.user),
        **ucc_context(request.user, active="directory"),
    })


@login_required
def invite_user(request):
    if not can_manage_users(request.user):
        raise PermissionDenied
    from sitecontrol.registration_services import institution_invites_allowed

    if not institution_invites_allowed():
        flash_error(
            request,
            "User invitations are disabled by the platform administrator.",
            title="Invitations disabled",
        )
        return redirect("accounts:user_list")
    initial = {}
    if request.method == "GET":
        if request.GET.get("role"):
            initial["role"] = request.GET.get("role")
        if request.GET.get("scope_level"):
            initial["scope_level"] = request.GET.get("scope_level")
    form = UserInviteForm(request.POST or None, manager=request.user, initial=initial)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        existing = selectors.pending_invitation_for_email(
            email=data["email"],
            church=data.get("church"),
        )
        if existing and existing.is_valid:
            flash_warning(request, "Use the existing invite link or wait for it to expire.", title="Invitation pending")
        else:
            church = data.get("church")
            allowed, message = (True, "")
            if church:
                allowed, message = can_add_user_to_church(church)
            if not allowed:
                flash_error(request, message, title="User limit reached")
            else:
                try:
                    inv = create_invitation(
                        email=data["email"],
                        username=data["username"],
                        role=data["role"],
                        church=church,
                        invited_by=request.user,
                        scope_level=data.get("scope_level"),
                        scope_district=data.get("scope_district"),
                        scope_zone=data.get("scope_zone"),
                        scope_conference=data.get("scope_conference"),
                        scope_union=data.get("scope_union"),
                        scope_general_conference=data.get("scope_general_conference"),
                        denomination=data.get("denomination"),
                    )
                except ValueError as exc:
                    flash_exception(request, exc, title="Invitation could not be created")
                else:
                    try:
                        emailed = send_invitation_email(
                            inv,
                            request=request,
                            fail_silently=False,
                        )
                    except Exception as exc:
                        flash_warning(
                            request,
                            (
                                f"Invitation was created for {inv.email}, but the email could not be sent "
                                f"({exc}). Share the invite link from the next screen, then fix SMTP under "
                                "Platform → Email."
                            ),
                            title="Invitation created — email failed",
                        )
                    else:
                        if emailed:
                            flash_success(
                                request,
                                f"Invitation emailed to {inv.email}.",
                                title="Invitation sent",
                            )
                        else:
                            flash_warning(
                                request,
                                (
                                    f"Invitation created for {inv.email}, but SMTP is not configured. "
                                    "Share the invite link from the next screen. Configure SMTP under "
                                    "Platform → Email (or EMAIL_HOST / DEFAULT_FROM_EMAIL)."
                                ),
                                title="Invitation created — email not sent",
                            )
                    return redirect("accounts:invite_detail", pk=inv.pk)

    from accounts.control_center import ucc_context

    return render(request, "accounts/invite.html", {
        "form": form,
        **ucc_context(request.user, active="invite"),
    })


def _get_manageable_invitation(request, pk):
    """Invitation visible if its home church is in the manager subtree (or denomination invite)."""
    invitation = selectors.invitation_with_scope_or_404(pk)
    church_ids = set(get_manageable_churches(request.user).values_list("pk", flat=True))
    if invitation.church_id and invitation.church_id in church_ids:
        return invitation
    if not invitation.church_id and invitation.invited_by_id == request.user.id:
        return invitation
    if not invitation.church_id and can_manage_users(request.user):
        # Denomination-level invite: allow tree admins in same denomination
        from church_system.denomination_scope import get_user_denomination

        denom = get_user_denomination(request.user)
        if denom and invitation.denomination_id == denom.pk:
            return invitation
    raise PermissionDenied


@login_required
def invite_detail(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    invitation = _get_manageable_invitation(request, pk)
    from accounts.control_center import ucc_context

    return render(request, "accounts/invite_detail.html", {
        "invitation": invitation,
        **ucc_context(request.user, active="invite"),
    })


@login_required
@require_POST
def invite_revoke(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    invitation = _get_manageable_invitation(request, pk)
    try:
        revoke_invitation(invitation, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "Invitation revoked.", title="Invitation revoked")
    except ValueError as exc:
        flash_exception(request, exc, title="Could not revoke invitation")
    return redirect("accounts:invite_detail", pk=pk)


@login_required
@require_POST
def invite_resend(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    invitation = _get_manageable_invitation(request, pk)
    try:
        _invitation, emailed = resend_invitation(
            invitation,
            performed_by=request.user,
            ip_address=get_client_ip(request),
            request=request,
        )
        if emailed:
            flash_success(
                request,
                f"Invitation resent to {invitation.email}.",
                title="Invitation resent",
            )
        else:
            flash_warning(
                request,
                (
                    f"Invitation updated for {invitation.email}, but the email was not delivered. "
                    "Share the invite link below, and configure SMTP under Platform → Email."
                ),
                title="Invitation updated — email not sent",
            )
    except ValueError as exc:
        flash_exception(request, exc, title="Could not resend invitation")
    return redirect("accounts:invite_detail", pk=pk)


def accept_invite(request, token):
    invitation = selectors.get_invitation_by_token_or_404(token)
    if not invitation.is_valid:
        return render(request, "accounts/invite_invalid.html", {"invitation": invitation})

    form = AcceptInvitationForm(request.POST or None, invitation=invitation)
    if request.method == "POST" and form.is_valid():
        try:
            accept_invitation(
                invitation,
                password=form.cleaned_data["password1"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
            flash_success(request, "You can now sign in with your new account.", title="Welcome to ChurchHub")
            return redirect("login")
        except ValueError as exc:
            flash_exception(request, exc, title="Account could not be created")

    return render(request, "accounts/accept_invite.html", {
        "invitation": invitation,
        "form": form,
    })


@login_required
def activity_log(request):
    if not can_view_activity_logs(request.user):
        raise PermissionDenied
    manageable = get_manageable_users(request.user)
    action = request.GET.get("action", "").strip()
    logs = selectors.activity_logs_for_users(manageable, action=action)

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    from accounts.control_center import ucc_context

    return render(request, "accounts/activity_log.html", {
        "logs": page_obj,
        "page_obj": page_obj,
        "action_filter": action,
        "action_choices": UserActivityLog.ACTION_CHOICES,
        **ucc_context(request.user, active="activity"),
    })
