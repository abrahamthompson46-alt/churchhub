from django.urls import path

from . import views

app_name = "assets"

urlpatterns = [
    path("", views.index, name="index"),
    path("assets/", views.asset_list, name="asset_list"),
    path("assets/new/", views.asset_create, name="asset_create"),
    path("assets/<uuid:pk>/", views.asset_detail, name="asset_detail"),
    path("assets/<uuid:pk>/edit/", views.asset_edit, name="asset_edit"),
    path("assets/<uuid:pk>/submit/", views.asset_submit, name="asset_submit"),
    path("assets/<uuid:pk>/approve/", views.asset_approve, name="asset_approve"),
    path("assets/<uuid:pk>/reject/", views.asset_reject, name="asset_reject"),
    path("assets/<uuid:pk>/dispose/", views.asset_dispose, name="asset_dispose"),
    path("assets/<uuid:pk>/maintenance/", views.maintenance_add, name="maintenance_add"),
    path("assets/export.csv", views.asset_export_csv, name="asset_export_csv"),
    path("policy/", views.policy_edit, name="policy_edit"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<uuid:pk>/edit/", views.category_edit, name="category_edit"),
    path("depreciation/run/", views.run_depreciation, name="run_depreciation"),
    path("activity/", views.activity_log, name="activity_log"),
    path("activity/export.csv", views.activity_log_export, name="activity_log_export"),
    path("hierarchy/", views.hierarchy_rollup, name="hierarchy"),
]
