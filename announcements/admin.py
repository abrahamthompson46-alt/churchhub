from django.contrib import admin

from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from admin_custom.tenancy import filter_admin_qs_by_church
from announcements.models import Announcement, AnnouncementAuditLog, AnnouncementImage, AnnouncementView
from announcements.services import approve_announcement, archive_announcement, reject_announcement


class AnnouncementImageInline(admin.TabularInline):
    model = AnnouncementImage
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "visibility",
        "church",
        "is_pinned",
        "created_by",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "visibility", "is_pinned", "is_archived", "church")
    search_fields = ("title", "content", "created_by__username")
    readonly_fields = (
        "status",
        "is_approved",
        "is_rejected",
        "is_archived",
        "approved_at",
        "approved_by",
        "rejected_at",
        "rejected_by",
        "rejection_reason",
        "archived_at",
        "archived_by",
        "created_at",
        "updated_at",
        "created_by",
    )
    inlines = [AnnouncementImageInline]
    actions = ["action_approve", "action_reject", "action_archive"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "content",
                    "visibility",
                    "church",
                    "event_date",
                    "publish_at",
                    "auto_expire",
                    "is_pinned",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "is_approved",
                    "approved_by",
                    "approved_at",
                    "is_rejected",
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                    "is_archived",
                    "archived_by",
                    "archived_at",
                ),
            },
        ),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related("church", "created_by", "approved_by")
        )
        return filter_admin_qs_by_church(qs, request.user)

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Approve selected (via service)")
    def action_approve(self, request, queryset):
        ok = 0
        for obj in queryset.filter(is_archived=False, is_rejected=False):
            try:
                approve_announcement(obj, request.user)
                ok += 1
            except Exception:
                continue
        self.message_user(request, f"Approved {ok} announcement(s).")

    @admin.action(description="Reject selected (via service)")
    def action_reject(self, request, queryset):
        ok = 0
        for obj in queryset.filter(is_approved=False, is_archived=False, is_rejected=False):
            try:
                reject_announcement(obj, request.user, reason="Rejected via admin.")
                ok += 1
            except Exception:
                continue
        self.message_user(request, f"Rejected {ok} announcement(s).")

    @admin.action(description="Archive selected (via service)")
    def action_archive(self, request, queryset):
        ok = 0
        for obj in queryset.filter(is_archived=False):
            try:
                archive_announcement(obj, request.user)
                ok += 1
            except Exception:
                continue
        self.message_user(request, f"Archived {ok} announcement(s).")


@admin.register(AnnouncementView)
class AnnouncementViewAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("announcement", "user", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("announcement__title", "user__username")
    readonly_fields = ("announcement", "user", "viewed_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user, "announcement__church")


@admin.register(AnnouncementAuditLog)
class AnnouncementAuditLogAdmin(ReadOnlyAuditModelAdmin):
    list_display = ("action", "announcement", "church", "performed_by", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("announcement__title", "performed_by__username")
    readonly_fields = (
        "announcement",
        "church",
        "action",
        "performed_by",
        "details",
        "created_at",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user)
