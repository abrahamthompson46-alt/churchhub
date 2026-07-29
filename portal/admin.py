from django.contrib import admin

from .models import SpiritualSubmission, SpiritualSubmissionAuditLog


class SpiritualSubmissionAuditLogInline(admin.TabularInline):
    model = SpiritualSubmissionAuditLog
    extra = 0
    can_delete = False
    readonly_fields = ("action", "performed_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SpiritualSubmission)
class SpiritualSubmissionAdmin(admin.ModelAdmin):
    list_display = ("kind", "church", "status", "created_at", "is_anonymous")
    list_filter = ("kind", "status", "church")
    search_fields = ("body", "title", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    inlines = (SpiritualSubmissionAuditLogInline,)


@admin.register(SpiritualSubmissionAuditLog)
class SpiritualSubmissionAuditLogAdmin(admin.ModelAdmin):
    list_display = ("submission", "action", "performed_by", "created_at")
    list_filter = ("action",)
    readonly_fields = ("submission", "action", "performed_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
