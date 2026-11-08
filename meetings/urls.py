from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.meeting_list, name="list"),
    path("pending/", views.pending_minutes, name="pending_minutes"),
    path("add/", views.meeting_create, name="create"),
    path(
        "create/",
        RedirectView.as_view(pattern_name="meetings:create", query_string=True),
        name="create_alias",
    ),
    path("<uuid:pk>/", views.meeting_detail, name="detail"),
    path("<uuid:pk>/edit/", views.meeting_edit, name="edit"),
    path("<uuid:pk>/action/", views.meeting_action, name="action"),
    path("<uuid:pk>/attendance/", views.meeting_attendance, name="attendance"),
    path("<uuid:pk>/actions/", views.action_item_add, name="action_add"),
    path("<uuid:pk>/decisions/", views.decision_add, name="decision_add"),
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/add/", views.attendance_create, name="attendance_create"),
    path(
        "attendance/create/",
        RedirectView.as_view(pattern_name="meetings:attendance_create", query_string=True),
        name="attendance_create_alias",
    ),
    path("attendance/<uuid:pk>/", views.attendance_detail, name="attendance_detail"),
    path("attendance/<uuid:pk>/record/", views.attendance_record, name="attendance_record"),
]
