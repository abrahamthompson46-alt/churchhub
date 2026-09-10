from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("", views.case_list, name="case_list"),
    path("policy/", views.policy_edit, name="policy"),
    path("delegations/", views.delegation_list, name="delegations"),
    path("delegations/add/", views.delegation_create, name="delegation_create"),
    path("delegations/<uuid:pk>/revoke/", views.delegation_revoke, name="delegation_revoke"),
    path("cases/<uuid:pk>/", views.case_detail, name="case_detail"),
    path("transactions/<uuid:pk>/correct/", views.case_correct, name="correct"),
    path("transactions/<uuid:pk>/escalate/", views.case_escalate, name="escalate"),
]
