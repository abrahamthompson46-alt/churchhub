from django.urls import path

from church_system.auth import MemberPortalLoginView

from . import views

app_name = "portal"

urlpatterns = [
    path("login/", MemberPortalLoginView.as_view(), name="login"),
    path("", views.home, name="home"),
    path("profile/", views.profile, name="profile"),
]
