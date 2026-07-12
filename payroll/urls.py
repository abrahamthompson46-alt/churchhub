from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path("hierarchy/", views.hierarchy_dashboard, name="hierarchy"),
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/add/", views.employee_create, name="employee_create"),
    path("employees/<uuid:pk>/", views.employee_detail, name="employee_detail"),
    path("employees/<uuid:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("employees/<uuid:pk>/tax-certificate/", views.tax_certificate_pdf, name="tax_certificate"),
    path("employees/<uuid:employee_pk>/compensation/", views.compensation_create, name="compensation_create"),
    path("employees/<uuid:employee_pk>/loans/add/", views.loan_create, name="loan_create"),
    path("runs/", views.run_list, name="run_list"),
    path("runs/add/", views.run_create, name="run_create"),
    path("runs/<uuid:pk>/", views.run_detail, name="run_detail"),
    path("runs/<uuid:pk>/action/", views.run_action, name="run_action"),
    path("runs/<uuid:pk>/export-bank/", views.run_export_csv, name="run_export_csv"),
    path("runs/<uuid:pk>/export-register/", views.run_export_register, name="run_export_register"),
    path("runs/<uuid:pk>/paye-schedule/", views.run_paye_pdf, name="run_paye_pdf"),
    path("runs/<uuid:pk>/ssnit-schedule/", views.run_ssnit_pdf, name="run_ssnit_pdf"),
    path("payslips/<uuid:line_pk>/pdf/", views.payslip_pdf, name="payslip_pdf"),
    path("my-payslips/", views.my_payslips, name="my_payslips"),
    path("policies/", views.policy_index, name="policy_index"),
    path("policies/rules/add/", views.policy_rule_create, name="policy_rule_create"),
    path("policies/tables/<uuid:table_pk>/bands/add/", views.policy_band_add, name="policy_band_add"),
]
