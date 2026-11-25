from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_index, name="index"),
    path("welfare-statement/", views.welfare_statement, name="welfare_statement"),
    path("exports/<uuid:pk>/", views.export_job_status, name="export_job"),
    path("exports/<uuid:pk>/download/", views.export_job_download, name="export_job_download"),
    path("account/<uuid:account_id>/", views.account_activity, name="account_activity"),
    path("<slug:report_key>/", views.run_report, name="run"),
]
