from django.contrib import admin

from .models import Church, Conference, District, GeneralConference, OrganizationAuditLog, Union, Zone


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0


@admin.register(GeneralConference)
class GeneralConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")


class UnionInline(admin.TabularInline):
    model = Union
    extra = 0


@admin.register(Union)
class UnionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "general_conference")
    list_filter = ("general_conference",)
    search_fields = ("name", "code")


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "denomination", "union", "created_at")
    list_filter = ("denomination", "union")
    search_fields = ("name", "code")
    inlines = [ZoneInline]


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "conference")
    list_filter = ("conference", "conference__denomination")
    search_fields = ("name", "code")
    inlines = [DistrictInline]


class ChurchInline(admin.TabularInline):
    model = Church
    extra = 0
    fields = ("name", "code", "is_active", "address")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "zone")
    list_filter = ("zone__conference", "zone", "zone__conference__denomination")
    search_fields = ("name", "code")
    inlines = [ChurchInline]


@admin.register(Church)
class ChurchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "district", "is_active", "financials_provisioned", "created_at")
    list_filter = ("is_active", "district__zone__conference", "district", "financials_provisioned")
    search_fields = ("name", "code", "address")


@admin.register(OrganizationAuditLog)
class OrganizationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_label", "performed_by", "created_at")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_label", "performed_by__username")
    readonly_fields = ("action", "entity_type", "entity_id", "entity_label", "details", "created_at")
