from django.urls import path

from . import views

app_name = "contributions"

urlpatterns = [
    path("", views.campaign_list, name="campaign_list"),
    path("add/", views.campaign_create, name="campaign_create"),
    path("<uuid:pk>/", views.campaign_detail, name="campaign_detail"),
    path("<uuid:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("<uuid:pk>/open/", views.campaign_open, name="campaign_open"),
    path("<uuid:pk>/close/", views.campaign_close, name="campaign_close"),
    path("<uuid:pk>/archive/", views.campaign_archive, name="campaign_archive"),
    path("<uuid:pk>/record/", views.campaign_record_contribution, name="campaign_record"),
    path("<uuid:pk>/bulk/", views.campaign_bulk_entry, name="campaign_bulk"),
    path("<uuid:pk>/import/", views.campaign_import, name="campaign_import"),
    path("<uuid:pk>/import/template/", views.campaign_import_template, name="campaign_import_template"),
    path("<uuid:pk>/targets/", views.campaign_targets, name="campaign_targets"),
]
