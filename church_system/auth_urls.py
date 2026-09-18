"""Django auth URLs with ChurchHub-branded password reset email."""

from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.password_reset import StaffPasswordResetView, StaffPasswordChangeForm, StaffSetPasswordForm
from accounts.session_security import stamp_session


class ChurchHubPasswordChangeView(auth_views.PasswordChangeView):
    form_class = StaffPasswordChangeForm

    def form_valid(self, form):
        response = super().form_valid(form)
        stamp_session(self.request, form.user)
        return response


urlpatterns = [
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password_change/",
        ChurchHubPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "password_reset/",
        StaffPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password_reset/confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(form_class=StaffSetPasswordForm),
        name="password_reset_confirm",
    ),
    path(
        "password_reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
