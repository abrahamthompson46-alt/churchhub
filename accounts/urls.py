from django.urls import path

from . import mfa_views, views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("settings/branding/", views.institution_branding, name="institution_branding"),
    path("mfa/enroll/", mfa_views.mfa_enroll, name="mfa_enroll"),
    path("mfa/verify/", mfa_views.mfa_verify, name="mfa_verify"),
    path("mfa/send-email/", mfa_views.mfa_send_email, name="mfa_send_email"),
    path("users/", views.user_list, name="user_list"),
    path("users/<uuid:pk>/", views.user_detail, name="user_detail"),
    path("users/invite/", views.invite_user, name="invite_user"),
    path("users/invite/<uuid:pk>/", views.invite_detail, name="invite_detail"),
    path("users/invite/<uuid:pk>/revoke/", views.invite_revoke, name="invite_revoke"),
    path("users/invite/<uuid:pk>/resend/", views.invite_resend, name="invite_resend"),
    path("users/activity/", views.activity_log, name="activity_log"),
    path("invite/accept/<uuid:token>/", views.accept_invite, name="accept_invite"),
]
