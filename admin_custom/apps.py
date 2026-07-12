from django.apps import AppConfig


class AdminCustomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_custom"
    verbose_name = "Admin Branding"

    def ready(self):
        from types import MethodType

        from django.contrib import admin

        admin.site.site_header = "ChurchHub Platform"
        admin.site.site_title = "ChurchHub Admin"
        admin.site.index_title = "Break-Glass Console"

        def _has_permission(self, request):
            user = request.user
            return (
                user.is_active
                and user.is_authenticated
                and user.is_superuser
                and getattr(user, "is_platform_user", False)
            )

        admin.site.has_permission = MethodType(_has_permission, admin.site)
