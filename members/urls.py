from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("", views.MemberListView.as_view(), name="list"),
    path("api/search/", views.member_search, name="search"),
    path("add/", views.add, name="add"),
    path("<uuid:member_id>/", views.member_detail, name="detail"),
    path("<uuid:member_id>/export/", views.member_export, name="member_export"),
    path("edit/<uuid:member_id>/", views.edit, name="edit"),
    path("timeline/<uuid:member_id>/", views.member_timeline, name="timeline"),
    path("records/", views.record_list, name="record_list"),
    path("records/add/", views.record_add, name="record_add"),
    path("records/<int:pk>/", views.record_detail, name="record_detail"),
    path("records/<int:pk>/edit/", views.record_edit, name="record_edit"),
    path("departments/", views.department_list, name="department_list"),
    path("departments/add/", views.department_add, name="department_add"),
    path("families/", views.family_list, name="family_list"),
    path("families/add/", views.family_add, name="family_add"),
    path("families/<uuid:pk>/", views.family_detail, name="family_detail"),
    path("transfers/", views.transfer_list, name="transfer_list"),
    path("transfers/add/", views.transfer_create, name="transfer_create"),
    path("transfers/<uuid:pk>/", views.transfer_detail, name="transfer_detail"),
    path("baptisms/", views.baptism_register, name="baptism_register"),
    path("leadership/", views.leadership_list, name="leadership_list"),
    path("leadership/add/", views.leadership_add, name="leadership_add"),
    path("spiritual-gifts/", views.spiritual_gift_list, name="spiritual_gift_list"),
    path("spiritual-gifts/add/", views.spiritual_gift_add, name="spiritual_gift_add"),
    path("<uuid:member_id>/assign-gift/", views.member_assign_gift, name="assign_gift"),
]
