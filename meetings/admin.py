from django.contrib import admin

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


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "church", "scheduled_at", "status")
    list_filter = ("status", "church")
    inlines = [MeetingAttendanceInline]


admin.site.register(MeetingActionItem)
admin.site.register(MeetingDecision)
admin.site.register(MeetingAttachment)
admin.site.register(AttendanceEvent)
admin.site.register(AttendanceRecord)
