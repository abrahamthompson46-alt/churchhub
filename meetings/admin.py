from django.contrib import admin

from admin_custom.tenancy import filter_admin_qs_by_church

from .models import (
    AttendanceEvent,
    AttendanceRecord,
    Meeting,
    MeetingActionItem,
    MeetingAttachment,
    MeetingAttendance,
    MeetingDecision,
)


class MeetingAttendanceInline(admin.TabularInline):
    model = MeetingAttendance
    extra = 0


class ChurchScopedMeetingAdmin(admin.ModelAdmin):
    church_field = "church"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return filter_admin_qs_by_church(qs, request.user, self.church_field)


@admin.register(Meeting)
class MeetingAdmin(ChurchScopedMeetingAdmin):
    list_display = ("title", "church", "scheduled_at", "status")
    list_filter = ("status", "church")
    inlines = [MeetingAttendanceInline]


@admin.register(MeetingActionItem)
class MeetingActionItemAdmin(ChurchScopedMeetingAdmin):
    church_field = "meeting__church"
    list_display = ("description", "meeting", "status", "due_date")
    list_filter = ("status",)
    search_fields = ("description", "meeting__title")


@admin.register(MeetingDecision)
class MeetingDecisionAdmin(ChurchScopedMeetingAdmin):
    church_field = "meeting__church"
    list_display = ("decision_text", "meeting", "recorded_at")
    search_fields = ("decision_text", "meeting__title")


@admin.register(MeetingAttachment)
class MeetingAttachmentAdmin(ChurchScopedMeetingAdmin):
    church_field = "meeting__church"
    list_display = ("label", "meeting", "uploaded_at")
    search_fields = ("label", "meeting__title")


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(ChurchScopedMeetingAdmin):
    list_display = ("title", "church", "event_date", "event_type")
    list_filter = ("event_type", "church")
    search_fields = ("title", "church__name")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ChurchScopedMeetingAdmin):
    church_field = "event__church"
    list_display = ("event", "member", "is_present")
    list_filter = ("is_present",)
    search_fields = ("member__first_name", "member__last_name", "event__title")
