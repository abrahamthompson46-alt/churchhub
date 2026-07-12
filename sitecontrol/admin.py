from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from sitecontrol.models import (
    PlatformAnnouncement,
    PlatformAuditLog,
    SiteSettings,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "session_timeout_minutes", "maintenance_mode", "updated_at")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "max_users",
        "max_branches",
        "feature_payroll",
        "feature_remittance",
        "is_default",
        "is_active",
    )
    list_filter = ("is_active", "feature_payroll", "feature_remittance")
    search_fields = ("name", "code")


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("church", "plan", "status", "started_at", "expires_at", "updated_at")
    list_filter = ("status", "plan")
    search_fields = ("church__name", "church__code")
    autocomplete_fields = ("church",)


@admin.register(PlatformAuditLog)
class PlatformAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("created_at", "user", "action", "summary", "ip_address")
    list_filter = ("action",)
    search_fields = ("summary", "user__username")
    readonly_fields = ("created_at", "user", "action", "target_model", "target_id", "summary", "details", "ip_address")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformAnnouncement)
class PlatformAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "show_on_login", "starts_at", "ends_at", "created_at")
    list_filter = ("is_active", "show_on_login")
    search_fields = ("title", "message")


@admin.register(TenantApplication)
class TenantApplicationAdmin(admin.ModelAdmin):
    list_display = ("church_name", "church_code", "status", "contact_email", "created_at")
    list_filter = ("status", "application_type")
    search_fields = ("church_name", "contact_email", "applicant_username")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
