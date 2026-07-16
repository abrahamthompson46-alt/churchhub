from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("", views.hierarchy_overview, name="hierarchy"),
    path("directory/", views.unit_directory, name="directory"),
    path("general-conferences/add/", views.general_conference_create, name="general_conference_create"),
    path("general-conferences/<uuid:pk>/", views.general_conference_detail, name="general_conference_detail"),
    path("general-conferences/<uuid:pk>/edit/", views.general_conference_edit, name="general_conference_edit"),
    path("unions/add/", views.union_create, name="union_create"),
    path("unions/<uuid:pk>/", views.union_detail, name="union_detail"),
    path("unions/<uuid:pk>/edit/", views.union_edit, name="union_edit"),
    path("conferences/add/", views.conference_create, name="conference_create"),
    path("conferences/<uuid:pk>/", views.conference_detail, name="conference_detail"),
    path("conferences/<uuid:pk>/edit/", views.conference_edit, name="conference_edit"),
    path("zones/add/", views.zone_create, name="zone_create"),
    path("zones/<uuid:pk>/", views.zone_detail, name="zone_detail"),
    path("zones/<uuid:pk>/edit/", views.zone_edit, name="zone_edit"),
    path("districts/add/", views.district_create, name="district_create"),
    path("districts/<uuid:pk>/", views.district_detail, name="district_detail"),
    path("districts/<uuid:pk>/edit/", views.district_edit, name="district_edit"),
    path("churches/onboard/", views.church_onboard, name="church_onboard"),
    path("churches/add/", views.church_create, name="church_create"),
    path("churches/<uuid:pk>/", views.church_detail, name="church_detail"),
    path("churches/<uuid:pk>/edit/", views.church_edit, name="church_edit"),
    path("churches/<uuid:pk>/transfer/", views.church_transfer, name="church_transfer"),
    path("churches/<uuid:pk>/toggle-active/", views.church_toggle_active, name="church_toggle_active"),
]
