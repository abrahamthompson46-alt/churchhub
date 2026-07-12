from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin

from .models import (
    AssetAuditLog,
    AssetCategory,
    AssetCategoryTemplate,
    AssetDepreciationEntry,
    AssetMaintenanceLog,
    AssetPolicyAuditLog,
    DepreciationPolicy,
    FixedAsset,
)

admin.site.register(AssetCategoryTemplate)
admin.site.register(AssetCategory)
admin.site.register(DepreciationPolicy)
admin.site.register(FixedAsset)
admin.site.register(AssetDepreciationEntry)
admin.site.register(AssetMaintenanceLog)


@admin.register(AssetAuditLog)
class AssetAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "asset", "user", "created_at")
    list_filter = ("action",)


@admin.register(AssetPolicyAuditLog)
class AssetPolicyAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "church", "target_label", "user", "created_at")
    list_filter = ("action",)
