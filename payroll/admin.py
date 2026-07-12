from django.contrib import admin

from payroll.encryption import mask_account_number
from payroll.models import (
    DeductionType,
    Employee,
    EmployeeCompensation,
    EmployeeLoan,
    PayComponentType,
    PayrollLine,
    PayrollRun,
    PayrollRunAuditLog,
    PayrollTaxBand,
    PayrollTaxTable,
    StatutoryContributionRule,
)
from payroll.services import get_employee_pii


class ChurchScopedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        church = getattr(request.user, "church", None)
        if church and hasattr(qs.model, "host_church_id"):
            return qs.filter(host_church=church)
        if church and hasattr(qs.model, "employee"):
            return qs.filter(employee__host_church=church)
        if church and hasattr(qs.model, "payroll_run"):
            return qs.filter(payroll_run__host_church=church)
        return qs.none()


@admin.register(PayComponentType)
class PayComponentTypeAdmin(ChurchScopedAdmin):
    list_display = ("code", "name", "host_church", "is_taxable", "is_active")
    list_filter = ("is_active", "host_church")


@admin.register(DeductionType)
class DeductionTypeAdmin(ChurchScopedAdmin):
    list_display = ("code", "name", "host_church", "is_statutory", "is_active")
    list_filter = ("is_statutory", "is_active", "host_church")


@admin.register(PayrollTaxTable)
class PayrollTaxTableAdmin(ChurchScopedAdmin):
    list_display = ("name", "host_church", "effective_from", "is_active")
    list_filter = ("is_active", "host_church")


@admin.register(PayrollTaxBand)
class PayrollTaxBandAdmin(admin.ModelAdmin):
    list_display = ("tax_table", "lower_limit", "upper_limit", "rate_percent")


@admin.register(StatutoryContributionRule)
class StatutoryContributionRuleAdmin(ChurchScopedAdmin):
    list_display = ("code", "name", "host_church", "employee_rate", "employer_rate", "is_active")


@admin.register(Employee)
class EmployeeAdmin(ChurchScopedAdmin):
    list_display = (
        "employee_number",
        "full_name",
        "host_church",
        "status",
        "masked_account",
        "bank_name",
    )
    list_filter = ("status", "host_church", "employment_type")
    search_fields = ("employee_number", "first_name", "last_name")
    readonly_fields = (
        "tin_encrypted",
        "ssnit_number_encrypted",
        "bank_account_encrypted",
        "created_at",
        "updated_at",
    )
    exclude = ()

    @admin.display(description="Account")
    def masked_account(self, obj):
        pii = get_employee_pii(obj)
        return mask_account_number(pii.get("bank_account", ""))


@admin.register(EmployeeCompensation)
class EmployeeCompensationAdmin(ChurchScopedAdmin):
    list_display = ("employee", "effective_from", "is_active")


@admin.register(EmployeeLoan)
class EmployeeLoanAdmin(ChurchScopedAdmin):
    list_display = ("employee", "principal", "balance", "monthly_recovery", "status")
    list_filter = ("status",)


@admin.register(PayrollRun)
class PayrollRunAdmin(ChurchScopedAdmin):
    list_display = (
        "reference",
        "host_church",
        "year",
        "month",
        "status",
        "total_gross",
        "total_net",
        "prepared_by",
    )
    list_filter = ("status", "year", "host_church")
    search_fields = ("reference",)
    readonly_fields = (
        "reference",
        "total_gross",
        "total_deductions",
        "total_net",
        "total_employer_cost",
        "transaction",
        "payment_transaction",
        "approved_by",
        "approved_at",
        "treasury_approved_by",
        "treasury_approved_at",
        "posted_at",
        "paid_at",
        "created_at",
        "updated_at",
    )


@admin.register(PayrollLine)
class PayrollLineAdmin(ChurchScopedAdmin):
    list_display = ("payroll_run", "employee", "gross_pay", "net_pay", "payslip_number")
    readonly_fields = ("gross_pay", "total_deductions", "net_pay", "employer_cost")


@admin.register(PayrollRunAuditLog)
class PayrollRunAuditLogAdmin(admin.ModelAdmin):
    list_display = ("payroll_run", "action", "performed_by", "created_at")
    list_filter = ("action",)
    readonly_fields = ("payroll_run", "action", "performed_by", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
