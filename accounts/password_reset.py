"""Staff password reset with branded HTML and platform SMTP."""

from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetView
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from church_system.email_service import (
    build_absolute_uri,
    get_email_branding_context,
    send_platform_email,
)


class StaffPasswordResetForm(PasswordResetForm):
    def save(
        self,
        domain_override=None,
        subject_template_name=None,
        email_template_name=None,
        use_https=False,
        token_generator=None,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        from django.contrib.auth.tokens import default_token_generator

        if token_generator is None:
            token_generator = default_token_generator

        email = self.cleaned_data["email"]
        if not domain_override:
            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
        else:
            site_name = domain = domain_override

        for user in self.get_users(email):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            context = {
                "email": email,
                "domain": domain,
                "site_name": site_name,
                "uid": uid,
                "user": user,
                "token": token,
                "protocol": "https" if use_https else "http",
                **(extra_email_context or {}),
            }
            reset_path = reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
            context["reset_url"] = build_absolute_uri(request, reset_path)
            context.update(
                get_email_branding_context(
                    request,
                    preheader="Reset your ChurchHub password",
                )
            )
            subject = render_to_string(
                subject_template_name or "registration/password_reset_subject.txt",
                context,
            )
            subject = "".join(subject.splitlines())
            text_body = render_to_string(
                email_template_name or "registration/password_reset_email.html",
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


class StaffPasswordResetView(PasswordResetView):
    form_class = StaffPasswordResetForm
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "emails/staff_password_reset.html"
    subject_template_name = "registration/password_reset_subject.txt"
