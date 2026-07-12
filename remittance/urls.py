from django.urls import path

from . import views

app_name = "remittance"

urlpatterns = [
    path("", views.policy_index, name="index"),
    path("policies/add/", views.policy_create, name="policy_create"),
    path("policies/<uuid:pk>/edit/", views.policy_edit, name="policy_edit"),
    path("settlements/", views.settlement_list, name="settlements"),
    path("settlements/<uuid:pk>/post/", views.settlement_post, name="settlement_post"),
    path("welfare/", views.welfare_index, name="welfare"),
    path("welfare/member/<uuid:member_id>/", views.member_welfare_statement, name="member_welfare"),
    path("welfare/cases/<uuid:pk>/", views.welfare_case_detail, name="welfare_case_detail"),
    path("welfare/cases/<uuid:pk>/action/", views.welfare_case_action, name="welfare_case_action"),
]
