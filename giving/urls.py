from django.urls import path

from . import views

app_name = "giving"

urlpatterns = [
    path("", views.giving_index, name="index"),
    path("member/<uuid:member_id>/", views.member_statement, name="member_statement"),
]
