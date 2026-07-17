from django.urls import path

from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.index, name="index"),
    path("accounts/", views.account_list, name="accounts"),
    path("accounts/add/", views.account_create, name="account_add"),
    path("accounts/<uuid:pk>/edit/", views.account_edit, name="account_edit"),
    path("categories/", views.category_list, name="categories"),
    path("categories/add/", views.category_create, name="category_add"),
    path("categories/<uuid:pk>/", views.category_detail, name="category_detail"),
    path("categories/<uuid:pk>/edit/", views.category_edit, name="category_edit"),
    path("by-category/", views.category_report, name="category_report"),
    path("entries/", views.entry_list, name="entries"),
    path("entry/", views.entry_create, name="entry"),
    path("entry/confirm/", views.entry_confirm, name="entry_confirm"),
    path("api/categories/", views.api_categories, name="api_categories"),
    path("api/categories/<uuid:pk>/", views.api_category_detail, name="api_category_detail"),
]
