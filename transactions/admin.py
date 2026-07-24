from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.html import format_html

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin

from permissions.checks import can_approve_transactions
from members.models import Member

from .models import (
    Account,
    BankReconciliation,
    BankReconciliationItem,
    Budget,
    FinancialAuditLog,
    FinancialIdempotencyKey,
    FinancialPeriod,
    MonthlyCutoff,
    OfferingCategory,
    Transaction,
    TransactionLine,
    TreasuryApprovalPolicy,
    WorkingDay,
)
from .services import (
    approve_transaction as svc_approve,
    reject_transaction as svc_reject,
)

# =========================================================
# ACCOUNT ADMIN
# =========================================================
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "account_type", "church", "created_at"]
    search_fields = ["name"]
    list_filter = ["account_type", "church"]
    readonly_fields = ["created_at"]

# =========================================================
# TRANSACTION LINE INLINE
# =========================================================
class TransactionLineInline(admin.TabularInline):
    model = TransactionLine
    extra = 0
    can_delete = False
    autocomplete_fields = ["account"]
    readonly_fields = ["account", "amount", "fund", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False

# =========================================================
# TRANSACTION ADMIN
# =========================================================
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    inlines = [TransactionLineInline]

    list_display = [
        "reference",
        "transaction_type",
        "member_display",
        "church",
        "total_amount_display",
        "approval_status_colored",
        "date",
        "locked",
    ]

    list_filter = ["transaction_type", "approval_status", "church", "date"]
    search_fields = ["reference"]
    readonly_fields = [
        "reference",
        "created_by",
        "approved_by",
        "approved_at",
        "locked",
    ]
    actions = ["approve_selected", "reject_selected"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    # =====================================================
    # PERMISSION CHECK
    # =====================================================
    def can_approve(self, request):
        return can_approve_transactions(request.user)

    # =====================================================
    # INITIAL CHURCH SET
    # =====================================================
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if not request.user.is_superuser:
            if hasattr(request.user, "church") and request.user.church:
                initial["church"] = request.user.church.id
        return initial

    # =====================================================
    # FIELDSETS
    # =====================================================
    def get_fieldsets(self, request, obj=None):
        fields = ["transaction_type", "member"]
        if request.user.is_superuser:
            fields += ["church", "date"]
        return (
            ("Transaction Info", {"fields": tuple(fields)}),
            ("System Info", {
                "fields": ("reference", "created_by", "approved_by", "approved_at", "locked"),
                "classes": ("collapse",),
            }),
        )

    # =====================================================
    # FK FILTERING
    # =====================================================
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "church" and not request.user.is_superuser:
            if hasattr(request.user, "church") and request.user.church:
                kwargs["queryset"] = db_field.related_model.objects.filter(pk=request.user.church.pk)
            else:
                kwargs["queryset"] = db_field.related_model.objects.none()
        if db_field.name == "member":
            kwargs["required"] = False
            if not request.user.is_superuser and hasattr(request.user, "church"):
                kwargs["queryset"] = Member.objects.filter(church=request.user.church)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # =====================================================
    # SAVE MODEL
    # =====================================================
    def save_model(self, request, obj, form, change):
        raise PermissionDenied("Transactions must be created through the application UI.")

    def save_related(self, request, form, formsets, change):
        return

    # =====================================================
    # MEMBER DISPLAY
    # =====================================================
    def member_display(self, obj):
        return str(obj.member) if obj.member_id else "-"
    member_display.short_description = "Member"

    # =====================================================
    # TOTAL DISPLAY
    # =====================================================
    def total_amount_display(self, obj):
        return f"₵ {obj.total_amount:,.2f}"
    total_amount_display.short_description = "Total"

    # =====================================================
    # STATUS COLOR
    # =====================================================
    def approval_status_colored(self, obj):
        colors = {
            "PENDING": "#f39c12",
            "APPROVED": "#27ae60",
            "REJECTED": "#c0392b",
        }
        return format_html('<strong style="color:{};">{}</strong>', colors.get(obj.approval_status, "black"), obj.approval_status)
    approval_status_colored.short_description = "Status"

    # =====================================================
    # ACTION VISIBILITY CONTROL
    # =====================================================
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.can_approve(request):
            actions.pop("approve_selected", None)
            actions.pop("reject_selected", None)
        return actions

    # =====================================================
    # APPROVE / REJECT ACTIONS
    # =====================================================
    def approve_selected(self, request, queryset):
        if not self.can_approve(request):
            raise PermissionDenied("You do not have permission to approve transactions.")
        updated = 0
        for obj in queryset.filter(approval_status="PENDING"):
            try:
                svc_approve(obj, request.user)
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f"{updated} transaction(s) approved.")
    approve_selected.short_description = "Approve selected transactions"

    def reject_selected(self, request, queryset):
        if not self.can_approve(request):
            raise PermissionDenied("You do not have permission to reject transactions.")
        updated = 0
        for obj in queryset.filter(approval_status="PENDING"):
            try:
                svc_reject(obj, request.user)
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f"{updated} transaction(s) rejected.")
    reject_selected.short_description = "Reject selected transactions"

    # =====================================================
    # PROFESSIONAL TOTALS (FILTER-AWARE)
    # =====================================================
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            cl = response.context_data["cl"]
            qs = cl.queryset.prefetch_related("lines")
            total = approved = pending = rejected = 0
            for obj in qs[:500]:
                amt = abs(obj.receipt_total)
                total += amt
                if obj.approval_status == "APPROVED":
                    approved += amt
                elif obj.approval_status == "PENDING":
                    pending += amt
                else:
                    rejected += amt
            self.message_user(
                request,
                f"TOTAL: ₵ {total:,.2f} | APPROVED: ₵ {approved:,.2f} | "
                f"PENDING: ₵ {pending:,.2f} | REJECTED: ₵ {rejected:,.2f}",
                level="INFO",
            )
        except Exception:
            pass
        return response

    # =====================================================
    # DATA ISOLATION
    # =====================================================
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("church")
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(WorkingDay)
class WorkingDayAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["church", "date", "status", "opened_by", "closed_by"]
    list_filter = ["status", "church", "date"]
    readonly_fields = [
        "church", "date", "status", "opened_by", "opened_at",
        "closed_by", "closed_at", "notes", "updated_at",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(FinancialIdempotencyKey)
class FinancialIdempotencyKeyAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["church", "user", "action", "idempotency_key", "transaction", "created_at"]
    list_filter = ["action", "church"]
    readonly_fields = [
        "church", "user", "action", "idempotency_key", "transaction", "created_at",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


# =========================================================
# MONTHLY CUTOFF ADMIN
# =========================================================
@admin.register(MonthlyCutoff)
class MonthlyCutoffAdmin(admin.ModelAdmin):

    list_display = [
        "church",
        "month",
        "total_tithe",
        "total_combined",
        "total_payable_display",
        "transferred",
    ]

    readonly_fields = ["total_payable_display", "created_at"]
    list_filter = ["church", "month", "transferred"]

    def total_payable_display(self, obj):
        return f"₵ {obj.total_payable:,.2f}"
    total_payable_display.short_description = "Total Payable"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(OfferingCategory)
class OfferingCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "church", "remit_to_district", "is_active"]
    list_filter = ["church", "is_active", "remit_to_district"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["year", "level", "account", "amount", "church"]
    list_filter = ["year", "level", "church"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(FinancialAuditLog)
class FinancialAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["action", "church", "performed_by", "created_at"]
    list_filter = ["action", "church"]
    readonly_fields = ["action", "church", "transaction", "performed_by", "details", "created_at"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


class BankReconciliationItemInline(admin.TabularInline):
    model = BankReconciliationItem
    extra = 0


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = [
        "bank_account",
        "statement_date",
        "statement_balance",
        "book_balance",
        "is_reconciled",
    ]
    list_filter = ["church", "is_reconciled"]
    inlines = [BankReconciliationItemInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ("church", "year", "month", "is_locked", "locked_by", "locked_at")
    list_filter = ("is_locked", "year", "church")
    readonly_fields = ("locked_at", "created_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()


@admin.register(TreasuryApprovalPolicy)
class TreasuryApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "church",
        "receipt_auto_approve_enabled",
        "default_receipt_auto_approve_limit",
        "updated_at",
    )
    list_filter = ("receipt_auto_approve_enabled",)
    search_fields = ("church__name", "church__code")
