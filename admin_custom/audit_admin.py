"""Read-only Django admin for append-only audit logs."""

from django.contrib import admin


class ReadOnlyAuditModelAdmin(admin.ModelAdmin):
    """Prevent create, update, and delete on audit trail models."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [f.name for f in self.model._meta.fields]
        return list(self.readonly_fields) if self.readonly_fields else []
