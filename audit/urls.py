from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.controls_home, name="controls_home"),
    path("events/", views.audit_event_list, name="event_list"),
    path("events/<uuid:pk>/", views.audit_event_detail, name="event_detail"),
]
