from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.announcement_list, name="announcement_list"),
    path("upcoming/", views.upcoming_calendar, name="upcoming_calendar"),
    path("create/", views.create_announcement_view, name="create_announcement"),
    path("mine/", views.my_announcements, name="my_announcements"),
    path("pending/", views.pending_approvals, name="pending_approvals"),
    path("<int:pk>/", views.announcement_detail, name="announcement_detail"),
    path("<int:pk>/edit/", views.edit_announcement, name="edit_announcement"),
    path("<int:pk>/approve/", views.approve_announcement_view, name="approve_announcement"),
    path("<int:pk>/reject/", views.reject_announcement_view, name="reject_announcement"),
    path("<int:pk>/archive/", views.archive_announcement_view, name="archive_announcement"),
    path("track/<int:pk>/", views.track_view, name="track_view"),
]
