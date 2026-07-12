from django.apps import AppConfig


class SitecontrolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sitecontrol"
    verbose_name = "Platform Control"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_plans(sender, **kwargs):
            if sender.name != "sitecontrol":
                return
            from sitecontrol.services import ensure_default_plans
            ensure_default_plans()

        post_migrate.connect(seed_plans, dispatch_uid="sitecontrol_seed_plans")
