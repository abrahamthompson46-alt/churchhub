from django.contrib import admin

from .models import Church, Conference, District, GeneralConference, OrganizationAuditLog, Union, Zone


def _scoped_church_qs(request, qs):
    user = request.user
    if not user.is_authenticated:
        return qs.none()
    if user.is_superuser and not getattr(user, "is_platform_user", False):
        return qs
    from permissions.org_scope import church_q_for_scope

    return qs.filter(church_q_for_scope(user))


def _church_ids_for_user(request):
    return _scoped_church_qs(request, Church.objects.all()).values_list("pk", flat=True)


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0


@admin.register(GeneralConference)
class GeneralConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and not getattr(request.user, "is_platform_user", False):
            return qs
        return qs.filter(
            unions__conferences__zones__districts__churches__in=_church_ids_for_user(request)
        ).distinct()


class UnionInline(admin.TabularInline):
    model = Union
    extra = 0


@admin.register(Union)
class UnionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "general_conference")
    list_filter = ("general_conference",)
    search_fields = ("name", "code")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and not getattr(request.user, "is_platform_user", False):
            return qs
        return qs.filter(
            conferences__zones__districts__churches__in=_church_ids_for_user(request)
        ).distinct()


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "denomination", "union", "created_at")
    list_filter = ("denomination", "union")
    search_fields = ("name", "code")
    inlines = [ZoneInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and not getattr(request.user, "is_platform_user", False):
            return qs
        return qs.filter(
            zones__districts__churches__in=_church_ids_for_user(request)
        ).distinct()


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "conference")
    list_filter = ("conference", "conference__denomination")
    search_fields = ("name", "code")
    inlines = [DistrictInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and not getattr(request.user, "is_platform_user", False):
            return qs
        return qs.filter(districts__churches__in=_church_ids_for_user(request)).distinct()


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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and not getattr(request.user, "is_platform_user", False):
            return qs
        return qs.filter(churches__in=_church_ids_for_user(request)).distinct()


@admin.register(Church)
class ChurchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "district", "is_active", "financials_provisioned", "created_at")
    list_filter = ("is_active", "district__zone__conference", "district", "financials_provisioned")
    search_fields = ("name", "code", "address")

    def get_queryset(self, request):
        return _scoped_church_qs(request, super().get_queryset(request))


@admin.register(OrganizationAuditLog)
class OrganizationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_label", "performed_by", "created_at")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_label", "performed_by__username")
    readonly_fields = ("action", "entity_type", "entity_id", "entity_label", "details", "created_at")
