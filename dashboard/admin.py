from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "category", "read", "created_at")
    list_filter = ("read", "category", "created_at")
    search_fields = ("user__username", "title", "message")
    readonly_fields = ("created_at",)
