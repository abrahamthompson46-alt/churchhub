from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import TrustedDevice, User, UserActivityLog, UserInvitation


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Church & Role Info",
            {
                "fields": (
                    "role",
                    "church",
                    "phone",
                    "member",
                    "denomination",
                    "mfa_enabled",
                ),
            },
        ),
        (
            "Platform",
            {
                "fields": (
                    "is_platform_user",
                    "platform_role",
                    "managed_denominations",
                ),
            },
        ),
    )
    readonly_fields = ("member", "mfa_enabled", "mfa_secret", "mfa_recovery_hashes")
    filter_horizontal = ("managed_denominations", "groups", "user_permissions")
    list_display = (
        "username",
        "email",
        "role",
        "church",
        "is_platform_user",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "church", "is_platform_user", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            for field in (
                "is_platform_user",
                "platform_role",
                "managed_denominations",
                "denomination",
                "member",
            ):
                if field not in readonly:
                    readonly.append(field)
        return readonly


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "performed_by", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "action", "performed_by", "ip_address", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserInvitation)
class UserInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "username",
        "role",
        "church",
        "is_accepted",
        "revoked_at",
        "expires_at",
        "created_at",
    )
    list_filter = ("is_accepted", "role", "church")
    search_fields = ("email", "username")
    readonly_fields = ("token", "accepted_at", "revoked_at", "created_at")


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "ip_address", "last_used_at", "expires_at")
    list_filter = ("expires_at",)
    search_fields = ("user__username", "label")
    readonly_fields = (
        "user",
        "token_hash",
        "label",
        "user_agent",
        "ip_address",
        "created_at",
        "last_used_at",
        "expires_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
