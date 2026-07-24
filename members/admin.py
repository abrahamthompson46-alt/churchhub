from django.contrib import admin
from django.db import models
from django.forms import TextInput, ModelForm
from django.utils.html import format_html

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin

from .models import (
    Department,
    Family,
    History,
    HistoryImage,
    LeadershipRole,
    Member,
    MemberAuditLog,
    MemberLookupOption,
    MemberTransfer,
    Occupation,
    Record,
    RecordImage,
    SpiritualGift,
    Visitor,
)


def image_preview(obj):
    if obj.image:
        return format_html(
            '<img src="{}" width="80" style="border-radius:6px;" />',
            obj.image.url,
        )
    return "-"


image_preview.short_description = "Preview"


def _church_qs(qs, request):
    if request.user.is_superuser:
        return qs
    if getattr(request.user, "church_id", None):
        return qs.filter(church=request.user.church)
    return qs.none()


@admin.register(Occupation)
class OccupationAdmin(admin.ModelAdmin):
    list_display = ["name", "church"]
    search_fields = ["name"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.church_id and request.user.church_id:
            obj.church = request.user.church
        super().save_model(request, obj, form, change)


class AgeGroupFilter(admin.SimpleListFilter):
    title = "Age Group"
    parameter_name = "age_group"

    def lookups(self, request, model_admin):
        return [
            ("CHILD", "Child (0–12)"),
            ("TEEN", "Teen (13–17)"),
            ("YOUTH", "Youth (18–35)"),
            ("ADULT", "Adult (36–59)"),
            ("SENIOR", "Senior (60+)"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        from members.models import age_group_for_age

        ids = [
            m.pk
            for m in queryset.filter(date_of_birth__isnull=False).only("id", "date_of_birth")
            if age_group_for_age(m.age) == value
        ]
        return queryset.filter(pk__in=ids)


class MemberAdminForm(ModelForm):
    class Meta:
        model = Member
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user and not self.instance.pk and getattr(user, "church_id", None):
            self.fields["church"].initial = user.church


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    form = MemberAdminForm
    list_display = [
        "first_name",
        "last_name",
        "gender",
        "church",
        "membership_status",
        "phone",
        "created_at",
    ]
    readonly_fields = ("created_at", "updated_at")
    exclude = ("created_by",)
    search_fields = ["first_name", "last_name", "phone", "membership_number", "address"]
    list_filter = ["gender", "membership_status", "is_active", "church", AgeGroupFilter]
    formfield_overrides = {
        models.TextField: {"widget": TextInput(attrs={"size": "40"})},
    }

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class FormWithUser(form):
            def __new__(cls, *args, **kwargs2):
                kwargs2["user"] = request.user
                return form(*args, **kwargs2)

        return FormWithUser

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            if not obj.church_id and request.user.church_id:
                obj.church = request.user.church
        super().save_model(request, obj, form, change)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "church", "created_at"]
    search_fields = ["name"]
    list_filter = ["church"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ["name", "head", "church", "phone"]
    search_fields = ["name"]
    list_filter = ["church"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)


@admin.register(MemberTransfer)
class MemberTransferAdmin(admin.ModelAdmin):
    list_display = ["member", "from_church", "to_church", "status", "transfer_date"]
    list_filter = ["status", "from_church", "to_church"]
    search_fields = ["member__first_name", "member__last_name"]
    readonly_fields = ["created_at", "updated_at", "processed_at"]


@admin.register(SpiritualGift)
class SpiritualGiftAdmin(admin.ModelAdmin):
    list_display = ["name", "church"]
    list_filter = ["church"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)


@admin.register(LeadershipRole)
class LeadershipRoleAdmin(admin.ModelAdmin):
    list_display = ["title", "member", "department", "church", "is_active"]
    list_filter = ["is_active", "church"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)


@admin.register(MemberAuditLog)
class MemberAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["action", "member", "church", "performed_by", "created_at"]
    list_filter = ["action", "church"]
    readonly_fields = ["action", "church", "member", "performed_by", "details", "created_at"]

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)


@admin.register(RecordImage)
class RecordImageAdmin(admin.ModelAdmin):
    list_display = ["id", image_preview, "uploaded_at"]
    readonly_fields = ["uploaded_at"]


class RecordAdminForm(ModelForm):
    class Meta:
        model = Record
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user and not self.instance.pk and getattr(user, "church_id", None):
            self.fields["church"].initial = user.church


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    form = RecordAdminForm
    list_display = ["title", "member", "record_type", "church", "event_date"]
    readonly_fields = ("created_at", "updated_at")
    exclude = ("created_by",)
    filter_horizontal = ("images",)
    search_fields = ["title", "member__first_name", "member__last_name", "certificate_number"]
    list_filter = ["record_type", "church", "event_date"]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class FormWithUser(form):
            def __new__(cls, *args, **kwargs2):
                kwargs2["user"] = request.user
                return form(*args, **kwargs2)

        return FormWithUser

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            if not obj.church_id and request.user.church_id:
                obj.church = request.user.church
        super().save_model(request, obj, form, change)


@admin.register(HistoryImage)
class HistoryImageAdmin(admin.ModelAdmin):
    list_display = ["id", image_preview, "uploaded_at"]
    readonly_fields = ["uploaded_at"]


class HistoryAdminForm(ModelForm):
    class Meta:
        model = History
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user and not self.instance.pk and getattr(user, "church_id", None):
            self.fields["church"].initial = user.church


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    form = HistoryAdminForm
    list_display = ["title", "member", "church", "date"]
    readonly_fields = ("created_at", "updated_at")
    exclude = ("created_by",)
    filter_horizontal = ("images",)
    search_fields = ["title", "member__first_name", "member__last_name"]
    list_filter = ["date", "church"]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class FormWithUser(form):
            def __new__(cls, *args, **kwargs2):
                kwargs2["user"] = request.user
                return form(*args, **kwargs2)

        return FormWithUser

    def get_queryset(self, request):
        return _church_qs(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            if not obj.church_id and request.user.church_id:
                obj.church = request.user.church
        super().save_model(request, obj, form, change)

@admin.register(MemberLookupOption)
class MemberLookupOptionAdmin(admin.ModelAdmin):
    list_display = ("category", "label", "code", "sort_order", "is_active", "is_system")
    list_filter = ("category", "is_active", "is_system")
    search_fields = ("label", "code")
    ordering = ("category", "sort_order", "label")

@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "church", "visit_date", "follow_up_status", "is_deleted")
    list_filter = ("follow_up_status", "church", "is_deleted")
    search_fields = ("first_name", "last_name", "phone", "email")
