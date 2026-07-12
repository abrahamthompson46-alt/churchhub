from django.contrib import admin

from ledger.models import LedgerCategory


@admin.register(LedgerCategory)
class LedgerCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "church",
        "transaction_type",
        "default_debit_account",
        "default_credit_account",
        "remit_to_district",
        "is_active",
        "sort_order",
    )
    list_filter = ("transaction_type", "is_active", "remit_to_district", "church")
    search_fields = ("name", "code", "church__name")
    ordering = ("church", "transaction_type", "sort_order")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            "church",
            "default_debit_account",
            "default_credit_account",
        )
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "church") and request.user.church:
            return qs.filter(church=request.user.church)
        return qs.none()
