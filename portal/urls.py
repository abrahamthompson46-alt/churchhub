from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("login/", views.portal_login, name="login"),
    path("confirm-sent/", views.confirm_sent, name="confirm_sent"),
    path("confirm/<str:token>/", views.confirm_device, name="confirm_device"),
    path("password/change/", views.password_change, name="password_change"),
    path("password/reset/", views.PortalPasswordResetView.as_view(), name="password_reset"),
    path(
        "password/reset/done/",
        views.PortalPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        views.PortalPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        views.PortalPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("", views.home, name="home"),
    path("profile/", views.profile, name="profile"),
    path("announcements/<int:pk>/", views.announcement_detail, name="announcement_detail"),
    path("meetings/<uuid:pk>/", views.meeting_live, name="meeting_live"),
]
