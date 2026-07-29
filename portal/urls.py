from django.urls import path, re_path

from . import views

app_name = "portal"

urlpatterns = [
    path("login/", views.portal_login, name="login"),
    path("confirm-sent/", views.confirm_sent, name="confirm_sent"),
    path("confirm/", views.confirm_device, name="confirm_device"),
    re_path(
        r"^confirm/(?P<path_token>.+)/$",
        views.confirm_device,
        name="confirm_device_legacy",
    ),
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
    path("welfare/", views.my_welfare, name="welfare"),
    path("welfare/request/", views.welfare_request, name="welfare_request"),
    path("welfare/cases/<uuid:pk>/", views.welfare_case_detail, name="welfare_case"),
    path("prayer/", views.prayer_request, name="prayer_request"),
    path("thanksgiving/", views.thanksgiving_testimony, name="thanksgiving_testimony"),
    path("praise/", views.praise_wall, name="praise_wall"),
    path("staff/submissions/", views.staff_submission_list, name="staff_submissions"),
    path("", views.home, name="home"),
    path("profile/", views.profile, name="profile"),
    path("announcements/<int:pk>/", views.announcement_detail, name="announcement_detail"),
    path("meetings/<uuid:pk>/", views.meeting_live, name="meeting_live"),
]
