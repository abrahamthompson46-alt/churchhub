from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_list, name="list"),
    path("add/", views.budget_create, name="create"),
    path("clone/", views.budget_clone, name="clone"),
    path("<uuid:pk>/edit/", views.budget_edit, name="edit"),
    path("<uuid:pk>/delete/", views.budget_delete, name="delete"),
]
