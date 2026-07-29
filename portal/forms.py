"""Member portal forms."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from decimal import Decimal

from remittance.models import WelfareAssistanceCase
from permissions.roles import UserRole

from .services import (
    PortalAuthError,
    authenticate_portal_credentials,
    normalize_email,
)

User = get_user_model()


class MemberPortalLoginForm(AuthenticationForm):
    """Email as username; password is DOB (first login) or a chosen password."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control ps-5",
                "autocomplete": "username email",
                "placeholder": "you@example.com",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control ps-5",
                "autocomplete": "current-password",
                "placeholder": "Date of birth or your password",
            }
        ),
        help_text="First sign-in: use your date of birth as YYYY-MM-DD (example: 1990-05-21).",
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Email and password do not match our member records.",
    }

    def clean(self):
        email = normalize_email(self.cleaned_data.get("username", ""))
        password = self.cleaned_data.get("password")
        if email and password:
            try:
                user = authenticate_portal_credentials(email, password)
            except PortalAuthError as exc:
                raise forms.ValidationError(str(exc)) from exc
            self.user_cache = user
            self.confirm_login_allowed(user)
        return self.cleaned_data


class PortalPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("old_password", "new_password1", "new_password2"):
            self.fields[name].widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.must_change_password = False
        if commit:
            user.save()
        return user


class PortalPasswordResetForm(PasswordResetForm):
    """Only MEMBER accounts with a linked member email may reset via the portal."""

    def get_users(self, email):
        email = normalize_email(email)
        active_users = User.objects.filter(
            is_active=True,
            is_platform_user=False,
            role=UserRole.MEMBER,
        ).filter(email__iexact=email)
        return (u for u in active_users if u.has_usable_password())

    def save(
        self,
        domain_override=None,
        subject_template_name=None,
        email_template_name=None,
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        """Send via platform SMTP when possible; fall back to Django mailer."""
        from django.contrib.sites.shortcuts import get_current_site
        from church_system.email_service import (
            build_absolute_uri,
            get_email_branding_context,
            send_platform_email,
        )
        from django.template.loader import render_to_string
        from django.urls import reverse

        email = self.cleaned_data["email"]
        if not domain_override:
            current_site = get_current_site(request)
            domain = current_site.domain
        else:
            domain = domain_override

        for user in self.get_users(email):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            context = {
                "email": email,
                "domain": domain,
                "uid": uid,
                "user": user,
                "token": token,
                "protocol": "https" if use_https else "http",
                **(extra_email_context or {}),
            }
            reset_path = reverse(
                "portal:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
            context["reset_url"] = build_absolute_uri(request, reset_path)
            context.update(
                get_email_branding_context(
                    request,
                    preheader="Reset your member portal password",
                )
            )
            subject = render_to_string(
                subject_template_name or "emails/portal_password_reset_subject.txt",
                context,
            )
            subject = "".join(subject.splitlines())
            text_body = render_to_string(
                email_template_name or "emails/portal_password_reset.txt",
                context,
            )
            html_body = None
            if html_email_template_name:
                html_body = render_to_string(html_email_template_name, context)
            sent = send_platform_email(
                subject=subject,
                to=email,
                text_body=text_body,
                html_body=html_body,
                fail_silently=True,
            )
            if not sent:
                super().save(
                    domain_override=domain_override,
                    subject_template_name=subject_template_name,
                    email_template_name=email_template_name,
                    use_https=use_https,
                    token_generator=token_generator,
                    from_email=from_email,
                    request=request,
                    html_email_template_name=html_email_template_name,
                    extra_email_context=extra_email_context,
                )
                return


class PortalSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.must_change_password = False
        if commit:
            user.save()
        return user


class PortalWelfareRequestForm(forms.Form):
    assistance_type = forms.ChoiceField(
        label="Type of assistance",
        choices=WelfareAssistanceCase.ASSISTANCE_TYPES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount_requested = forms.DecimalField(
        label="Amount requested (₵)",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    priority = forms.ChoiceField(
        label="Urgency",
        choices=WelfareAssistanceCase.PRIORITY_CHOICES,
        initial="NORMAL",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        label="Describe your need",
        min_length=20,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Share enough detail for the welfare team to understand your situation.",
            }
        ),
    )
