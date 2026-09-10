from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from django.contrib import admin

from audit.models import AuditEvent
from permissions.scoping import get_manageable_churches


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["occurred_at", "action", "domain", "church", "actor", "outcome"]
    list_filter = ["domain", "action", "outcome"]
    search_fields = ["object_label", "object_id", "action"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(church__in=get_manageable_churches(request.user))
