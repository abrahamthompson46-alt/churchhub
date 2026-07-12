from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from permissions.models import Permission, PermissionAuditLog, PermissionOverride, RolePermission


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "category", "is_active", "sort_order")
    list_filter = ("category", "is_active")
    search_fields = ("name", "codename")
    ordering = ("category", "sort_order")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "granted", "updated_at")
    list_filter = ("role", "granted", "permission__category")
    search_fields = ("permission__codename", "permission__name")


@admin.register(PermissionOverride)
class PermissionOverrideAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "granted", "is_active", "expires_at", "created_at")
    list_filter = ("granted", "is_active")
    search_fields = ("user__username", "permission__codename")
    raw_id_fields = ("user", "created_by")


@admin.register(PermissionAuditLog)
class PermissionAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "performed_by", "target_user", "created_at")
    list_filter = ("action",)
    readonly_fields = ("action", "performed_by", "target_user", "details", "ip_address", "created_at")
