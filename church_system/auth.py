"""Custom authentication views."""

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy


class ChurchHubLoginView(LoginView):
    template_name = "login.html"

    def get_success_url(self):
        user = self.request.user
        if getattr(user, "is_platform_user", False):
            return reverse_lazy("sitecontrol:dashboard")
        return reverse_lazy("dashboard:home")
