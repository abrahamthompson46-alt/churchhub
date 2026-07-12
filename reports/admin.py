from django.contrib import admin

from .models import ReportAccessAuditLog, ReportExportJob


@admin.register(ReportExportJob)
class ReportExportJobAdmin(admin.ModelAdmin):
    list_display = ("report_key", "export_format", "status", "user", "created_at")
    list_filter = ("status", "export_format")
    readonly_fields = (
        "user",
        "report_key",
        "export_format",
        "params",
        "status",
        "export_file",
        "content_type",
        "error_message",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(ReportAccessAuditLog)
class ReportAccessAuditLogAdmin(admin.ModelAdmin):
    list_display = ("report_key", "action", "export_format", "user", "row_count", "created_at")
    list_filter = ("action", "export_format", "report_key")
    readonly_fields = (
        "user",
        "report_key",
        "action",
        "export_format",
        "params",
        "row_count",
        "church",
        "created_at",
    )
    search_fields = ("report_key", "user__username")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
