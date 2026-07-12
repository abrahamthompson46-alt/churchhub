from django.apps import AppConfig


class RemittanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "remittance"
    verbose_name = "Remittance & Welfare"

    def ready(self):
        from django.db.models.signals import post_save

        from organization.models import Church
        from remittance.services import ensure_default_policies_for_church

        def _seed_policies(sender, instance, created, **kwargs):
            if created:
                ensure_default_policies_for_church(instance)

        post_save.connect(_seed_policies, sender=Church, dispatch_uid="remittance_seed_policies")
