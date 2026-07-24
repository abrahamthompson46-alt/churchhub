from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("pending/", views.pending_approvals, name="pending_approvals"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/<uuid:pk>/", views.transaction_detail, name="transaction_detail"),
    path("transactions/<uuid:pk>/void/", views.void_transaction_view, name="void_transaction"),
    path("approve/<uuid:pk>/", views.approve_transaction_view, name="approve_transaction"),
    path("reject/<uuid:pk>/", views.reject_transaction_view, name="reject_transaction"),
    path("receipt/<uuid:pk>/", views.transaction_receipt, name="transaction_receipt"),
    path("confirm/<uuid:pk>/", views.transaction_receipt, name="transaction_confirm"),
    path("bulk-approve/", views.bulk_approve, name="bulk_approve"),
    path("financial-dashboard/", views.financial_dashboard, name="financial_dashboard"),
    path("record/receipt/", views.record_receipt_view, name="record_receipt"),
    path("record/expense/", views.record_expense_view, name="record_expense"),
    path("remittance/", views.record_remittance_view, name="record_remittance"),
    path("budget/", views.budget_report, name="budget_report"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("periods/", views.period_list, name="period_list"),
    path("periods/approval-policy/", views.treasury_approval_policy_save, name="treasury_approval_policy"),
    path("periods/lock/", views.period_lock, name="period_lock"),
    path("periods/unlock/", views.period_unlock, name="period_unlock"),
    path("working-day/open/", views.working_day_open, name="working_day_open"),
    path("working-day/close/", views.working_day_close, name="working_day_close"),
    path("reconciliations/", views.reconciliation_list, name="reconciliation_list"),
    path("reconciliations/add/", views.reconciliation_create, name="reconciliation_create"),
    path("reconciliations/<uuid:pk>/", views.reconciliation_detail, name="reconciliation_detail"),
]
