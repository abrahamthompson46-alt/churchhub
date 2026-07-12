from django.apps import AppConfig


class ChurchSystemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "church_system"
    verbose_name = "ChurchHub Core"

    def ready(self):
        from church_system.logging_config import configure_sentry

        configure_sentry()
