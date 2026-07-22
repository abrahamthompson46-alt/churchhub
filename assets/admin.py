from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from admin_custom.tenancy import filter_admin_qs_by_church

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


@admin.register(AssetCategoryTemplate)
class AssetCategoryTemplateAdmin(admin.ModelAdmin):
    """Platform-wide templates — not church-scoped."""

    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


class ChurchScopedAssetAdmin(admin.ModelAdmin):
    church_field = "church"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user, self.church_field)


@admin.register(AssetCategory)
class AssetCategoryAdmin(ChurchScopedAssetAdmin):
    list_display = ("code", "name", "church", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "church__name")


@admin.register(DepreciationPolicy)
class DepreciationPolicyAdmin(ChurchScopedAssetAdmin):
    list_display = ("church", "default_method", "updated_at")
    search_fields = ("church__name", "church__code")


@admin.register(FixedAsset)
class FixedAssetAdmin(ChurchScopedAssetAdmin):
    list_display = ("asset_code", "name", "church", "status", "acquisition_cost")
    list_filter = ("status",)
    search_fields = ("asset_code", "name", "church__name")


@admin.register(AssetDepreciationEntry)
class AssetDepreciationEntryAdmin(ChurchScopedAssetAdmin):
    church_field = "asset__church"
    list_display = ("asset", "period_year", "period_month", "amount")
    list_filter = ("period_year",)


@admin.register(AssetMaintenanceLog)
class AssetMaintenanceLogAdmin(ChurchScopedAssetAdmin):
    church_field = "asset__church"
    list_display = ("asset", "service_date", "cost")
    search_fields = ("asset__asset_code", "asset__name")


@admin.register(AssetAuditLog)
class AssetAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "asset", "user", "created_at")
    list_filter = ("action",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user, "asset__church")


@admin.register(AssetPolicyAuditLog)
class AssetPolicyAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "church", "target_label", "user", "created_at")
    list_filter = ("action",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user, "church")
