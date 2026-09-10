from django.urls import path

from . import views

app_name = "intelligence"

urlpatterns = [
    path("", views.alert_list, name="alert_list"),
    path("policy/", views.policy_edit, name="policy"),
    path("<uuid:pk>/", views.alert_detail, name="alert_detail"),
    path("<uuid:pk>/dismiss/", views.alert_dismiss, name="alert_dismiss"),
    path("<uuid:pk>/confirm/", views.alert_confirm, name="alert_confirm"),
]
