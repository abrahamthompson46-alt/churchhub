from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("users/", views.user_list, name="user_list"),
    path("users/<uuid:pk>/", views.user_detail, name="user_detail"),
    path("users/invite/", views.invite_user, name="invite_user"),
    path("users/invite/<uuid:pk>/", views.invite_detail, name="invite_detail"),
    path("users/invite/<uuid:pk>/revoke/", views.invite_revoke, name="invite_revoke"),
    path("users/invite/<uuid:pk>/resend/", views.invite_resend, name="invite_resend"),
    path("users/activity/", views.activity_log, name="activity_log"),
    path("invite/accept/<uuid:token>/", views.accept_invite, name="accept_invite"),
]
