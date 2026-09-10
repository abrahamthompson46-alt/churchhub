from admin_custom.audit_admin import ReadOnlyAuditModelAdmin
from django.contrib import admin

from intelligence.models import RiskAlert, RiskPolicy
from permissions.scoping import get_manageable_churches


@admin.register(RiskPolicy)
class RiskPolicyAdmin(admin.ModelAdmin):
    list_display = ["church", "is_active", "block_auto_approve_on_high", "large_absolute"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(church__in=get_manageable_churches(request.user))


@admin.register(RiskAlert)
class RiskAlertAdmin(ReadOnlyAuditModelAdmin):
    list_display = ["detected_at", "rule_code", "severity", "status", "church"]
    list_filter = ["severity", "status", "rule_code"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(church__in=get_manageable_churches(request.user))
