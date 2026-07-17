"""Account views — profile, user management, invitations."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from church_system.flash import (
    flash_error,
    flash_exception,
    flash_success,
    flash_validation_errors,
    flash_warning,
)

from accounts.forms import (
    AcceptInvitationForm,
    ProfileForm,
    UserInviteForm,
    UserManageForm,
)
from accounts.models import UserActivityLog, UserInvitation
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
    assign_user_to_church,
    create_invitation,
    deactivate_user,
    get_client_ip,
    log_activity,
    resend_invitation,
    revoke_invitation,
    send_invitation_email,
    update_user_profile,
    update_user_role,
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
                user = password_form.save()
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

    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    if role:
        users = users.filter(role=role)
    if status == "1":
        users = users.filter(is_active=True)
    elif status == "0":
        users = users.filter(is_active=False)

    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    church_ids = get_manageable_churches(request.user).values_list("pk", flat=True)
    pending_invites = UserInvitation.objects.filter(
        is_accepted=False,
        revoked_at__isnull=True,
        church_id__in=church_ids,
    ).select_related("church", "invited_by").order_by("-created_at")[:50]

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
    })


@login_required
def user_detail(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    user_obj = get_object_or_404(get_manageable_users(request.user), pk=pk)
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

        # Capture before is_valid() — ModelForm._post_clean mutates instance via construct_instance.
        old_role = user_obj.role
        old_church_id = user_obj.church_id

        form = UserManageForm(request.POST, instance=user_obj, manager=request.user)
        if form.is_valid():
            new_role = form.cleaned_data["role"]
            new_church = form.cleaned_data.get("church")

            # Persist non-role / non-church fields only; role & church go through services.
            user_obj.first_name = form.cleaned_data["first_name"]
            user_obj.last_name = form.cleaned_data["last_name"]
            user_obj.email = form.cleaned_data["email"]
            user_obj.phone = form.cleaned_data.get("phone") or ""
            user_obj.member = form.cleaned_data.get("member")
            # Keep DB role/church stable until services apply changes.
            user_obj.role = old_role
            user_obj.church_id = old_church_id
            user_obj.save(
                update_fields=["first_name", "last_name", "email", "phone", "member", "role", "church"]
            )

            if new_church and new_church.pk != old_church_id:
                assign_user_to_church(
                    user_obj, new_church,
                    performed_by=request.user, ip_address=ip,
                )
            elif new_church is None and old_church_id is not None:
                user_obj.church = None
                user_obj.save(update_fields=["church"])

            if new_role != old_role:
                try:
                    update_user_role(
                        user_obj, new_role,
                        performed_by=request.user, ip_address=ip,
                    )
                except ValueError as exc:
                    flash_exception(request, exc, title="Role could not be updated")
                    return redirect("accounts:user_detail", pk=pk)

            flash_success(request, "Role and church assignment saved.", title="User updated")
            return redirect("accounts:user_detail", pk=pk)
        flash_validation_errors(request, form, title="User could not be updated")

    activity = user_obj.activity_logs.order_by("-created_at")[:20]
    return render(request, "accounts/user_detail.html", {
        "user_obj": user_obj,
        "form": form,
        "activity": activity,
        "is_self": user_obj.pk == request.user.pk,
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
    form = UserInviteForm(request.POST or None, manager=request.user)

    if request.method == "POST" and form.is_valid():
        existing = UserInvitation.objects.filter(
            email=form.cleaned_data["email"],
            church=form.cleaned_data["church"],
            is_accepted=False,
            revoked_at__isnull=True,
        ).first()
        if existing and existing.is_valid:
            flash_warning(request, "Use the existing invite link or wait for it to expire.", title="Invitation pending")
        else:
            church = form.cleaned_data["church"]
            allowed, message = can_add_user_to_church(church)
            if not allowed:
                flash_error(request, message, title="User limit reached")
            else:
                try:
                    inv = create_invitation(
                        email=form.cleaned_data["email"],
                        username=form.cleaned_data["username"],
                        role=form.cleaned_data["role"],
                        church=church,
                        invited_by=request.user,
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

    return render(request, "accounts/invite.html", {"form": form})


@login_required
def invite_detail(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    church_ids = get_manageable_churches(request.user).values_list("pk", flat=True)
    invitation = get_object_or_404(UserInvitation, pk=pk, church_id__in=church_ids)
    return render(request, "accounts/invite_detail.html", {"invitation": invitation})


@login_required
@require_POST
def invite_revoke(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    church_ids = get_manageable_churches(request.user).values_list("pk", flat=True)
    invitation = get_object_or_404(UserInvitation, pk=pk, church_id__in=church_ids)
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
    church_ids = get_manageable_churches(request.user).values_list("pk", flat=True)
    invitation = get_object_or_404(UserInvitation, pk=pk, church_id__in=church_ids)
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
    invitation = get_object_or_404(UserInvitation, token=token)
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
    logs = UserActivityLog.objects.filter(
        user__in=manageable,
    ).select_related("user", "performed_by").order_by("-created_at")

    action = request.GET.get("action", "").strip()
    if action:
        logs = logs.filter(action=action)

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "accounts/activity_log.html", {
        "logs": page_obj,
        "page_obj": page_obj,
        "action_filter": action,
        "action_choices": UserActivityLog.ACTION_CHOICES,
    })
