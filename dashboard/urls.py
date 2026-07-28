from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("switch-church/", views.switch_church, name="switch_church"),
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notifications/<int:pk>/delete/", views.notification_delete, name="notification_delete"),
    path("notifications/read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("notifications/count/", views.notification_count, name="notification_count"),
    path("notifications/pending/", views.pending_announcements_ajax, name="pending_announcements_count"),
    path("teller-console/", views.teller_console_api, name="teller_console_api"),
    path("pin-action/", views.pin_quick_action, name="pin_quick_action"),
    path("cutoff/", views.cutoff, name="cutoff"),
    path("logout/", views.custom_logout, name="logout"),
]
