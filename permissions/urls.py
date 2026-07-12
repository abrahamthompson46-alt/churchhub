from django.urls import path

from . import views

app_name = "permissions"

urlpatterns = [
    path("", views.index, name="index"),
    path("matrix/", views.role_matrix, name="matrix"),
    path("roles/", views.role_list, name="role_list"),
    path("roles/<slug:role>/", views.role_detail, name="role_detail"),
    path("overrides/", views.override_list, name="override_list"),
    path("overrides/add/", views.override_create, name="override_create"),
    path("overrides/<uuid:pk>/edit/", views.override_edit, name="override_edit"),
    path("overrides/<uuid:pk>/delete/", views.override_delete, name="override_delete"),
    path("users/<uuid:user_id>/effective/", views.user_effective, name="user_effective"),
    path("audit/", views.audit_log, name="audit_log"),
    path("export/matrix.csv", views.export_matrix_csv, name="export_matrix"),
]
