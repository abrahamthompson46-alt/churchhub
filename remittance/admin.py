from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from remittance.models import (
    RemittancePolicy,
    RemittancePolicyAuditLog,
    SettlementBatch,
    SettlementLine,
    WelfareAssistanceCase,
    WelfareCaseAttachment,
    WelfareContribution,
    WelfareMemberLedger,
)


@admin.register(RemittancePolicy)
class RemittancePolicyAdmin(admin.ModelAdmin):
    list_display = (
        "unit_type",
        "offering_type",
        "application_scope",
        "retain_percent",
        "remit_percent",
        "is_active",
        "effective_from",
    )
    list_filter = ("unit_type", "offering_type", "application_scope", "is_active")
    search_fields = ("notes",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(RemittancePolicyAuditLog)
class RemittancePolicyAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "policy", "changed_by", "created_at")
    list_filter = ("action",)
    readonly_fields = ("snapshot", "created_at")


class SettlementLineInline(admin.TabularInline):
    model = SettlementLine
    extra = 0
    readonly_fields = ("source_transaction", "amount", "notes")


@admin.register(SettlementBatch)
class SettlementBatchAdmin(admin.ModelAdmin):
    list_display = (
        "offering_type",
        "from_unit_type",
        "to_unit_type",
        "period_end",
        "gross_received",
        "retain_amount",
        "remit_amount",
        "status",
    )
    list_filter = ("status", "offering_type", "from_unit_type")
    inlines = [SettlementLineInline]
    readonly_fields = ("posted_at", "created_at")


@admin.register(WelfareContribution)
class WelfareContributionAdmin(admin.ModelAdmin):
    list_display = ("church", "member", "amount", "contribution_date", "is_anonymous")
    list_filter = ("contribution_date", "is_anonymous")
    search_fields = ("member__first_name", "member__last_name", "church__name")


class WelfareCaseAttachmentInline(admin.TabularInline):
    model = WelfareCaseAttachment
    extra = 0
    readonly_fields = ("uploaded_by", "uploaded_at")


@admin.register(WelfareAssistanceCase)
class WelfareAssistanceCaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number",
        "church",
        "member",
        "assistance_type",
        "amount_requested",
        "amount_approved",
        "status",
        "created_at",
    )
    list_filter = ("status", "assistance_type", "priority")
    search_fields = ("case_number", "member__first_name", "member__last_name", "reason")
    inlines = [WelfareCaseAttachmentInline]
    readonly_fields = ("created_at", "updated_at", "approved_at", "reviewed_at", "disbursed_at")


@admin.register(WelfareMemberLedger)
class WelfareMemberLedgerAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("entry_date", "church", "member", "entry_type", "direction", "amount", "reference")
    list_filter = ("entry_type", "direction", "entry_date")
    search_fields = ("member__first_name", "member__last_name", "reference", "description")
